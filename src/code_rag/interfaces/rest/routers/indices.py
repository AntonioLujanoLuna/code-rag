from __future__ import annotations

from fastapi import APIRouter, Depends

from code_rag.adapters.elasticsearch.index import ElasticsearchCodeIndex
from code_rag.adapters.elasticsearch.permission_store import ElasticsearchPermissionStore
from code_rag.interfaces.rest.dependencies import get_index, get_permission_store
from code_rag.interfaces.rest.security import require_auth

router = APIRouter()


@router.post("/indices/init")
def init_indices(
    _: object = Depends(require_auth),
    index: ElasticsearchCodeIndex = Depends(get_index),
    permission_store: ElasticsearchPermissionStore = Depends(get_permission_store),
) -> dict[str, str]:
    index.ensure_indices()
    permission_store.ensure_index()
    return {"status": "created"}
