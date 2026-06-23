from __future__ import annotations

from code_rag.adapters.embeddings.hash_embedding_provider import HashEmbeddingProvider
from code_rag.adapters.embeddings.http_embedding_provider import (
    HttpLateInteractionEmbeddingProvider,
)
from code_rag.config.settings import Settings


def test_hash_embedding_is_deterministic_and_normalized() -> None:
    provider = HashEmbeddingProvider(dimension=16, late_interaction_dimension=8)
    first = provider.embed_query("PaymentService authorize")
    second = provider.embed_query("PaymentService authorize")

    assert first.dense == second.dense
    assert len(first.dense) == 16
    norm = sum(value * value for value in first.dense) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_http_provider_parses_batch_results() -> None:
    provider = HttpLateInteractionEmbeddingProvider(Settings(embedding_dimension=3))
    items = provider._batch_items({"results": [{"dense": [1, 2, 3]}, {"embedding": [4, 5, 6]}]}, 2)
    assert len(items) == 2

    result = provider._to_result({"dense": [1.0, 2.0, 3.0], "late_interaction": [[1.0]]}, "text")
    assert result.dense == [1.0, 2.0, 3.0]
    assert result.late_interaction == [[1.0]]


def test_http_provider_falls_back_without_service_url() -> None:
    provider = HttpLateInteractionEmbeddingProvider(Settings(embedding_service_url=""))
    results = provider.embed_documents(["alpha", "beta"])
    assert len(results) == 2
    assert results[0].dense
