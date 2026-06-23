from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from code_rag.apps.jobs.index_job_queue import IndexJobQueue
from code_rag.domain.models import JobStatus
from code_rag.interfaces.rest.dependencies import get_job_queue, get_job_store
from code_rag.interfaces.rest.routers.helpers import job_status_from_result
from code_rag.ports.job_store import JobStorePort

router = APIRouter()


@router.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(
    job_id: str,
    queue: IndexJobQueue = Depends(get_job_queue),
    job_store: JobStorePort = Depends(get_job_store),
):
    status_result = queue.get(job_id)
    if status_result:
        return status_result
    persisted_result = job_store.get_job(job_id)
    if persisted_result:
        return job_status_from_result(persisted_result)
    raise HTTPException(status_code=404, detail="Job not found")
