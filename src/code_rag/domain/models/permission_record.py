from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from code_rag.domain.time import utcnow


class PermissionRecord(BaseModel):
    user_id: str
    tenant_id: str = "default"
    accessible_project_ids: list[str]
    last_synced_at: datetime = Field(default_factory=utcnow)
