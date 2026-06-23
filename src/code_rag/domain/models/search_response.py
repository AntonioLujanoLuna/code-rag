from __future__ import annotations

from pydantic import BaseModel

from code_rag.domain.enums.query_type import QueryType
from code_rag.domain.models.search_hit import SearchHit


class SearchResponse(BaseModel):
    query: str
    query_type: QueryType
    identifiers: list[str]
    hits: list[SearchHit]
    context: str
