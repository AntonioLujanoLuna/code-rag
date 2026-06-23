from __future__ import annotations

from pydantic import BaseModel

from code_rag.domain.enums.file_class import FileClass


class FileMetadata(BaseModel):
    tenant_id: str
    gitlab_instance_url: str
    gitlab_project_id: str
    repo_path_with_namespace: str
    repo_name: str
    repo_url: str
    branch: str
    commit_sha: str
    file_path: str
    file_name: str
    file_extension: str
    language: str
    file_hash: str
    size_bytes: int
    line_count: int
    file_class: FileClass
    is_test: bool = False
    is_generated: bool = False
    is_vendor: bool = False
    is_config: bool = False
    is_migration: bool = False
    is_binary: bool = False
    is_large: bool = False
    team_owner: str | None = None
    business_domain: str | None = None
    service_name: str | None = None
    slack_channel: str | None = None
    jira_project: str | None = None
    service_type: str | None = None
    deployment_name: str | None = None
    secret_findings_count: int = 0
    secret_redactions_count: int = 0
    secret_high_confidence_count: int = 0
