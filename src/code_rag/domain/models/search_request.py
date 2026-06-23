from __future__ import annotations

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2_000)
    user_id: str | None = None
    allowed_project_ids: list[str] = Field(default_factory=list, max_length=500)
    tenant_id: str | None = None
    branch: str | None = None
    repo_path_with_namespace: str | None = None
    repo_paths_with_namespace: list[str] = Field(default_factory=list, max_length=50)
    top_k: int = Field(default=8, ge=1, le=50)
