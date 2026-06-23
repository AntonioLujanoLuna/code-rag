from __future__ import annotations

import re

from code_rag.domain.enums.query_type import QueryType

IDENTIFIER_RE = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9_]+|[a-zA-Z_][\w]*(?:\.[a-zA-Z_][\w]*)+|/[A-Za-z0-9_./-]+|[A-Z0-9_]{3,})\b"
)
IDENTIFIER_STOP_WORDS = {
    "A",
    "An",
    "And",
    "Are",
    "Can",
    "Does",
    "How",
    "Is",
    "The",
    "What",
    "When",
    "Where",
    "Which",
    "Who",
    "Why",
}


class QueryClassifier:
    def classify(self, query: str) -> QueryType:
        q = query.lower()
        if any(term in q for term in ("owner", "who owns", "team", "maintainer")):
            return QueryType.OWNERSHIP_QUESTION
        if any(term in q for term in ("where is", "implemented", "defined", "source")):
            return QueryType.DEFINITION_LOOKUP
        if any(
            term in q for term in ("who calls", "where used", "references", "uses ", "called by")
        ):
            return QueryType.USAGE_LOOKUP
        if any(term in q for term in ("endpoint", "route", "api", "http")):
            return QueryType.API_QUESTION
        if any(term in q for term in ("config", "setting", "environment", "env var", "property")):
            return QueryType.CONFIG_QUESTION
        if any(term in q for term in ("test", "spec", "coverage")):
            return QueryType.TEST_QUESTION
        if any(term in q for term in ("deploy", "helm", "kubernetes", "docker")):
            return QueryType.DEPLOYMENT_QUESTION
        if any(term in q for term in ("debug", "error", "exception", "traceback", "bug")):
            return QueryType.DEBUGGING_QUESTION
        if any(term in q for term in ("migration", "schema", "table")):
            return QueryType.MIGRATION_QUESTION
        return QueryType.ARCHITECTURE_QUESTION

    def identifiers(self, query: str) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for match in IDENTIFIER_RE.findall(query):
            value = match.strip("`'\"")
            if value in IDENTIFIER_STOP_WORDS:
                continue
            if value and value not in seen:
                seen.add(value)
                result.append(value)
        return result
