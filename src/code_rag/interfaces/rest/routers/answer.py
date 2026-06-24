from __future__ import annotations

from inspect import isawaitable

from fastapi import APIRouter, Depends

from code_rag.apps.auth.authenticator import Authenticator
from code_rag.apps.retrieval.retrieval_service import RetrievalService
from code_rag.domain.models import (
    AnswerRequest,
    AnswerResponse,
    AuthContext,
    SearchRequest,
    SourceCitation,
)
from code_rag.interfaces.rest.dependencies import (
    get_answer_provider,
    get_authenticator,
    get_retrieval_service,
)
from code_rag.interfaces.rest.security import enforce_rate_limit
from code_rag.ports.answer import AnswerProvider

router = APIRouter()


@router.post("/answer", response_model=AnswerResponse)
async def answer(
    request: AnswerRequest,
    context: AuthContext = Depends(enforce_rate_limit),
    authenticator: Authenticator = Depends(get_authenticator),
    retrieval: RetrievalService = Depends(get_retrieval_service),
    answer_provider: AnswerProvider = Depends(get_answer_provider),
) -> AnswerResponse:
    user_id = authenticator.resolve_user_id(context, request.user_id)
    if user_id != request.user_id:
        request = request.model_copy(update={"user_id": user_id})
    search_result = retrieval.search(
        SearchRequest(**request.model_dump(exclude={"max_context_chars"}))
    )
    search_response = await search_result if isawaitable(search_result) else search_result
    citations = [
        SourceCitation(
            index=index,
            repo_path_with_namespace=hit.repo_path_with_namespace,
            file_path=hit.file_path,
            line_start=hit.line_start,
            line_end=hit.line_end,
            url=hit.gitlab_blob_url,
        )
        for index, hit in enumerate(search_response.hits, start=1)
    ]
    return AnswerResponse(
        query=request.query,
        answer=answer_provider.answer(search_response, request.max_context_chars),
        grounded=answer_provider.is_grounded(search_response),
        refusal_reason=answer_provider.refusal_reason(search_response),
        source_coverage=answer_provider.source_coverage(search_response),
        query_type=search_response.query_type,
        identifiers=search_response.identifiers,
        sources=citations,
        context=search_response.context[: request.max_context_chars],
    )
