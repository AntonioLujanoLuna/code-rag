from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

from code_rag.adapters.gitlab.gitlab_client import GitLabClient
from code_rag.apps.jobs.index_job_queue import IndexJobQueue
from code_rag.config.settings import Settings, get_settings
from code_rag.domain.ids import stable_id
from code_rag.domain.models import GitLabProject, JobStatus
from code_rag.interfaces.rest.dependencies import (
    get_gitlab,
    get_job_queue,
    get_job_store,
)
from code_rag.interfaces.rest.routers.helpers import job_status_from_result
from code_rag.ports.job_store import JobStorePort

router = APIRouter()


@router.post("/webhooks/gitlab", response_model=JobStatus | dict[str, str])
def gitlab_webhook(
    payload: dict[str, Any],
    x_gitlab_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    gitlab: GitLabClient = Depends(get_gitlab),
    queue: IndexJobQueue = Depends(get_job_queue),
    job_store: JobStorePort = Depends(get_job_store),
):
    if settings.gitlab_webhook_secret and x_gitlab_token != settings.gitlab_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token"
        )
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
        repo_path_with_namespace=project_payload.get("path_with_namespace") or "",
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
    job_id = stable_id(
        "incremental_repo_index", project.gitlab_project_id, branch, old_sha, new_sha
    )
    existing = job_store.get_job(job_id)
    if existing and existing.status == "succeeded":
        return job_status_from_result(existing)
    return queue.submit(
        job_id,
        "incremental_repo_index",
        {
            "project": project.model_dump(mode="json"),
            "branch": branch,
            "old_sha": old_sha,
            "new_sha": new_sha,
            "changes": None,
            "fallback_to_full_index": True,
        },
    )
