from __future__ import annotations

import os
import uuid

import pytest

from code_rag.adapters.elasticsearch.index import ElasticsearchCodeIndex
from code_rag.config.settings import Settings
from tests.fixtures.seed_eval_index import eval_documents

pytestmark = pytest.mark.skipif(
    not os.getenv("CODE_RAG_TEST_ELASTICSEARCH_URL"),
    reason="Set CODE_RAG_TEST_ELASTICSEARCH_URL to run Elasticsearch integration tests.",
)


def test_elasticsearch_mapping_and_retrieval_roundtrip() -> None:
    settings = Settings(
        elasticsearch_url=os.environ["CODE_RAG_TEST_ELASTICSEARCH_URL"],
        index_prefix=f"test-{uuid.uuid4().hex}-",
        allow_request_supplied_permissions=True,
    )
    index = ElasticsearchCodeIndex(settings)
    index.ensure_indices()
    metadata, chunk, symbol = eval_documents(settings)

    index.replace_file(metadata, [chunk], [symbol], [])
    index.client.indices.refresh(index=index.chunks_index)
    index.client.indices.refresh(index=index.symbols_index)

    filters = {
        "tenant_id": settings.tenant_id,
        "branch": settings.branch,
        "allowed_project_ids": ["123"],
        "repo_paths_with_namespace": ["group/payments"],
    }
    lexical_hits = index.lexical_search("PaymentService implemented", filters, 5)
    vector_hits = index.vector_search(chunk.embedding_dense, filters, 5)
    symbol_hits = index.symbol_search(["PaymentService"], filters, 5)

    assert lexical_hits[0].chunk_id == "eval-payment-service"
    assert vector_hits[0].chunk_id == "eval-payment-service"
    assert symbol_hits[0].chunk_id == "eval-payment-service"
