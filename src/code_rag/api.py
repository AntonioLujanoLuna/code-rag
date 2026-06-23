from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from code_rag.adapters.gitlab_client import GitLabClient
from code_rag.adapters.answer import ExtractiveAnswerProvider
from code_rag.application.indexing import IndexingService
from code_rag.application.jobs import IndexJobQueue
from code_rag.application.metrics import MetricsRegistry
from code_rag.application.permissions import PermissionService
from code_rag.application.retrieval import RetrievalService
from code_rag.dependencies import (
    get_answer_provider,
    get_gitlab,
    get_index,
    get_indexing_service,
    get_job_queue,
    get_metrics,
    get_permission_service,
    get_retrieval_service,
)
from code_rag.domain.ids import stable_id
from code_rag.models import (
    AnswerRequest,
    AnswerResponse,
    ChangedFile,
    GitLabProject,
    IndexJobResult,
    JobStatus,
    PermissionRecord,
    SearchRequest,
    SearchResponse,
    SourceCitation,
)
from code_rag.settings import Settings, get_settings


app = FastAPI(title="GitLab Code RAG", version="0.1.0")
logger = logging.getLogger(__name__)


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    started = time.perf_counter()
    metrics = get_metrics()
    try:
        response = await call_next(request)
    except Exception:
        duration = time.perf_counter() - started
        metrics.increment("http_requests_failed_total")
        metrics.observe("http_request_duration_seconds", duration)
        logger.exception(
            "HTTP request failed",
            extra={"method": request.method, "path": request.url.path, "duration_seconds": duration},
        )
        raise
    duration = time.perf_counter() - started
    metrics.increment("http_requests_total")
    metrics.observe("http_request_duration_seconds", duration)
    response.headers["X-Process-Time-Ms"] = f"{duration * 1000:.2f}"
    logger.info(
        "HTTP request completed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_seconds": duration,
        },
    )
    return response


class IndexProjectRequest(BaseModel):
    project_id: str = Field(..., description="GitLab project id")
    repo_path_with_namespace: str | None = None
    repo_name: str | None = None
    repo_url: str | None = None
    branch: str | None = None
    commit_sha: str | None = None


class IncrementalIndexRequest(BaseModel):
    project_id: str
    repo_path_with_namespace: str | None = None
    repo_name: str | None = None
    repo_url: str | None = None
    branch: str | None = None
    old_sha: str
    new_sha: str
    changes: list[ChangedFile] | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics(registry: MetricsRegistry = Depends(get_metrics)) -> dict[str, dict]:
    return registry.snapshot()


@app.post("/indices/init")
def init_indices(index=Depends(get_index)) -> dict[str, str]:
    index.ensure_indices()
    return {"status": "created"}


@app.post("/index/project", response_model=JobStatus)
def index_project(
    request: IndexProjectRequest,
    service: IndexingService = Depends(get_indexing_service),
    gitlab: GitLabClient = Depends(get_gitlab),
    queue: IndexJobQueue = Depends(get_job_queue),
):
    project = _project_from_request(request, gitlab)
    branch = request.branch or get_settings().branch
    job_id = stable_id("full_repo_index", project.gitlab_project_id, branch, None, request.commit_sha or "")
    existing = service.index.get_job(job_id)
    if existing and existing.status == "succeeded":
        return _job_status_from_result(existing)

    def work():
        result = service.full_index_project(project, request.branch, request.commit_sha)
        return _record_job_result(service, result, job_id)

    return queue.submit(job_id, "full_repo_index", work)


@app.post("/index/incremental", response_model=JobStatus)
def incremental_index_project(
    request: IncrementalIndexRequest,
    service: IndexingService = Depends(get_indexing_service),
    gitlab: GitLabClient = Depends(get_gitlab),
    queue: IndexJobQueue = Depends(get_job_queue),
):
    project = _project_from_incremental_request(request, gitlab)
    branch = request.branch or get_settings().branch
    job_id = stable_id(
        "incremental_repo_index", project.gitlab_project_id, branch, request.old_sha, request.new_sha
    )
    existing = service.index.get_job(job_id)
    if existing and existing.status == "succeeded":
        return _job_status_from_result(existing)

    def work():
        changes = request.changes or gitlab.compare(request.project_id, request.old_sha, request.new_sha)
        result = service.incremental_index_project(
            project=project,
            old_sha=request.old_sha,
            new_sha=request.new_sha,
            changes=changes,
            branch=request.branch,
        )
        return _record_job_result(service, result, job_id)

    return queue.submit(job_id, "incremental_repo_index", work)


