from __future__ import annotations

import hashlib
import re

import numpy as np

from code_rag.domain.models import EmbeddingResult


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

    async def aembed_documents(self, texts: list[str]) -> list[EmbeddingResult]:
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> EmbeddingResult:
        return self.embed_query(text)

    def _embed_result(self, text: str) -> EmbeddingResult:
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+", text.lower())
        dense = self._embed_tokens(tokens, self.dimension)
        late = [
            self._embed_tokens([token], self.late_interaction_dimension) for token in tokens[:128]
        ]
        return EmbeddingResult(dense=dense, late_interaction=late)

    def _embed_tokens(self, tokens: list[str], dimension: int) -> list[float]:
        vector: np.ndarray = np.zeros(dimension, dtype=np.float64)
        if not tokens:
            return vector.tolist()
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            bucket = int.from_bytes(digest[:4], "big") % dimension
            vector[bucket] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = float(np.linalg.norm(vector)) or 1.0
        return (vector / norm).tolist()
