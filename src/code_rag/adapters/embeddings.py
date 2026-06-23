from __future__ import annotations

import hashlib
import math
import re

import httpx

from code_rag.adapters.http import request_with_retries
from code_rag.ports.embedding import EmbeddingResult
from code_rag.settings import Settings


class HashEmbeddingProvider:
    """Deterministic local embedding backend for development and tests."""

    model_name = "hash-embedding-v1"

    def __init__(self, dimension: int = 384, late_interaction_dimension: int = 128) -> None:
        self.dimension = dimension
        self.late_interaction_dimension = late_interaction_dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [result.dense for result in self.embed_documents(texts)]

    def embed_documents(self, texts: list[str]) -> list[EmbeddingResult]:
        return [self._embed_result(text) for text in texts]

    def embed_query(self, text: str) -> EmbeddingResult:
        return self._embed_result(text)

    def _embed_result(self, text: str) -> EmbeddingResult:
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+", text.lower())
        dense = self._embed_tokens(tokens, self.dimension)
        late = [self._embed_tokens([token], self.late_interaction_dimension) for token in tokens[:128]]
        return EmbeddingResult(dense=dense, late_interaction=late)

    def _embed_tokens(self, tokens: list[str], dimension: int) -> list[float]:
        vector = [0.0] * self.dimension
        if dimension != self.dimension:
            vector = [0.0] * dimension
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            bucket = int.from_bytes(digest[:4], "big") % dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class HttpLateInteractionEmbeddingProvider:
    """Adapter for an embedding service that accepts a string and returns late embeddings."""

    def __init__(self, settings: Settings, fallback: HashEmbeddingProvider | None = None) -> None:
        self.settings = settings
        self.model_name = settings.embedding_model
        self.dimension = settings.embedding_dimension
        self.late_interaction_dimension = settings.late_interaction_dimension
        self.fallback = fallback or HashEmbeddingProvider(
            settings.embedding_dimension, settings.late_interaction_dimension
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [result.dense for result in self.embed_documents(texts)]

    def embed_documents(self, texts: list[str]) -> list[EmbeddingResult]:
        if not self.settings.embedding_service_url:
            return self.fallback.embed_documents(texts)
        return [self._embed_one(text, "document") for text in texts]

    def embed_query(self, text: str) -> EmbeddingResult:
        if not self.settings.embedding_service_url:
            return self.fallback.embed_query(text)
        return self._embed_one(text, "query")

    def _embed_one(self, text: str, input_type: str) -> EmbeddingResult:
        payload = {"text": text, "input_type": input_type}
        with httpx.Client(timeout=self.settings.embedding_service_timeout_seconds) as client:
            response = request_with_retries(
                client,
                "POST",
                self.settings.embedding_service_url,
                json=payload,
                retries=self.settings.http_retries,
                backoff_seconds=self.settings.http_retry_backoff_seconds,
            )
            response.raise_for_status()
            data = response.json()
        late = data.get("late_interaction") or data.get("late_interaction_embeddings") or data.get("embeddings")
        dense = data.get("dense") or data.get("embedding") or []
        if not late:
            late = self.fallback.embed_query(text).late_interaction
        if not dense:
            dense = self._mean_pool(late)
        return EmbeddingResult(dense=dense, late_interaction=late)

    def _mean_pool(self, vectors: list[list[float]]) -> list[float]:
        if not vectors:
            return [0.0] * self.dimension
        dim = len(vectors[0])
        pooled = [0.0] * dim
        for vector in vectors:
            for index, value in enumerate(vector):
                pooled[index] += value
        pooled = [value / len(vectors) for value in pooled]
        if len(pooled) == self.dimension:
            return pooled
        if len(pooled) > self.dimension:
            return pooled[: self.dimension]
        return pooled + [0.0] * (self.dimension - len(pooled))
