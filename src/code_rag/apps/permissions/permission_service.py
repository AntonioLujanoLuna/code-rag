from __future__ import annotations

from fastapi import HTTPException

from code_rag.config.settings import Settings
from code_rag.domain.models import PermissionRecord
from code_rag.ports.permissions import PermissionStorePort


class PermissionService:
    def __init__(self, settings: Settings, store: PermissionStorePort) -> None:
        self.settings = settings
        self.store = store

    def upsert(self, record: PermissionRecord) -> PermissionRecord:
        if not record.tenant_id:
            record.tenant_id = self.settings.tenant_id
        record.accessible_project_ids = [str(item) for item in record.accessible_project_ids]
        self.store.upsert(record)
        return record

    def resolve_allowed_projects(
        self,
        tenant_id: str,
        user_id: str | None,
        requested_project_ids: list[str],
    ) -> list[str]:
        requested = [str(item) for item in requested_project_ids]
        if user_id:
            record = self.store.get(tenant_id, user_id)
            if not record:
                raise HTTPException(status_code=403, detail="No GitLab permission cache for user")
            allowed = set(record.accessible_project_ids)
            if requested:
                return sorted(allowed.intersection(requested))
            return sorted(allowed)
        if self.settings.allow_request_supplied_permissions and requested:
            return requested
        raise HTTPException(status_code=403, detail="user_id with synced permissions is required")
