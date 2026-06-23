from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FileClass(StrEnum):
    SOURCE = "source_code"
    TEST = "test_code"
    CONFIG = "config"
    CI_CD = "ci_cd"
    DEPLOYMENT = "deployment"
    SCHEMA = "schema"
    MIGRATION = "migration"
    DOCUMENTATION = "documentation"
    GENERATED = "generated"
    VENDOR = "vendor"
    BINARY = "binary"
    LARGE_UNKNOWN = "large_unknown"
    UNKNOWN = "unknown"


class ChunkKind(StrEnum):
    FILE = "file"
    FUNCTION_DEFINITION = "function_definition"
    METHOD_DEFINITION = "method_definition"
    CLASS_DEFINITION = "class_definition"
    CONFIG_BLOCK = "config_block"
    DOCUMENTATION_SECTION = "documentation_section"
    TEST_CASE = "test_case"


class SymbolRole(StrEnum):
    DEFINITION = "definition"
    REFERENCE = "reference"
    MIXED = "mixed"
    NONE = "none"


class QueryType(StrEnum):
    DEFINITION_LOOKUP = "definition_lookup"
    USAGE_LOOKUP = "usage_lookup"
    ARCHITECTURE_QUESTION = "architecture_question"
    DEBUGGING_QUESTION = "debugging_question"
    API_QUESTION = "api_question"
    CONFIG_QUESTION = "config_question"
    TEST_QUESTION = "test_question"
    DEPLOYMENT_QUESTION = "deployment_question"
    OWNERSHIP_QUESTION = "ownership_question"
    MIGRATION_QUESTION = "migration_question"


class GitLabProject(BaseModel):
    gitlab_project_id: str
    repo_path_with_namespace: str
    repo_name: str
    repo_url: str
    default_branch: str | None = None
    description: str | None = None


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


class EdgeType(StrEnum):
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    REFERENCES = "REFERENCES"
    TESTS = "TESTS"
    CONFIGURES = "CONFIGURES"
    EXPOSES_ENDPOINT = "EXPOSES_ENDPOINT"


class CodeEdge(BaseModel):
    edge_id: str
    tenant_id: str
    branch: str
    commit_sha: str
    source_symbol_id: str | None = None
    source_symbol_fqn: str | None = None
    source_repo_project_id: str
    source_file_path: str
    source_line_start: int
    target_symbol_id: str | None = None
    target_symbol_fqn: str | None = None
    target_repo_project_id: str | None = None
    target_file_path: str | None = None
    target_line_start: int | None = None
    edge_type: EdgeType
    confidence: float = 0.5
    extraction_method: str = "static"
    indexed_at: datetime = Field(default_factory=utcnow)


class ChangedFile(BaseModel):
    old_path: str
    new_path: str
    added: bool = False
    deleted: bool = False
    renamed: bool = False
    modified: bool = False


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


class JobStatus(BaseModel):
    job_id: str
    status: str
    job_type: str
    submitted_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: IndexJobResult | None = None
    error_message: str | None = None


class PermissionRecord(BaseModel):
    user_id: str
    tenant_id: str = "default"
    accessible_project_ids: list[str]
    last_synced_at: datetime = Field(default_factory=utcnow)


class SearchRequest(BaseModel):
    query: str
    user_id: str | None = None
    allowed_project_ids: list[str] = Field(default_factory=list)
    tenant_id: str | None = None
    branch: str | None = None
    repo_path_with_namespace: str | None = None
    top_k: int = 8


class SearchHit(BaseModel):
    chunk_id: str
    score: float
    repo_path_with_namespace: str
    file_path: str
    line_start: int
    line_end: int
    language: str
    chunk_kind: str
    symbol_name: str | None = None
    symbol_fqn: str | None = None
    gitlab_blob_url: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    query_type: QueryType
    identifiers: list[str]
    hits: list[SearchHit]
    context: str


class SecretFinding(BaseModel):
    secret_type: str
    line: int
    start: int
    end: int
    confidence: str
    redacted_value: str = "[REDACTED_SECRET]"


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


class AnswerRequest(SearchRequest):
    max_context_chars: int = 12_000


class SourceCitation(BaseModel):
    index: int
    repo_path_with_namespace: str
    file_path: str
    line_start: int
    line_end: int
    url: str


class AnswerResponse(BaseModel):
    query: str
    answer: str
    grounded: bool = True
    refusal_reason: str | None = None
    source_coverage: float = 0.0
    query_type: QueryType
    identifiers: list[str]
    sources: list[SourceCitation]
    context: str


def path_language(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".java": "java",
        ".kt": "kotlin",
        ".go": "go",
        ".rs": "rust",
        ".cs": "csharp",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".c": "c",
        ".h": "c",
        ".hpp": "cpp",
        ".rb": "ruby",
        ".php": "php",
        ".scala": "scala",
        ".md": "markdown",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".json": "json",
        ".toml": "toml",
        ".xml": "xml",
        ".sql": "sql",
    }.get(suffix, suffix.lstrip(".") or "text")
