from __future__ import annotations

from fastapi import APIRouter, Depends

from code_rag.apps.auth.authenticator import Authenticator
from code_rag.apps.retrieval.retrieval_service import RetrievalService
from code_rag.domain.models import AuthContext, SearchRequest, SearchResponse
from code_rag.interfaces.rest.dependencies import get_authenticator, get_retrieval_service
from code_rag.interfaces.rest.security import enforce_rate_limit

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    context: AuthContext = Depends(enforce_rate_limit),
    authenticator: Authenticator = Depends(get_authenticator),
    service: RetrievalService = Depends(get_retrieval_service),
) -> SearchResponse:
    user_id = authenticator.resolve_user_id(context, request.user_id)
    if user_id != request.user_id:
        request = request.model_copy(update={"user_id": user_id})
    return service.search(request)
