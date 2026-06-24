from __future__ import annotations

from code_rag.apps.retrieval.query_expander import QueryExpander
from code_rag.config.settings import Settings


def _expander(enabled: bool = True) -> QueryExpander:
    return QueryExpander(Settings(query_expansion_enabled=enabled))


def test_disabled_returns_query_unchanged() -> None:
    assert _expander(enabled=False).expand("auth") == "auth"


def test_long_queries_are_not_expanded() -> None:
    query = "where is the payment service implemented"
    assert _expander().expand(query) == query


def test_camelcase_is_split_and_appended() -> None:
    expanded = _expander().expand("getUserById")
    assert expanded.startswith("getUserById ")
    for word in ("get", "user", "by", "id"):
        assert word in expanded.split()


def test_snake_case_and_synonyms_are_added() -> None:
    expanded = _expander().expand("auth db")
    tokens = expanded.split()
    # synonyms for both abbreviations
    assert "authentication" in tokens
    assert "authorization" in tokens
    assert "database" in tokens


def test_no_additions_returns_original() -> None:
    # A short plain word with no identifier split and no synonym entry.
    assert _expander().expand("payment") == "payment"
