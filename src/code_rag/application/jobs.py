from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from threading import RLock

from code_rag.models import IndexJobResult, JobStatus, utcnow


logger = logging.getLogger(__name__)


class IndexJobQueue:
    def __init__(self, max_workers: int = 2) -> None:
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="code-rag-index")
        self._jobs: dict[str, JobStatus] = {}
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
            self._jobs[job_id] = status
            future = self.executor.submit(self._run, job_id, work)
            self._futures[job_id] = future
            return status

    def get(self, job_id: str) -> JobStatus | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _run(self, job_id: str, work: Callable[[], IndexJobResult]) -> IndexJobResult:
        with self._lock:
            current = self._jobs[job_id]
            self._jobs[job_id] = current.model_copy(update={"status": "running", "started_at": utcnow()})
        logger.info("Index job started", extra={"job_id": job_id})
        try:
            result = work()
            status = "succeeded" if result.status == "succeeded" else "failed"
            with self._lock:
                self._jobs[job_id] = self._jobs[job_id].model_copy(
                    update={
                        "status": status,
                        "finished_at": utcnow(),
                        "result": result,
                        "error_message": result.error_message,
                    }
                )
            logger.info(
                "Index job finished",
                extra={"job_id": job_id, "status": status, "chunks_added": result.chunks_added},
            )
            return result
        except Exception as exc:
            with self._lock:
                self._jobs[job_id] = self._jobs[job_id].model_copy(
                    update={"status": "failed", "finished_at": utcnow(), "error_message": str(exc)}
                )
            logger.exception("Index job crashed", extra={"job_id": job_id})
            raise
