from __future__ import annotations

from typing import Any

from code_rag.domain import QueryType, SearchHit, SearchResponse


def make_hit(
    chunk_id: str = "c1",
    *,
    score: float = 1.0,
    file_path: str = "service.py",
    symbol_name: str | None = "PaymentService",
    symbol_role: str = "definition",
    chunk_kind: str = "function_definition",
    gitlab_blob_url: str = "https://gitlab.example.com/group/payments/-/blob/abc/service.py#L1-L3",
    metadata: dict[str, Any] | None = None,
) -> SearchHit:
    meta = {"symbol_role": symbol_role, "branch": "develop", "gitlab_project_id": "123"}
    if metadata:
        meta.update(metadata)
    return SearchHit(
        chunk_id=chunk_id,
        score=score,
        repo_path_with_namespace="group/payments",
        file_path=file_path,
        line_start=1,
        line_end=3,
        language="python",
        chunk_kind=chunk_kind,
        symbol_name=symbol_name,
        symbol_fqn=f"group.payments.{symbol_name}" if symbol_name else None,
        gitlab_blob_url=gitlab_blob_url,
        text="Repository: group/payments\nCode:\npass",
        metadata=meta,
    )


def make_response(
    hits: list[SearchHit] | None = None,
    *,
    query: str = "Where is PaymentService implemented?",
    query_type: QueryType = QueryType.DEFINITION_LOOKUP,
    context: str = "Source: group/payments/service.py",
) -> SearchResponse:
    return SearchResponse(
        query=query,
        query_type=query_type,
        identifiers=["PaymentService"],
        hits=[make_hit()] if hits is None else hits,
        context=context,
    )
