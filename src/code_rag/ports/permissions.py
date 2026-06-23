from __future__ import annotations

from typing import Protocol

from code_rag.models import PermissionRecord


class PermissionStorePort(Protocol):
    def upsert(self, record: PermissionRecord) -> None:
        """Store a user permission record."""

    def get(self, tenant_id: str, user_id: str) -> PermissionRecord | None:
        """Return a user permission record when present."""

