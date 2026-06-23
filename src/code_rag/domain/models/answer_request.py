from __future__ import annotations

from pydantic import Field

from code_rag.domain.models.search_request import SearchRequest


class AnswerRequest(SearchRequest):
    max_context_chars: int = Field(default=12_000, ge=1_000, le=100_000)