@app.post("/webhooks/gitlab", response_model=JobStatus | dict[str, str])
def gitlab_webhook(
    payload: dict[str, Any],
    x_gitlab_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    service: IndexingService = Depends(get_indexing_service),
    gitlab: GitLabClient = Depends(get_gitlab),
    queue: IndexJobQueue = Depends(get_job_queue),
):
    if settings.gitlab_webhook_secret and x_gitlab_token != settings.gitlab_webhook_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token")
    ref = payload.get("ref", "")
    branch = ref.removeprefix("refs/heads/")
    if branch != settings.branch:
        return {"status": "ignored", "reason": f"branch {branch!r} is not {settings.branch!r}"}
    project_payload = payload.get("project") or {}
    project_id = str(project_payload.get("id") or payload.get("project_id"))
    if not project_id:
        raise HTTPException(status_code=400, detail="Missing project id")
    project = GitLabProject(
        gitlab_project_id=project_id,
        repo_path_with_namespace=project_payload.get("path_with_namespace")
        or project_payload.get("path_with_namespace")
        or "",
        repo_name=project_payload.get("name") or project_payload.get("path") or project_id,
        repo_url=project_payload.get("git_http_url")
        or project_payload.get("http_url")
        or project_payload.get("web_url")
        or gitlab.get_project(project_id).repo_url,
        default_branch=project_payload.get("default_branch"),
        description=project_payload.get("description"),
    )
    if not project.repo_path_with_namespace:
        project = gitlab.get_project(project_id)
    old_sha = payload.get("before")
    new_sha = payload.get("after")
    if not old_sha or not new_sha:
        raise HTTPException(status_code=400, detail="Missing before/after commit SHA")
    job_id = stable_id("incremental_repo_index", project.gitlab_project_id, branch, old_sha, new_sha)
    existing = service.index.get_job(job_id)
    if existing and existing.status == "succeeded":
        return _job_status_from_result(existing)

    def work():
        changes = gitlab.compare(project_id, old_sha, new_sha)
        if not changes:
            result = service.full_index_project(project, branch, new_sha)
        else:
            result = service.incremental_index_project(project, old_sha, new_sha, changes, branch)
        return _record_job_result(service, result, job_id)

    return queue.submit(job_id, "incremental_repo_index", work)


@app.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(
    job_id: str,
    queue: IndexJobQueue = Depends(get_job_queue),
    service: IndexingService = Depends(get_indexing_service),
):
    status_result = queue.get(job_id)
    if status_result:
        return status_result
    persisted_result = service.index.get_job(job_id)
    if persisted_result:
        return _job_status_from_result(persisted_result)
    raise HTTPException(status_code=404, detail="Job not found")


@app.post("/permissions", response_model=PermissionRecord)
def upsert_permissions(
    record: PermissionRecord,
    service: PermissionService = Depends(get_permission_service),
) -> PermissionRecord:
    return service.upsert(record)


@app.post("/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    service: RetrievalService = Depends(get_retrieval_service),
) -> SearchResponse:
    return service.search(request)


@app.post("/answer", response_model=AnswerResponse)
def answer(
    request: AnswerRequest,
    retrieval: RetrievalService = Depends(get_retrieval_service),
    answer_provider: ExtractiveAnswerProvider = Depends(get_answer_provider),
) -> AnswerResponse:
    search_response = retrieval.search(SearchRequest(**request.model_dump()))
    citations = [
        SourceCitation(
            index=index,
            repo_path_with_namespace=hit.repo_path_with_namespace,
            file_path=hit.file_path,
            line_start=hit.line_start,
            line_end=hit.line_end,
            url=hit.gitlab_blob_url,
        )
        for index, hit in enumerate(search_response.hits, start=1)
    ]
    return AnswerResponse(
        query=request.query,
        answer=answer_provider.answer(search_response, request.max_context_chars),
        grounded=answer_provider.is_grounded(search_response),
        refusal_reason=answer_provider.refusal_reason(search_response),
        source_coverage=answer_provider.source_coverage(search_response),
        query_type=search_response.query_type,
        identifiers=search_response.identifiers,
        sources=citations,
        context=search_response.context[: request.max_context_chars],
    )


def _project_from_request(request: IndexProjectRequest, gitlab: GitLabClient) -> GitLabProject:
    if request.repo_path_with_namespace and request.repo_url:
        return GitLabProject(
            gitlab_project_id=request.project_id,
            repo_path_with_namespace=request.repo_path_with_namespace,
            repo_name=request.repo_name or request.repo_path_with_namespace.rsplit("/", 1)[-1],
            repo_url=request.repo_url,
        )
    return gitlab.get_project(request.project_id)


def _project_from_incremental_request(
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


def _job_status_from_result(result: IndexJobResult) -> JobStatus:
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


def _record_job_result(
    service: IndexingService, result: IndexJobResult, request_job_id: str
) -> IndexJobResult:
    if result.job_id != request_job_id:
        result = result.model_copy(update={"job_id": request_job_id})
    service.index.record_job(result)
    return result
