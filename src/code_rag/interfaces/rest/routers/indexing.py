from __future__ import annotations

from fastapi import APIRouter, Depends

from code_rag.adapters.gitlab.gitlab_client import GitLabClient
from code_rag.apps.indexing.indexing_service import IndexingService
from code_rag.apps.jobs.index_job_queue import IndexJobQueue
from code_rag.config.settings import get_settings
from code_rag.domain.ids import stable_id
from code_rag.domain.models import JobStatus
from code_rag.interfaces.rest.dependencies import (
    get_gitlab,
    get_indexing_service,
    get_job_queue,
    get_job_store,
)
from code_rag.interfaces.rest.routers.helpers import (
    job_status_from_result,
    project_from_incremental_request,
    project_from_request,
    record_job_result,
)
from code_rag.interfaces.rest.routers.schemas import (
    IncrementalIndexRequest,
    IndexProjectRequest,
)
from code_rag.interfaces.rest.security import require_auth
from code_rag.ports.job_store import JobStorePort

router = APIRouter()


@router.post("/index/project", response_model=JobStatus)
def index_project(
    request: IndexProjectRequest,
    _: object = Depends(require_auth),
    service: IndexingService = Depends(get_indexing_service),
    gitlab: GitLabClient = Depends(get_gitlab),
    queue: IndexJobQueue = Depends(get_job_queue),
    job_store: JobStorePort = Depends(get_job_store),
):
    project = project_from_request(request, gitlab)
    branch = request.branch or get_settings().branch
    job_id = stable_id(
        "full_repo_index", project.gitlab_project_id, branch, None, request.commit_sha or ""
    )
    existing = job_store.get_job(job_id)
    if existing and existing.status == "succeeded":
        return job_status_from_result(existing)

    def work():
        result = service.full_index_project(project, request.branch, request.commit_sha)
        return record_job_result(job_store, result, job_id)

    return queue.submit(job_id, "full_repo_index", work)


@router.post("/index/incremental", response_model=JobStatus)
def incremental_index_project(
    request: IncrementalIndexRequest,
    _: object = Depends(require_auth),
    service: IndexingService = Depends(get_indexing_service),
    gitlab: GitLabClient = Depends(get_gitlab),
    queue: IndexJobQueue = Depends(get_job_queue),
    job_store: JobStorePort = Depends(get_job_store),
):
    project = project_from_incremental_request(request, gitlab)
    branch = request.branch or get_settings().branch
    job_id = stable_id(
        "incremental_repo_index",
        project.gitlab_project_id,
        branch,
        request.old_sha,
        request.new_sha,
    )
    existing = job_store.get_job(job_id)
    if existing and existing.status == "succeeded":
        return job_status_from_result(existing)

    def work():
        changes = request.changes or gitlab.compare(
            request.project_id, request.old_sha, request.new_sha
        )
        result = service.incremental_index_project(
            project=project,
            old_sha=request.old_sha,
            new_sha=request.new_sha,
            changes=changes,
            branch=request.branch,
        )
        return record_job_result(job_store, result, job_id)

    return queue.submit(job_id, "incremental_repo_index", work)
