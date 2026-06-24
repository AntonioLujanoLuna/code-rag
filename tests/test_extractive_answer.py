from __future__ import annotations

from code_rag.adapters.answer.extractive_answer_provider import ExtractiveAnswerProvider
from code_rag.config.settings import Settings
from tests.conftest import make_hit, make_response


def test_answer_draft_lists_grounded_sources() -> None:
    provider = ExtractiveAnswerProvider(Settings())
    response = make_response([make_hit("a"), make_hit("b", file_path="other.py")])

    draft = provider.answer(response, max_context_chars=1000)

    assert "Grounded answer draft" in draft
    assert "group/payments/service.py:1-3 `PaymentService`" in draft
    assert "Source [2]" in draft
    assert provider.is_grounded(response) is True


def test_answer_returns_refusal_when_no_hits() -> None:
    provider = ExtractiveAnswerProvider(Settings())
    response = make_response([])

    draft = provider.answer(response, max_context_chars=1000)

    assert "could not find" in draft
    assert provider.is_grounded(response) is False
    assert provider.refusal_reason(response) is not None
    assert provider.source_coverage(response) == 0.0
