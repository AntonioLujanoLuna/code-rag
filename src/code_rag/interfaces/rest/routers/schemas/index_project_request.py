from __future__ import annotations

from pydantic import BaseModel, Field


class IndexProjectRequest(BaseModel):
    project_id: str = Field(..., description="GitLab project id")
    repo_path_with_namespace: str | None = None
    repo_name: str | None = None
    repo_url: str | None = None
    branch: str | None = None
    commit_sha: str | None = None
