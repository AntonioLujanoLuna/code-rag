from __future__ import annotations

import re

from code_rag.config.settings import Settings

_SYNONYMS: dict[str, list[str]] = {
    "auth": ["authentication", "authorization"],
    "authn": ["authentication"],
    "authz": ["authorization"],
    "config": ["configuration", "settings"],
    "db": ["database"],
    "repo": ["repository"],
    "svc": ["service"],
    "mgr": ["manager"],
    "util": ["utility", "helper"],
    "utils": ["utilities", "helpers"],
    "msg": ["message"],
    "err": ["error", "exception"],
    "req": ["request"],
    "res": ["response"],
    "ctx": ["context"],
    "impl": ["implementation"],
    "handler": ["controller", "processor"],
    "dto": ["data transfer object"],
    "orm": ["object relational mapping"],
    "api": ["application programming interface"],
    "sdk": ["software development kit"],
    "cli": ["command line interface"],
}

# Minimum token count below which expansion is applied.
_EXPANSION_THRESHOLD = 4


class QueryExpander:
    """Expand short queries for the BM25 retrieval leg.

    For queries with fewer than ``_EXPANSION_THRESHOLD`` whitespace-delimited
    tokens, this class appends extra terms derived from:

    1. CamelCase splitting (``getUserById`` → ``get user by id``)
    2. snake_case/kebab-case splitting (``user_service`` → ``user service``)
    3. A small synonym table for common abbreviations
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def expand(self, query: str) -> str:
        if not self.settings.query_expansion_enabled:
            return query
        tokens = query.split()
        if len(tokens) >= _EXPANSION_THRESHOLD:
            return query
        extra: list[str] = []
        for token in tokens:
            extra.extend(self._split_identifier(token))
            extra.extend(_SYNONYMS.get(token.lower(), []))
        if not extra:
            return query
        seen: set[str] = set(t.lower() for t in tokens)
        additions = [t for t in extra if t.lower() not in seen]
        if not additions:
            return query
        return query + " " + " ".join(additions)

    @staticmethod
    def _split_identifier(token: str) -> list[str]:
        words: list[str] = []
        # CamelCase → individual words
        words.extend(w.lower() for w in re.sub(r"([A-Z])", r" \1", token).split() if len(w) > 1)
        # snake_case / kebab-case → individual words
        words.extend(w.lower() for w in re.split(r"[_\-]", token) if len(w) > 1)
        return words
