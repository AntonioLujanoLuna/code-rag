from __future__ import annotations

from fastapi import APIRouter, Depends

from code_rag.apps.permissions.permission_service import PermissionService
from code_rag.domain.models import PermissionRecord
from code_rag.interfaces.rest.dependencies import get_permission_service
from code_rag.interfaces.rest.security import require_auth

router = APIRouter()


@router.post("/permissions", response_model=PermissionRecord)
def upsert_permissions(
    record: PermissionRecord,
    _: object = Depends(require_auth),
    service: PermissionService = Depends(get_permission_service),
) -> PermissionRecord:
    return service.upsert(record)
