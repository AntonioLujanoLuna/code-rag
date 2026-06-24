from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from code_rag.adapters.embeddings.hash_embedding_provider import HashEmbeddingProvider
from code_rag.adapters.http.retries import request_with_retries
from code_rag.config.settings import Settings
from code_rag.domain.models import EmbeddingResult


class HttpLateInteractionEmbeddingProvider:
    """Adapter for a remote embedding service.

    Documents are embedded in a single batched request (``{"texts": [...]}``)
    instead of one HTTP round-trip per chunk. The service may answer with a
    ``results``/``embeddings`` list, or — for a single text — the legacy
    object shape, both of which are handled here.
    """

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
        if not texts:
            return []
        if not self.settings.embedding_service_url:
            return self.fallback.embed_documents(texts)
        batch_size = self.settings.max_embedding_batch_size
        if batch_size > 0 and len(texts) > batch_size:
            return self._parallel_embed(texts, batch_size)
        return self._embed_batch(texts, "document")

    def embed_query(self, text: str) -> EmbeddingResult:
        if not self.settings.embedding_service_url:
            return self.fallback.embed_query(text)
        return self._embed_batch([text], "query")[0]

    async def aembed_documents(self, texts: list[str]) -> list[EmbeddingResult]:
        return await asyncio.to_thread(self.embed_documents, texts)

    async def aembed_query(self, text: str) -> EmbeddingResult:
        return await asyncio.to_thread(self.embed_query, text)

    def _parallel_embed(self, texts: list[str], batch_size: int) -> list[EmbeddingResult]:
        batches = [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]
        results: list[list[EmbeddingResult]] = [[] for _ in batches]
        workers = min(len(batches), 8)
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="code-rag-embed") as pool:
            future_to_index = {
                pool.submit(self._embed_batch, batch, "document"): idx
                for idx, batch in enumerate(batches)
            }
            for future in as_completed(future_to_index):
                results[future_to_index[future]] = future.result()
        return [item for batch_results in results for item in batch_results]

    def _embed_batch(self, texts: list[str], input_type: str) -> list[EmbeddingResult]:
        payload = {"texts": texts, "input_type": input_type}
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
        items = self._batch_items(data, len(texts))
        return [self._to_result(item, texts[index]) for index, item in enumerate(items)]

    def _batch_items(self, data: object, count: int) -> list[dict]:
        if isinstance(data, list):
            return [item if isinstance(item, dict) else {} for item in data]
        if isinstance(data, dict):
            results = data.get("results") or data.get("data")
            if isinstance(results, list):
                return [item if isinstance(item, dict) else {} for item in results]
            # Single-object response (legacy single-text contract).
            return [data] * count if count == 1 else [data for _ in range(count)]
        return [{} for _ in range(count)]

    def _to_result(self, item: dict, text: str) -> EmbeddingResult:
        late = (
            item.get("late_interaction")
            or item.get("late_interaction_embeddings")
            or item.get("embeddings")
        )
        dense = item.get("dense") or item.get("embedding") or []
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
