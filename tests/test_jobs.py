from __future__ import annotations

from code_rag.apps.jobs.index_job_queue import IndexJobQueue
from code_rag.domain.models import IndexJobRecord, IndexJobResult, JobStatus
from code_rag.domain.time import utcnow


class RecordingJobStore:
    def __init__(self) -> None:
        self.records: dict[str, IndexJobRecord] = {}

    def enqueue_job(self, record: IndexJobRecord) -> JobStatus:
        self.records[record.job_id] = record
        return self._status(record)

    def get_job_status(self, job_id: str) -> JobStatus | None:
        record = self.records.get(job_id)
        return self._status(record) if record else None

    def claim_next_job(self, worker_id: str, lock_ttl_seconds: float) -> IndexJobRecord | None:
        for record in self.records.values():
            if record.status == "queued":
                claimed = record.model_copy(
                    update={"status": "running", "locked_by": worker_id, "started_at": utcnow()}
                )
                self.records[record.job_id] = claimed
                return claimed
        return None

    def finish_job(self, job_id: str, result: IndexJobResult) -> JobStatus:
        record = self.records[job_id].model_copy(
            update={
                "status": result.status,
                "finished_at": result.finished_at,
                "result": result,
            }
        )
        self.records[job_id] = record
        return self._status(record)

    def fail_job(self, job_id: str, error_message: str) -> JobStatus:
        record = self.records[job_id].model_copy(
            update={"status": "failed", "finished_at": utcnow(), "error_message": error_message}
        )
        self.records[job_id] = record
        return self._status(record)

    def record_job(self, job: IndexJobResult) -> None:
        pass

    def get_job(self, job_id: str) -> IndexJobResult | None:
        record = self.records.get(job_id)
        return record.result if record else None

    def record_job_status(self, status: JobStatus) -> None:
        self.records[status.job_id] = IndexJobRecord(**status.model_dump())

    def _status(self, record: IndexJobRecord) -> JobStatus:
        return JobStatus(
            job_id=record.job_id,
            job_type=record.job_type,
            status=record.status,
            submitted_at=record.submitted_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            result=record.result,
            error_message=record.error_message,
        )


def _result(job_id: str) -> IndexJobResult:
    now = utcnow()
    return IndexJobResult(
        job_id=job_id,
        job_type="full_repo_index",
        gitlab_project_id="123",
        repo_path_with_namespace="group/payments",
        branch="develop",
        new_sha="abc",
        status="succeeded",
        started_at=now,
        finished_at=now,
    )


def test_queue_persists_payload_and_reads_from_store() -> None:
    store = RecordingJobStore()
    queue = IndexJobQueue(store=store, max_workers=1)

    status = queue.submit("job-1", "full_repo_index", {"project": {"gitlab_project_id": "123"}})

    assert status.status == "queued"
    assert queue.get("job-1").status == "queued"
    assert store.records["job-1"].payload["project"]["gitlab_project_id"] == "123"


def test_queue_claims_and_finishes_job() -> None:
    store = RecordingJobStore()
    queue = IndexJobQueue(store=store, max_workers=1)
    queue.submit("job-1", "full_repo_index", {"project": {"gitlab_project_id": "123"}})

    record = store.claim_next_job(queue.worker_id, queue.lock_ttl_seconds)
    assert record is not None and record.status == "running"
    finished = store.finish_job("job-1", _result("job-1"))

    assert finished.status == "succeeded"
    assert queue.get("job-1").result is not None
