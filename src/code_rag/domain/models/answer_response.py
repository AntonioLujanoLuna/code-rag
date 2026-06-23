from __future__ import annotations

from pydantic import BaseModel

from code_rag.domain.enums.query_type import QueryType
from code_rag.domain.models.source_citation import SourceCitation


class AnswerResponse(BaseModel):
    query: str
    answer: str
    grounded: bool = True
    refusal_reason: str | None = None
    source_coverage: float = 0.0
    query_type: QueryType
    identifiers: list[str]
    sources: list[SourceCitation]
    context: str
