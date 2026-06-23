from __future__ import annotations

from typing import Protocol

from code_rag.domain.models import IndexJobResult, JobStatus


class JobStorePort(Protocol):
    def record_job(self, job: IndexJobResult) -> None:
        """Persist an index job result."""

    def get_job(self, job_id: str) -> IndexJobResult | None:
        """Fetch a persisted index job result."""

    def record_job_status(self, status: JobStatus) -> None:
        """Persist a transient job status (queued/running/finished)."""

    def get_job_status(self, job_id: str) -> JobStatus | None:
        """Fetch a persisted job status if present."""
