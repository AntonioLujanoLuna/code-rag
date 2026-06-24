"""Durable index-job queue methods for the Elasticsearch adapter."""

from __future__ import annotations

from datetime import timedelta

from code_rag.adapters.elasticsearch._base import _CONFLICT_ERRORS, EsClientBase
from code_rag.domain.models import IndexJobRecord, IndexJobResult, JobStatus
from code_rag.domain.time import utcnow


class JobStoreMixin(EsClientBase):
    """Persisted job results, statuses, and worker-safe claiming."""

    def record_job(self, job: IndexJobResult) -> None:
        self.client.index(index=self.jobs_index, id=job.job_id, document=self._dump(job))

    def get_job(self, job_id: str) -> IndexJobResult | None:
        if not self.client.exists(index=self.jobs_index, id=job_id):
            return None
        response = self.client.get(index=self.jobs_index, id=job_id)
        return IndexJobResult.model_validate(response["_source"])

    def record_job_status(self, status: JobStatus) -> None:
        self.client.index(
            index=self.job_status_index,
            id=status.job_id,
            document=status.model_dump(mode="json"),
            refresh=True,
        )

    def get_job_status(self, job_id: str) -> JobStatus | None:
        if not self.client.exists(index=self.job_status_index, id=job_id):
            return None
        response = self.client.get(index=self.job_status_index, id=job_id)
        return JobStatus.model_validate(response["_source"])

    def enqueue_job(self, record: IndexJobRecord) -> JobStatus:
        existing = self.get_job_status(record.job_id)
        if existing and existing.status in {"queued", "running", "succeeded"}:
            return existing
        document = record.model_dump(mode="json")
        if existing:
            self.client.index(
                index=self.job_status_index,
                id=record.job_id,
                document=document,
                refresh=True,
            )
            return self._job_status(record)
        try:
            self.client.index(
                index=self.job_status_index,
                id=record.job_id,
                document=document,
                op_type="create",
                refresh=True,
            )
        except _CONFLICT_ERRORS:
            # Another worker created the same job concurrently; adopt its status.
            existing = self.get_job_status(record.job_id)
            if existing:
                return existing
            raise
        return self._job_status(record)

    def claim_next_job(self, worker_id: str, lock_ttl_seconds: float) -> IndexJobRecord | None:
        now = utcnow()
        response = self.client.search(
            index=self.job_status_index,
            query={
                "bool": {
                    "should": [
                        {"term": {"status": "queued"}},
                        {
                            "bool": {
                                "filter": [
                                    {"term": {"status": "running"}},
                                    {"range": {"lock_expires_at": {"lt": now.isoformat()}}},
                                ]
                            }
                        },
                    ],
                    "minimum_should_match": 1,
                }
            },
            sort=[{"submitted_at": {"order": "asc"}}],
            size=10,
            seq_no_primary_term=True,
        )
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            updates = {
                "status": "running",
                "started_at": now.isoformat(),
                "locked_by": worker_id,
                "lock_expires_at": (now + timedelta(seconds=lock_ttl_seconds)).isoformat(),
                "attempts": int(source.get("attempts") or 0) + 1,
            }
            try:
                self.client.update(
                    index=self.job_status_index,
                    id=hit["_id"],
                    if_seq_no=hit["_seq_no"],
                    if_primary_term=hit["_primary_term"],
                    doc=updates,
                    refresh=True,
                )
            except _CONFLICT_ERRORS:
                # Lost the race for this job to another worker; try the next one.
                continue
            return IndexJobRecord.model_validate({**source, **updates})
        return None

    def finish_job(self, job_id: str, result: IndexJobResult) -> JobStatus:
        status = "succeeded" if result.status == "succeeded" else "failed"
        self.record_job(result)
        self.client.update(
            index=self.job_status_index,
            id=job_id,
            doc={
                "status": status,
                "finished_at": utcnow().isoformat(),
                "result": result.model_dump(mode="json"),
                "error_message": result.error_message,
                "locked_by": None,
                "lock_expires_at": None,
            },
            refresh=True,
        )
        job_status = self.get_job_status(job_id)
        if job_status is None:
            raise RuntimeError(f"Job {job_id} disappeared after completion")
        return job_status

    def fail_job(self, job_id: str, error_message: str) -> JobStatus:
        self.client.update(
            index=self.job_status_index,
            id=job_id,
            doc={
                "status": "failed",
                "finished_at": utcnow().isoformat(),
                "error_message": error_message,
                "locked_by": None,
                "lock_expires_at": None,
            },
            refresh=True,
        )
        job_status = self.get_job_status(job_id)
        if job_status is None:
            raise RuntimeError(f"Job {job_id} disappeared after failure")
        return job_status
