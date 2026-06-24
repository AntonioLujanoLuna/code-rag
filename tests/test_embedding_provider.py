from __future__ import annotations

from code_rag.adapters.embeddings.http_embedding_provider import (
    HttpLateInteractionEmbeddingProvider,
)
from code_rag.config.settings import Settings


def _provider(**kwargs) -> HttpLateInteractionEmbeddingProvider:
    # No embedding_service_url => the deterministic fallback is used.
    return HttpLateInteractionEmbeddingProvider(Settings(embedding_dimension=8, **kwargs))


def test_empty_input_returns_empty_list() -> None:
    assert _provider().embed_documents([]) == []


def test_falls_back_to_local_provider_without_service_url() -> None:
    provider = _provider()
    results = provider.embed_documents(["alpha", "beta"])
    assert len(results) == 2
    assert all(len(r.dense) == 8 for r in results)
    # embed_query also routes to the fallback.
    assert len(provider.embed_query("alpha").dense) == 8


def test_embed_texts_returns_dense_vectors() -> None:
    vectors = _provider().embed_texts(["alpha"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 8


def test_batch_items_handles_list_dict_and_garbage() -> None:
    provider = _provider()
    # Top-level list.
    assert provider._batch_items([{"dense": [1.0]}, "junk"], 2) == [{"dense": [1.0]}, {}]
    # Wrapped under "results".
    assert provider._batch_items({"results": [{"dense": [2.0]}]}, 1) == [{"dense": [2.0]}]
    # Single legacy object echoed for each text.
    single = provider._batch_items({"dense": [3.0]}, 2)
    assert single == [{"dense": [3.0]}, {"dense": [3.0]}]
    # Unparseable payload yields empty dicts.
    assert provider._batch_items(42, 2) == [{}, {}]


def test_to_result_uses_dense_and_late_interaction_when_present() -> None:
    provider = _provider()
    result = provider._to_result({"dense": [1.0, 2.0], "late_interaction": [[0.5, 0.5]]}, "alpha")
    assert result.dense == [1.0, 2.0]
    assert result.late_interaction == [[0.5, 0.5]]


def test_to_result_mean_pools_dense_from_late_interaction_when_missing() -> None:
    provider = _provider()
    result = provider._to_result({"late_interaction": [[2.0, 4.0], [4.0, 8.0]]}, "alpha")
    # Mean pooled to (3.0, 6.0), then right-padded to the configured dimension (8).
    assert result.dense[:2] == [3.0, 6.0]
    assert len(result.dense) == 8


def test_mean_pool_empty_returns_zero_vector() -> None:
    provider = _provider()
    assert provider._mean_pool([]) == [0.0] * 8


def test_mean_pool_truncates_oversized_vectors() -> None:
    provider = _provider()
    pooled = provider._mean_pool([[float(i) for i in range(12)]])
    assert len(pooled) == 8
