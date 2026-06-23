from __future__ import annotations

from pydantic import BaseModel


class GitLabProject(BaseModel):
    gitlab_project_id: str
    repo_path_with_namespace: str
    repo_name: str
    repo_url: str
    default_branch: str | None = None
    description: str | None = None
