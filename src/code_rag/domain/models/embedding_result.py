from __future__ import annotations

from pydantic import BaseModel, Field


class EmbeddingResult(BaseModel):
    dense: list[float] = Field(default_factory=list)
    late_interaction: list[list[float]] = Field(default_factory=list)
