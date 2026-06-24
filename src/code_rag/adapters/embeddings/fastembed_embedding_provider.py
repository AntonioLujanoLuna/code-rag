from __future__ import annotations

from collections.abc import Iterable

from code_rag.adapters.embeddings.hash_embedding_provider import HashEmbeddingProvider
from code_rag.config.settings import Settings
from code_rag.domain.models import EmbeddingResult


class FastEmbedEmbeddingProvider:
    """Local semantic embedding backend powered by the optional fastembed extra."""

    def __init__(self, settings: Settings, fallback: HashEmbeddingProvider | None = None) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "Install code-rag[local-embeddings] to use CODE_RAG_EMBEDDING_BACKEND=fastembed"
            ) from exc
        self.settings = settings
        self.model_name = settings.fastembed_model
        self.dimension = settings.embedding_dimension
        self.late_interaction_dimension = settings.late_interaction_dimension
        self.fallback = fallback or HashEmbeddingProvider(
            settings.embedding_dimension, settings.late_interaction_dimension
        )
        self.model = TextEmbedding(model_name=settings.fastembed_model)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [result.dense for result in self.embed_documents(texts)]

    def embed_documents(self, texts: list[str]) -> list[EmbeddingResult]:
        dense_vectors = self._embed_dense(texts)
        fallback = self.fallback.embed_documents(texts)
        return [
            EmbeddingResult(dense=dense, late_interaction=late.late_interaction)
            for dense, late in zip(dense_vectors, fallback, strict=True)
        ]

    def embed_query(self, text: str) -> EmbeddingResult:
        return self.embed_documents([text])[0]

    async def aembed_documents(self, texts: list[str]) -> list[EmbeddingResult]:
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> EmbeddingResult:
        return self.embed_query(text)

    def _embed_dense(self, texts: Iterable[str]) -> list[list[float]]:
        vectors = []
        for vector in self.model.embed(list(texts)):
            dense = [float(value) for value in vector]
            if len(dense) > self.dimension:
                dense = dense[: self.dimension]
            elif len(dense) < self.dimension:
                dense = dense + [0.0] * (self.dimension - len(dense))
            vectors.append(dense)
        return vectors
