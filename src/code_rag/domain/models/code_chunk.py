from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from code_rag.domain.enums.chunk_kind import ChunkKind
from code_rag.domain.enums.symbol_role import SymbolRole
from code_rag.domain.time import utcnow


class CodeChunk(BaseModel):
    chunk_id: str
    tenant_id: str
    gitlab_instance_url: str
    gitlab_project_id: str
    repo_path_with_namespace: str
    repo_name: str
    repo_url: str
    team_owner: str | None = None
    business_domain: str | None = None
    service_name: str | None = None
    slack_channel: str | None = None
    jira_project: str | None = None
    service_type: str | None = None
    deployment_name: str | None = None
    branch: str
    commit_sha: str
    active_snapshot: bool = True
    file_path: str
    file_name: str
    file_extension: str
    language: str
    file_hash: str
    is_test: bool = False
    is_generated: bool = False
    is_vendor: bool = False
    is_config: bool = False
    is_migration: bool = False
    is_deprecated: bool = False
    chunk_type: str = "code"
    chunk_kind: ChunkKind
    symbol_role: SymbolRole = SymbolRole.NONE
    symbol_name: str | None = None
    symbol_fqn: str | None = None
    symbol_kind: str | None = None
    parent_symbol_fqn: str | None = None
    line_start: int
    line_end: int
    gitlab_blob_url: str
    gitlab_raw_url: str
    text: str
    text_for_embedding: str
    summary: str | None = None
    imports: list[str] = Field(default_factory=list)
    defines_symbols: list[str] = Field(default_factory=list)
    references_symbols: list[str] = Field(default_factory=list)
    calls_symbols: list[str] = Field(default_factory=list)
    called_by_symbols: list[str] = Field(default_factory=list)
    secret_findings_count: int = 0
    secret_redactions_count: int = 0
    secret_high_confidence_count: int = 0
    secret_types: list[str] = Field(default_factory=list)
    embedding_dense: list[float] = Field(default_factory=list)
    embedding_late_interaction: list[list[float]] = Field(default_factory=list)
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    embedding_created_at: datetime | None = None
    embedding_input_hash: str | None = None
    indexed_at: datetime = Field(default_factory=utcnow)
