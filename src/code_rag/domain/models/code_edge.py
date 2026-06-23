from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from code_rag.domain.enums.edge_type import EdgeType
from code_rag.domain.time import utcnow


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
