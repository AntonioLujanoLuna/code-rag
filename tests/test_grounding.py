from __future__ import annotations

from code_rag.adapters.answer import grounding
from code_rag.config.settings import Settings
from tests.conftest import make_hit, make_response


def test_source_coverage_ratio() -> None:
    hits = [make_hit("a"), make_hit("b", gitlab_blob_url="")]
    response = make_response(hits)
    assert grounding.source_coverage(response) == 0.5


def test_source_coverage_zero_without_hits() -> None:
    assert grounding.source_coverage(make_response([])) == 0.0


def test_refusal_when_no_hits() -> None:
    reason = grounding.refusal_reason(Settings(), make_response([]))
    assert reason and "could not find" in reason


def test_refusal_when_too_few_sources() -> None:
    settings = Settings(min_answer_sources=3)
    reason = grounding.refusal_reason(settings, make_response([make_hit("a")]))
    assert reason and "too few" in reason


def test_refusal_when_below_score_threshold() -> None:
    settings = Settings(min_answer_score=5.0)
    reason = grounding.refusal_reason(settings, make_response([make_hit("a", score=1.0)]))
    assert reason and "relevance threshold" in reason


def test_refusal_when_no_source_links() -> None:
    settings = Settings(min_answer_sources=1, min_answer_score=0.0)
    response = make_response([make_hit("a", score=1.0, gitlab_blob_url="")])
    reason = grounding.refusal_reason(settings, response)
    assert reason and "source links" in reason


def test_no_refusal_when_evidence_is_sufficient() -> None:
    assert grounding.refusal_reason(Settings(), make_response()) is None
