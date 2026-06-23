from __future__ import annotations

from threading import RLock

from code_rag.models import PermissionRecord


class InMemoryPermissionStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], PermissionRecord] = {}
        self._lock = RLock()

    def upsert(self, record: PermissionRecord) -> None:
        with self._lock:
            self._records[(record.tenant_id, record.user_id)] = record

    def get(self, tenant_id: str, user_id: str) -> PermissionRecord | None:
        with self._lock:
            return self._records.get((tenant_id, user_id))

