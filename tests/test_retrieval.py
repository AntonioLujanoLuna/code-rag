from __future__ import annotations

from code_rag.adapters.embeddings import HashEmbeddingProvider
from code_rag.application.retrieval import QueryClassifier, RetrievalService
from code_rag.models import QueryType, SearchHit, SearchRequest
from code_rag.settings import Settings


class FakeIndex:
    def __init__(self) -> None:
        self.filters = []

    def lexical_search(self, query: str, filters: dict, size: int) -> list[SearchHit]:
        self.filters.append(filters)
        return [
            hit("lex", 2.0, "consumer.py", "reference", "Consumer"),
            hit("def", 1.0, "service.py", "definition", "PaymentService"),
        ]

    def vector_search(self, vector: list[float], filters: dict, size: int) -> list[SearchHit]:
        self.filters.append(filters)
        return [hit("vec", 1.0, "README.md", "none", None)]

    def symbol_search(self, identifiers: list[str], filters: dict, size: int) -> list[SearchHit]:
        self.filters.append(filters)
        return [hit("def", 10.0, "service.py", "definition", "PaymentService")]

    def edge_search(self, identifiers: list[str], filters: dict, size: int) -> list[SearchHit]:
        self.filters.append(filters)
        edge_hit = hit("edge", 1.5, "caller.py", "reference", "PaymentService")
        edge_hit.metadata["edge_match"] = True
        return [edge_hit]


def test_query_classifier_detects_definition_lookup() -> None:
    classifier = QueryClassifier()

    assert classifier.classify("Where is PaymentService implemented?") == QueryType.DEFINITION_LOOKUP
    assert classifier.identifiers("Where is PaymentService implemented?") == ["PaymentService"]


def test_retrieval_applies_permission_filters_and_boosts_definitions() -> None:
    index = FakeIndex()
    service = RetrievalService(Settings(), index, HashEmbeddingProvider(16))

    response = service.search(
        SearchRequest(query="Where is PaymentService implemented?", allowed_project_ids=["123"])
    )

    assert response.hits[0].chunk_id == "def"
    assert response.query_type == QueryType.DEFINITION_LOOKUP
    assert all(filters["allowed_project_ids"] == ["123"] for filters in index.filters)
    assert all(filters["branch"] == "develop" for filters in index.filters)
    assert "Source:" in response.context


def hit(
    chunk_id: str,
    score: float,
    file_path: str,
    symbol_role: str,
    symbol_name: str | None,
) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        score=score,
        repo_path_with_namespace="group/payments",
        file_path=file_path,
        line_start=1,
        line_end=3,
        language="python",
        chunk_kind="function_definition",
        symbol_name=symbol_name,
        symbol_fqn=f"group.payments.{symbol_name}" if symbol_name else None,
        gitlab_blob_url=f"https://gitlab.example.com/group/payments/-/blob/abc/{file_path}#L1-L3",
        text="Repository: group/payments\nCode:\npass",
        metadata={"symbol_role": symbol_role, "branch": "develop", "gitlab_project_id": "123"},
    )
