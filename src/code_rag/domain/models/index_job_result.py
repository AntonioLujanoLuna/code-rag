from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class IndexJobResult(BaseModel):
    job_id: str
    job_type: str
    gitlab_project_id: str
    repo_path_with_namespace: str
    branch: str
    old_sha: str | None = None
    new_sha: str
    status: str
    started_at: datetime
    finished_at: datetime
    files_seen: int = 0
    files_added: int = 0
    files_modified: int = 0
    files_deleted: int = 0
    files_renamed: int = 0
    chunks_added: int = 0
    chunks_deleted: int = 0
    error_message: str | None = None
