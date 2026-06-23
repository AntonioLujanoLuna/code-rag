from __future__ import annotations

from code_rag.adapters.answer.extractive_answer_provider import ExtractiveAnswerProvider
from code_rag.config.settings import Settings
from code_rag.domain import QueryType, SearchHit, SearchResponse


def test_answer_provider_refuses_without_evidence() -> None:
    provider = ExtractiveAnswerProvider(Settings())
    response = SearchResponse(
        query="How does PaymentService work?",
        query_type=QueryType.ARCHITECTURE_QUESTION,
        identifiers=["PaymentService"],
        hits=[],
        context="",
    )

    assert not provider.is_grounded(response)
    assert "could not find" in provider.answer(response, 12000)


def test_answer_provider_requires_configured_source_count() -> None:
    provider = ExtractiveAnswerProvider(Settings(min_answer_sources=2))
    response = SearchResponse(
        query="Where is PaymentService?",
        query_type=QueryType.DEFINITION_LOOKUP,
        identifiers=["PaymentService"],
        hits=[hit()],
        context="context",
    )

    assert provider.refusal_reason(response)
    assert not provider.is_grounded(response)


def hit() -> SearchHit:
    return SearchHit(
        chunk_id="c1",
        score=1.0,
        repo_path_with_namespace="group/payments",
        file_path="service.py",
        line_start=1,
        line_end=10,
        language="python",
        chunk_kind="class_definition",
        symbol_name="PaymentService",
        symbol_fqn="group.payments.PaymentService",
        gitlab_blob_url="https://gitlab.example.com/group/payments/-/blob/abc/service.py#L1-L10",
        text="Repository: group/payments\nCode:\nclass PaymentService: ...",
    )
