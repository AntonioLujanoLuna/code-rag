from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from code_rag.domain.time import utcnow


class CodeSymbol(BaseModel):
    symbol_id: str
    tenant_id: str
    gitlab_project_id: str
    repo_path_with_namespace: str
    branch: str
    commit_sha: str
    language: str
    symbol_name: str
    symbol_fqn: str
    symbol_kind: str
    visibility: str | None = None
    exported: bool = False
    definition_file_path: str
    definition_line_start: int
    definition_line_end: int
    definition_chunk_id: str
    definition_gitlab_url: str
    parent_symbol_fqn: str | None = None
    package_name: str | None = None
    module_path: str | None = None
    docstring: str | None = None
    signature: str | None = None
    annotations: list[str] = Field(default_factory=list)
    decorators: list[str] = Field(default_factory=list)
    referenced_by_count: int = 0
    called_by_count: int = 0
    tested_by_count: int = 0
    indexed_at: datetime = Field(default_factory=utcnow)
