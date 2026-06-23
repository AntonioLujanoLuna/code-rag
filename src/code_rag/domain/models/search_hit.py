from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
