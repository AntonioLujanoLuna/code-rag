from __future__ import annotations

from typing import Protocol

from code_rag.domain.models import EmbeddingResult


class EmbeddingProvider(Protocol):
    model_name: str
    dimension: int
    late_interaction_dimension: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one dense embedding per input text."""

    def embed_documents(self, texts: list[str]) -> list[EmbeddingResult]:
        """Return dense and late-interaction embeddings for documents."""

    def embed_query(self, text: str) -> EmbeddingResult:
        """Return dense and late-interaction embeddings for a query."""
