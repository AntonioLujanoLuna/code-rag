from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from code_rag.domain.time import utcnow


class CodeCommunity(BaseModel):
    """A cluster of densely connected symbols in the code graph.

    Communities are detected per repository/branch at index time by clustering
    the symbol/edge graph. Each community carries an extractive summary so that
    global, architecture-level questions can retrieve a cluster overview instead
    of relying solely on chunk-level retrieval.
    """

    community_id: str
    tenant_id: str
    gitlab_project_id: str
    repo_path_with_namespace: str
    branch: str
    commit_sha: str
    label: str
    summary: str
    size: int
    dominant_language: str | None = None
    member_symbol_fqns: list[str] = Field(default_factory=list)
    member_chunk_ids: list[str] = Field(default_factory=list)
    member_file_paths: list[str] = Field(default_factory=list)
    representative_chunk_id: str | None = None
    representative_gitlab_url: str | None = None
    edge_count: int = 0
    embedding_dense: list[float] = Field(default_factory=list)
    indexed_at: datetime = Field(default_factory=utcnow)
