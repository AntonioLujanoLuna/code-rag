from __future__ import annotations

import time
from threading import RLock

from fastapi import HTTPException

from code_rag.config.settings import Settings
from code_rag.domain.models import PermissionRecord
from code_rag.ports.permissions import PermissionStorePort


class PermissionService:
    def __init__(self, settings: Settings, store: PermissionStorePort) -> None:
        self.settings = settings
        self.store = store
        self._cache: dict[tuple[str, str | None, tuple[str, ...]], tuple[float, list[str]]] = {}
        self._lock = RLock()

    def upsert(self, record: PermissionRecord) -> PermissionRecord:
        if not record.tenant_id:
            record.tenant_id = self.settings.tenant_id
        record.accessible_project_ids = [str(item) for item in record.accessible_project_ids]
        self.store.upsert(record)
        with self._lock:
            for key in list(self._cache):
                if key[0] == record.tenant_id and key[1] == record.user_id:
                    self._cache.pop(key, None)
        return record

    def resolve_allowed_projects(
        self,
        tenant_id: str,
        user_id: str | None,
        requested_project_ids: list[str],
    ) -> list[str]:
        requested = [str(item) for item in requested_project_ids]
        cache_key = (tenant_id, user_id, tuple(sorted(requested)))
        ttl = self.settings.permission_cache_ttl_seconds
        now = time.monotonic()
        if ttl > 0:
            with self._lock:
                cached = self._cache.get(cache_key)
                if cached and cached[0] > now:
                    return list(cached[1])
        if user_id:
            record = self.store.get(tenant_id, user_id)
            if not record:
                raise HTTPException(status_code=403, detail="No GitLab permission cache for user")
            allowed = set(record.accessible_project_ids)
            result = sorted(allowed.intersection(requested)) if requested else sorted(allowed)
            self._store_cache(cache_key, ttl, result)
            return result
        if self.settings.allow_request_supplied_permissions and requested:
            self._store_cache(cache_key, ttl, requested)
            return requested
        raise HTTPException(status_code=403, detail="user_id with synced permissions is required")

    def _store_cache(
        self,
        cache_key: tuple[str, str | None, tuple[str, ...]],
        ttl: float,
        value: list[str],
    ) -> None:
        if ttl <= 0:
            return
        with self._lock:
            self._cache[cache_key] = (time.monotonic() + ttl, list(value))
