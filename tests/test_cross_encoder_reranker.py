from __future__ import annotations

from code_rag.adapters.rerank.http_cross_encoder_reranker import HttpCrossEncoderReranker
from code_rag.apps.retrieval.reranker import Reranker
from code_rag.config.settings import Settings
from code_rag.domain import QueryType, SearchHit


def _hit(chunk_id: str, score: float, text: str) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        score=score,
        repo_path_with_namespace="group/payments",
        file_path=f"{chunk_id}.py",
        line_start=1,
        line_end=3,
        language="python",
        chunk_kind="function_definition",
        symbol_name=None,
        symbol_fqn=None,
        gitlab_blob_url="https://gitlab.example.com/x",
        text=text,
    )


class StubCrossEncoder:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores

    @property
    def enabled(self) -> bool:
        return True

    def score(self, query: str, documents: list[str]) -> list[float]:
        return self.scores[: len(documents)]


def test_disabled_reranker_returns_empty_scores() -> None:
    reranker = HttpCrossEncoderReranker(Settings(rerank_service_url=""))

    assert reranker.enabled is False
    assert reranker.score("q", ["doc"]) == []


def test_parses_various_score_shapes() -> None:
    reranker = HttpCrossEncoderReranker(Settings(rerank_service_url="http://x"))

    assert reranker._scores([0.1, 0.2]) == [0.1, 0.2]
    assert reranker._scores({"scores": [0.3, 0.4]}) == [0.3, 0.4]
    assert reranker._scores({"results": [{"score": 0.5}, {"relevance": 0.6}]}) == [0.5, 0.6]
    assert reranker._scores("nonsense") == []


def test_cross_encoder_reorders_hits() -> None:
    settings = Settings(rerank_service_url="http://x", rerank_cross_encoder_weight=5.0)
    # Heuristic order would keep A first; the cross-encoder strongly prefers B.
    cross_encoder = StubCrossEncoder([0.0, 1.0])
    reranker = Reranker(settings, cross_encoder=cross_encoder)
    hits = [_hit("A", 1.0, "alpha"), _hit("B", 0.9, "beta")]

    ranked = reranker.rerank(hits, QueryType.ARCHITECTURE_QUESTION, [], [], "q")

    assert ranked[0].chunk_id == "B"
    assert ranked[0].metadata["cross_encoder_score"] == 1.0


def test_reranker_without_cross_encoder_uses_heuristics() -> None:
    reranker = Reranker(Settings())
    hits = [_hit("A", 0.5, "alpha"), _hit("B", 1.0, "beta")]

    ranked = reranker.rerank(hits, QueryType.ARCHITECTURE_QUESTION, [], [], "q")

    assert ranked[0].chunk_id == "B"
