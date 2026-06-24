from __future__ import annotations

from code_rag.apps.retrieval.graph_expander import GraphExpander
from code_rag.config.settings import Settings
from code_rag.domain import QueryType, SearchHit


def _hit(chunk_id: str, symbol_fqn: str | None) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        score=1.0,
        repo_path_with_namespace="group/payments",
        file_path=f"{chunk_id}.py",
        line_start=1,
        line_end=3,
        language="python",
        chunk_kind="function_definition",
        symbol_name=symbol_fqn.split(".")[-1] if symbol_fqn else None,
        symbol_fqn=symbol_fqn,
        gitlab_blob_url="https://gitlab.example.com/x",
        text="code",
    )


class RecordingIndex:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], list[str]]] = []

    def neighbor_chunks(self, symbol_fqns, edge_types, filters, size):
        self.calls.append((symbol_fqns, edge_types))
        return [_hit("neighbor", "group.payments.ChargeProcessor")]


def test_graph_expander_returns_neighbors_and_marks_metadata() -> None:
    index = RecordingIndex()
    expander = GraphExpander(Settings(), index)

    neighbors = expander.expand(
        [_hit("seed", "group.payments.PaymentService")],
        QueryType.DEFINITION_LOOKUP,
        {"tenant_id": "default"},
    )

    assert [hit.chunk_id for hit in neighbors] == ["neighbor"]
    assert neighbors[0].metadata["graph_expanded"] is True
    seeded_fqns, edge_types = index.calls[0]
    assert seeded_fqns == ["group.payments.PaymentService"]
    # Definition lookups should follow call/reference/import edges.
    assert "CALLS" in edge_types


def test_graph_expander_uses_test_edges_for_test_questions() -> None:
    index = RecordingIndex()
    expander = GraphExpander(Settings(), index)

    expander.expand(
        [_hit("seed", "group.payments.PaymentService")],
        QueryType.TEST_QUESTION,
        {"tenant_id": "default"},
    )

    _, edge_types = index.calls[0]
    assert "TESTS" in edge_types


def test_graph_expander_noop_when_index_has_no_neighbor_support() -> None:
    expander = GraphExpander(Settings(), object())

    assert (
        expander.expand(
            [_hit("seed", "group.payments.PaymentService")],
            QueryType.DEFINITION_LOOKUP,
            {},
        )
        == []
    )


def test_graph_expander_skips_seeds_without_symbols() -> None:
    index = RecordingIndex()
    expander = GraphExpander(Settings(), index)

    assert expander.expand([_hit("seed", None)], QueryType.DEFINITION_LOOKUP, {}) == []
    assert index.calls == []
