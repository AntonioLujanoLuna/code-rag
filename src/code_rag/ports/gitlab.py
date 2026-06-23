from __future__ import annotations

from typing import Protocol

from code_rag.domain.models import ChangedFile, GitLabProject


class GitLabPort(Protocol):
    def get_project(self, project_id: str) -> GitLabProject:
        """Fetch project metadata by GitLab project id."""

    def list_group_projects(self, group_id: str) -> list[GitLabProject]:
        """List projects under a GitLab group."""

    def compare(self, project_id: str, old_sha: str, new_sha: str) -> list[ChangedFile]:
        """Return file changes between two commits."""
