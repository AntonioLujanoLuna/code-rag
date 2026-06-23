from __future__ import annotations

from pydantic import BaseModel

from code_rag.domain.models import ChangedFile


class IncrementalIndexRequest(BaseModel):
    project_id: str
    repo_path_with_namespace: str | None = None
    repo_name: str | None = None
    repo_url: str | None = None
    branch: str | None = None
    old_sha: str
    new_sha: str
    changes: list[ChangedFile] | None = None
