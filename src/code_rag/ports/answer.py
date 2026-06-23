from __future__ import annotations

from typing import Protocol

from code_rag.domain.models import SearchResponse


class AnswerProvider(Protocol):
    def answer(self, search_response: SearchResponse, max_context_chars: int) -> str:
        """Generate an answer grounded in retrieved context."""

    def is_grounded(self, search_response: SearchResponse) -> bool:
        """Return whether the response meets grounding thresholds."""

    def refusal_reason(self, search_response: SearchResponse) -> str | None:
        """Return a refusal reason when evidence is insufficient."""

    def source_coverage(self, search_response: SearchResponse) -> float:
        """Return the fraction of hits that carry a source link."""
