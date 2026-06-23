from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from code_rag.domain.models.index_job_result import IndexJobResult


class JobStatus(BaseModel):
    job_id: str
    status: str
    job_type: str
    submitted_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: IndexJobResult | None = None
    error_message: str | None = None
