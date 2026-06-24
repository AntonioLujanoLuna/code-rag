from __future__ import annotations

from code_rag.apps.retrieval.reranker import Reranker
from code_rag.config.settings import Settings
from code_rag.domain.enums.query_type import QueryType
from tests.conftest import make_hit


def test_identifier_match_boosts_hit_above_higher_base_score() -> None:
    settings = Settings(rerank_identifier_boost=5.0)
    matching = make_hit("match", score=1.0, symbol_name="PaymentService")
    other = make_hit("other", score=1.4, symbol_name="Unrelated", file_path="other.py")

    ranked = Reranker(settings).rerank(
        [other, matching], QueryType.DEFINITION_LOOKUP, ["PaymentService"], []
    )

    assert ranked[0].chunk_id == "match"


def test_definition_role_boost_applied_for_definition_lookup() -> None:
    settings = Settings(rerank_identifier_boost=0.0, rerank_definition_boost=10.0)
    definition = make_hit("def", score=0.0, symbol_role="definition")
    reference = make_hit("ref", score=0.5, symbol_role="none", file_path="ref.py")

    ranked = Reranker(settings).rerank([reference, definition], QueryType.DEFINITION_LOOKUP, [], [])

    assert ranked[0].chunk_id == "def"


def test_late_interaction_similarity_contributes_to_score() -> None:
    settings = Settings(
        rerank_identifier_boost=0.0,
        rerank_definition_boost=0.0,
        rerank_late_interaction_weight=1.0,
    )
    aligned = make_hit(
        "aligned",
        score=0.0,
        symbol_role="none",
        metadata={"embedding_late_interaction": [[1.0, 0.0]]},
    )
    orthogonal = make_hit(
        "orthogonal",
        score=0.0,
        symbol_role="none",
        file_path="o.py",
        metadata={"embedding_late_interaction": [[0.0, 1.0]]},
    )

    ranked = Reranker(settings).rerank(
        [orthogonal, aligned],
        QueryType.ARCHITECTURE_QUESTION,
        [],
        query_late_embedding=[[1.0, 0.0]],
    )

    assert ranked[0].chunk_id == "aligned"
