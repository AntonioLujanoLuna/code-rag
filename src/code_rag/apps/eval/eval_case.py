from __future__ import annotations

from pydantic import BaseModel, Field


class EvalCase(BaseModel):
    """A single golden retrieval example.

    ``relevant`` holds any mix of chunk ids, file paths, or symbol FQNs; a hit
    counts as relevant when its chunk id, file path, or symbol FQN matches one of
    them. Matching by file path / FQN keeps a dataset stable across re-indexing,
    where content-hash chunk ids change.
    """

    query: str
    relevant: list[str] = Field(default_factory=list)
    user_id: str | None = None
    allowed_project_ids: list[str] = Field(default_factory=list)
    branch: str | None = None
    repo_path_with_namespace: str | None = None


class EvalDataset(BaseModel):
    cases: list[EvalCase] = Field(default_factory=list)
