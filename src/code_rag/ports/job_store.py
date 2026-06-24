from __future__ import annotations

from typing import Protocol

from code_rag.domain.models import IndexJobRecord, IndexJobResult, JobStatus


class JobStorePort(Protocol):
    def record_job(self, job: IndexJobResult) -> None:
        """Persist an index job result."""

    def get_job(self, job_id: str) -> IndexJobResult | None:
        """Fetch a persisted index job result."""

    def record_job_status(self, status: JobStatus) -> None:
        """Persist a transient job status (queued/running/finished)."""

    def get_job_status(self, job_id: str) -> JobStatus | None:
        """Fetch a persisted job status if present."""

    def enqueue_job(self, record: IndexJobRecord) -> JobStatus:
        """Persist a queued index job if it is not already active or completed."""

    def claim_next_job(self, worker_id: str, lock_ttl_seconds: float) -> IndexJobRecord | None:
        """Atomically claim the next queued or expired running job."""

    def finish_job(self, job_id: str, result: IndexJobResult) -> JobStatus:
        """Persist a completed job result."""

    def fail_job(self, job_id: str, error_message: str) -> JobStatus:
        """Persist a failed job status."""
