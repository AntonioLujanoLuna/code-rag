from __future__ import annotations

from code_rag.apps.jobs.index_job_queue import IndexJobQueue
from code_rag.domain.models import IndexJobResult, JobStatus
from code_rag.domain.time import utcnow


class RecordingJobStore:
    def __init__(self) -> None:
        self.statuses: dict[str, JobStatus] = {}

    def record_job_status(self, status: JobStatus) -> None:
        self.statuses[status.job_id] = status

    def get_job_status(self, job_id: str) -> JobStatus | None:
        return self.statuses.get(job_id)


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


def test_queue_persists_status_transitions_and_falls_back_to_store() -> None:
    store = RecordingJobStore()
    queue = IndexJobQueue(max_workers=1, store=store)

    status = queue.submit("job-1", "full_repo_index", lambda: _result("job-1"))
    assert status.status in {"queued", "running", "succeeded"}
    queue.executor.shutdown(wait=True)

    # The store captured at least the terminal status.
    assert store.get_job_status("job-1") is not None
    assert store.get_job_status("job-1").status == "succeeded"

    # A fresh queue (simulating another worker) resolves via the store.
    other = IndexJobQueue(max_workers=1, store=store)
    resolved = other.get("job-1")
    assert resolved is not None and resolved.status == "succeeded"


def test_in_memory_finished_jobs_are_evicted_when_bounded() -> None:
    queue = IndexJobQueue(max_workers=1, max_tracked_jobs=2)
    queue.executor.shutdown(wait=True)
    for i in range(5):
        queue._remember(
            JobStatus(
                job_id=f"job-{i}",
                job_type="full_repo_index",
                status="succeeded",
                submitted_at=utcnow(),
            )
        )

    # Completed jobs beyond the bound are evicted (LRU).
    assert len(queue._jobs) == 2
    assert "job-4" in queue._jobs and "job-3" in queue._jobs


def test_running_jobs_are_not_evicted() -> None:
    queue = IndexJobQueue(max_workers=1, max_tracked_jobs=1)
    queue.executor.shutdown(wait=True)
    queue._remember(
        JobStatus(job_id="running", job_type="t", status="running", submitted_at=utcnow())
    )
    queue._remember(
        JobStatus(job_id="queued", job_type="t", status="queued", submitted_at=utcnow())
    )

    # Neither in-flight job is evicted even though the bound is exceeded.
    assert "running" in queue._jobs and "queued" in queue._jobs
