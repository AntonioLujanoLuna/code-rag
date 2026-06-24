from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from code_rag.domain.models.index_job_result import IndexJobResult


class IndexJobRecord(BaseModel):
    job_id: str
    status: str
    job_type: str
    submitted_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: IndexJobResult | None = None
    error_message: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    locked_by: str | None = None
    lock_expires_at: datetime | None = None
    attempts: int = 0
