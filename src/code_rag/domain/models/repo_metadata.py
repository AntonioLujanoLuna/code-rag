from __future__ import annotations

from pydantic import BaseModel, Field


class RepoMetadata(BaseModel):
    repo_path_with_namespace: str
    service_name: str | None = None
    team_owner: str | None = None
    business_domain: str | None = None
    slack_channel: str | None = None
    jira_project: str | None = None
    primary_language: str | None = None
    service_type: str | None = None
    deployment_name: str | None = None
    tags: list[str] = Field(default_factory=list)
