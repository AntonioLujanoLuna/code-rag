from __future__ import annotations

from typing import Protocol

from code_rag.models import SearchResponse


class AnswerProvider(Protocol):
    def answer(self, search_response: SearchResponse, max_context_chars: int) -> str:
        """Generate an answer grounded in retrieved context."""
