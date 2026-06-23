from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from threading import RLock

from code_rag.domain.models import IndexJobResult, JobStatus
from code_rag.domain.time import utcnow
from code_rag.ports.job_store import JobStorePort

logger = logging.getLogger(__name__)


class IndexJobQueue:
    """Async indexing queue.

    In-memory status is the fast path; an optional :class:`JobStorePort` makes
    queued/running/finished transitions durable so a different worker (or a
    process restart) can still answer ``GET /jobs/{id}``. The in-memory map is
    bounded with LRU eviction of completed jobs to avoid unbounded growth.
    """

    def __init__(
        self,
        max_workers: int = 2,
        store: JobStorePort | None = None,
        max_tracked_jobs: int = 1_000,
    ) -> None:
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="code-rag-index"
        )
        self.store = store
        self.max_tracked_jobs = max_tracked_jobs
        self._jobs: OrderedDict[str, JobStatus] = OrderedDict()
        self._futures: dict[str, Future[IndexJobResult]] = {}
        self._lock = RLock()

    def submit(
        self,
        job_id: str,
        job_type: str,
        work: Callable[[], IndexJobResult],
    ) -> JobStatus:
        with self._lock:
            existing = self._jobs.get(job_id)
            if existing and existing.status in {"queued", "running", "succeeded"}:
                return existing
            status = JobStatus(
                job_id=job_id,
                job_type=job_type,
                status="queued",
                submitted_at=utcnow(),
            )
            self._remember(status)
            future = self.executor.submit(self._run, job_id, work)
            self._futures[job_id] = future
            self._persist(status)
            return status

    def get(self, job_id: str) -> JobStatus | None:
        with self._lock:
            status = self._jobs.get(job_id)
        if status:
            return status
        if self.store:
            return self.store.get_job_status(job_id)
        return None

    def _run(self, job_id: str, work: Callable[[], IndexJobResult]) -> IndexJobResult:
        with self._lock:
            current = self._jobs[job_id]
            running = current.model_copy(update={"status": "running", "started_at": utcnow()})
            self._jobs[job_id] = running
        self._persist(running)
        logger.info("Index job started", extra={"job_id": job_id})
        try:
            result = work()
            status = "succeeded" if result.status == "succeeded" else "failed"
            with self._lock:
                finished = self._jobs[job_id].model_copy(
                    update={
                        "status": status,
                        "finished_at": utcnow(),
                        "result": result,
                        "error_message": result.error_message,
                    }
                )
                self._jobs[job_id] = finished
            self._persist(finished)
            logger.info(
                "Index job finished",
                extra={"job_id": job_id, "status": status, "chunks_added": result.chunks_added},
            )
            return result
        except Exception as exc:
            with self._lock:
                crashed = self._jobs[job_id].model_copy(
                    update={"status": "failed", "finished_at": utcnow(), "error_message": str(exc)}
                )
                self._jobs[job_id] = crashed
            self._persist(crashed)
            logger.exception("Index job crashed", extra={"job_id": job_id})
            raise

    def _remember(self, status: JobStatus) -> None:
        self._jobs[status.job_id] = status
        self._jobs.move_to_end(status.job_id)
        while len(self._jobs) > self.max_tracked_jobs:
            evict_id, evicted = next(iter(self._jobs.items()))
            if evicted.status in {"queued", "running"}:
                break
            self._jobs.popitem(last=False)
            self._futures.pop(evict_id, None)

    def _persist(self, status: JobStatus) -> None:
        if not self.store:
            return
        try:
            self.store.record_job_status(status)
        except Exception:
            logger.warning(
                "Failed to persist job status", extra={"job_id": status.job_id}, exc_info=True
            )
