from __future__ import annotations

import pytest

from code_rag.apps.retrieval.query_classifier import QueryClassifier
from code_rag.domain.enums.query_type import QueryType


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Who owns the payments service?", QueryType.OWNERSHIP_QUESTION),
        ("Where is PaymentService implemented?", QueryType.DEFINITION_LOOKUP),
        ("who calls chargeCard?", QueryType.USAGE_LOOKUP),
        ("What HTTP endpoint handles refunds?", QueryType.API_QUESTION),
        ("Which environment setting controls retries?", QueryType.CONFIG_QUESTION),
        ("Is there a test for the parser?", QueryType.TEST_QUESTION),
        ("How is this deployed with helm?", QueryType.DEPLOYMENT_QUESTION),
        ("Why does this throw an exception?", QueryType.DEBUGGING_QUESTION),
        ("What does the schema migration add?", QueryType.MIGRATION_QUESTION),
        ("How does the system fit together?", QueryType.ARCHITECTURE_QUESTION),
    ],
)
def test_classify(query: str, expected: QueryType) -> None:
    assert QueryClassifier().classify(query) == expected


def test_identifiers_extracts_and_dedupes_skipping_stopwords() -> None:
    classifier = QueryClassifier()
    identifiers = classifier.identifiers("Where is `PaymentService` and payments.api.Client used?")
    assert "PaymentService" in identifiers
    assert "payments.api.Client" in identifiers
    # "Where" is a stop word and must be excluded.
    assert "Where" not in identifiers
    # No duplicates.
    assert len(identifiers) == len(set(identifiers))


def test_identifiers_empty_for_plain_prose() -> None:
    assert QueryClassifier().identifiers("how does it all work") == []
