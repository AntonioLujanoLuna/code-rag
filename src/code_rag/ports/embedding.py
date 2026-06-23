from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Protocol


class EmbeddingResult(BaseModel):
    dense: list[float] = Field(default_factory=list)
    late_interaction: list[list[float]] = Field(default_factory=list)


class EmbeddingProvider(Protocol):
    model_name: str
    dimension: int
    late_interaction_dimension: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding per input text."""

    def embed_documents(self, texts: list[str]) -> list[EmbeddingResult]:
        """Return dense and late-interaction embeddings for documents."""

    def embed_query(self, text: str) -> EmbeddingResult:
        """Return dense and late-interaction embeddings for a query."""
