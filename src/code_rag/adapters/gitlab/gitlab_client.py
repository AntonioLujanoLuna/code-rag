from __future__ import annotations

from urllib.parse import quote

import httpx

from code_rag.adapters.http.retries import request_with_retries
from code_rag.config.settings import Settings
from code_rag.domain.models import ChangedFile, GitLabProject


class GitLabClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = settings.gitlab_base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api/v4"

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.settings.gitlab_token:
            headers["PRIVATE-TOKEN"] = self.settings.gitlab_token
        return headers

    def get_project(self, project_id: str) -> GitLabProject:
        encoded = quote(str(project_id), safe="")
        with httpx.Client(timeout=30.0, headers=self._headers()) as client:
            response = request_with_retries(
                client,
                "GET",
                f"{self.api_url}/projects/{encoded}",
                retries=self.settings.http_retries,
                backoff_seconds=self.settings.http_retry_backoff_seconds,
            )
            response.raise_for_status()
            return self._project(response.json())

    def list_group_projects(self, group_id: str) -> list[GitLabProject]:
        encoded = quote(group_id, safe="")
        projects: list[GitLabProject] = []
        page = 1
        with httpx.Client(timeout=30.0, headers=self._headers()) as client:
            while True:
                response = request_with_retries(
                    client,
                    "GET",
                    f"{self.api_url}/groups/{encoded}/projects",
                    params={"include_subgroups": True, "per_page": 100, "page": page},
                    retries=self.settings.http_retries,
                    backoff_seconds=self.settings.http_retry_backoff_seconds,
                )
                response.raise_for_status()
                payload = response.json()
                projects.extend(self._project(item) for item in payload)
                if not response.headers.get("X-Next-Page"):
                    return projects
                page += 1

    def compare(self, project_id: str, old_sha: str, new_sha: str) -> list[ChangedFile]:
        encoded = quote(str(project_id), safe="")
        with httpx.Client(timeout=60.0, headers=self._headers()) as client:
            response = request_with_retries(
                client,
                "GET",
                f"{self.api_url}/projects/{encoded}/repository/compare",
                params={"from": old_sha, "to": new_sha},
                retries=self.settings.http_retries,
                backoff_seconds=self.settings.http_retry_backoff_seconds,
            )
            response.raise_for_status()
            diffs = response.json().get("diffs", [])
        changes: list[ChangedFile] = []
        for diff in diffs:
            changes.append(
                ChangedFile(
                    old_path=diff.get("old_path") or diff.get("new_path"),
                    new_path=diff.get("new_path") or diff.get("old_path"),
                    added=bool(diff.get("new_file")),
                    deleted=bool(diff.get("deleted_file")),
                    renamed=bool(diff.get("renamed_file")),
                    modified=not any(
                        [diff.get("new_file"), diff.get("deleted_file"), diff.get("renamed_file")]
                    ),
                )
            )
        return changes

    def _project(self, payload: dict) -> GitLabProject:
        return GitLabProject(
            gitlab_project_id=str(payload["id"]),
            repo_path_with_namespace=payload["path_with_namespace"],
            repo_name=payload.get("name") or payload["path"],
            repo_url=payload.get("http_url_to_repo") or payload.get("web_url") or "",
            default_branch=payload.get("default_branch"),
            description=payload.get("description"),
        )
