from __future__ import annotations

from code_rag.adapters.gitlab.gitlab_client import GitLabClient
from code_rag.domain.models import GitLabProject, IndexJobResult, JobStatus
from code_rag.interfaces.rest.routers.schemas import (
    IncrementalIndexRequest,
    IndexProjectRequest,
)
from code_rag.ports.job_store import JobStorePort


def project_from_request(request: IndexProjectRequest, gitlab: GitLabClient) -> GitLabProject:
    if request.repo_path_with_namespace and request.repo_url:
        return GitLabProject(
            gitlab_project_id=request.project_id,
            repo_path_with_namespace=request.repo_path_with_namespace,
            repo_name=request.repo_name or request.repo_path_with_namespace.rsplit("/", 1)[-1],
            repo_url=request.repo_url,
        )
    return gitlab.get_project(request.project_id)


def project_from_incremental_request(
    request: IncrementalIndexRequest, gitlab: GitLabClient
) -> GitLabProject:
    if request.repo_path_with_namespace and request.repo_url:
        return GitLabProject(
            gitlab_project_id=request.project_id,
            repo_path_with_namespace=request.repo_path_with_namespace,
            repo_name=request.repo_name or request.repo_path_with_namespace.rsplit("/", 1)[-1],
            repo_url=request.repo_url,
        )
    return gitlab.get_project(request.project_id)


def job_status_from_result(result: IndexJobResult) -> JobStatus:
    return JobStatus(
        job_id=result.job_id,
        job_type=result.job_type,
        status=result.status,
        submitted_at=result.started_at,
        started_at=result.started_at,
        finished_at=result.finished_at,
        result=result,
        error_message=result.error_message,
    )


def record_job_result(
    job_store: JobStorePort, result: IndexJobResult, request_job_id: str
) -> IndexJobResult:
    if result.job_id != request_job_id:
        result = result.model_copy(update={"job_id": request_job_id})
    job_store.record_job(result)
    return result
