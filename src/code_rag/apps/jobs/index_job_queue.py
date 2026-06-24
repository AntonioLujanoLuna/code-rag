from __future__ import annotations

import logging
import threading
import uuid

from code_rag.adapters.gitlab.gitlab_client import GitLabClient
from code_rag.apps.indexing.indexing_service import IndexingService
from code_rag.domain.models import (
    ChangedFile,
    GitLabProject,
    IndexJobRecord,
    IndexJobResult,
    JobStatus,
)
from code_rag.domain.time import utcnow
from code_rag.ports.job_store import JobStorePort

logger = logging.getLogger(__name__)


class IndexJobQueue:
    """Durable indexing queue backed by a JobStorePort claim protocol."""

    def __init__(
        self,
        store: JobStorePort,
        max_workers: int = 2,
        poll_interval_seconds: float = 0.5,
        lock_ttl_seconds: float = 900.0,
    ) -> None:
        self.store = store
        self.max_workers = max_workers
        self.poll_interval_seconds = poll_interval_seconds
        self.lock_ttl_seconds = lock_ttl_seconds
        self.worker_id = str(uuid.uuid4())
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()
        self._started = False
        self._lock = threading.RLock()

    def start(self, service: IndexingService, gitlab: GitLabClient) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            for worker_number in range(self.max_workers):
                thread = threading.Thread(
                    target=self._poll,
                    args=(service, gitlab),
                    name=f"code-rag-index-{worker_number}",
                    daemon=True,
                )
                thread.start()
                self._threads.append(thread)

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=5)

    def submit(self, job_id: str, job_type: str, payload: dict) -> JobStatus:
        return self.store.enqueue_job(
            IndexJobRecord(
                job_id=job_id,
                job_type=job_type,
                status="queued",
                submitted_at=utcnow(),
                payload=payload,
            )
        )

    def get(self, job_id: str) -> JobStatus | None:
        return self.store.get_job_status(job_id)

    def _poll(self, service: IndexingService, gitlab: GitLabClient) -> None:
        while not self._stop.is_set():
            try:
                record = self.store.claim_next_job(self.worker_id, self.lock_ttl_seconds)
                if record is None:
                    self._stop.wait(self.poll_interval_seconds)
                    continue
                self._run(record, service, gitlab)
            except Exception:
                logger.exception("Index job polling failed")
                self._stop.wait(self.poll_interval_seconds)

    def _run(
        self,
        record: IndexJobRecord,
        service: IndexingService,
        gitlab: GitLabClient,
    ) -> IndexJobResult:
        logger.info(
            "Index job started", extra={"job_id": record.job_id, "job_type": record.job_type}
        )
        try:
            result = self._execute(record, service, gitlab)
            if result.job_id != record.job_id:
                result = result.model_copy(update={"job_id": record.job_id})
            self.store.finish_job(record.job_id, result)
            logger.info(
                "Index job finished",
                extra={
                    "job_id": record.job_id,
                    "status": result.status,
                    "chunks_added": result.chunks_added,
                },
            )
            return result
        except Exception as exc:
            self.store.fail_job(record.job_id, str(exc))
            logger.exception("Index job crashed", extra={"job_id": record.job_id})
            raise

    def _execute(
        self,
        record: IndexJobRecord,
        service: IndexingService,
        gitlab: GitLabClient,
    ) -> IndexJobResult:
        payload = record.payload
        project = GitLabProject.model_validate(payload["project"])
        if record.job_type == "full_repo_index":
            return service.full_index_project(
                project=project,
                branch=payload.get("branch"),
                commit_sha=payload.get("commit_sha"),
            )
        if record.job_type == "incremental_repo_index":
            old_sha = payload["old_sha"]
            new_sha = payload["new_sha"]
            changes_payload = payload.get("changes")
            changes = (
                [ChangedFile.model_validate(item) for item in changes_payload]
                if changes_payload is not None
                else gitlab.compare(project.gitlab_project_id, old_sha, new_sha)
            )
            if not changes and payload.get("fallback_to_full_index"):
                return service.full_index_project(project, payload.get("branch"), new_sha)
            return service.incremental_index_project(
                project=project,
                old_sha=old_sha,
                new_sha=new_sha,
                changes=changes,
                branch=payload.get("branch"),
            )
        raise ValueError(f"Unsupported index job type {record.job_type!r}")
