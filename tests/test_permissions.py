from __future__ import annotations

import pytest
from fastapi import HTTPException

from code_rag.adapters.permissions.in_memory_permission_store import InMemoryPermissionStore
from code_rag.apps.permissions.permission_service import PermissionService
from code_rag.config.settings import Settings
from code_rag.domain.models import PermissionRecord


def _service(**settings_kwargs) -> tuple[PermissionService, InMemoryPermissionStore]:
    store = InMemoryPermissionStore()
    return PermissionService(Settings(**settings_kwargs), store), store


def test_in_memory_store_upsert_and_get() -> None:
    store = InMemoryPermissionStore()
    record = PermissionRecord(user_id="alice", tenant_id="default", accessible_project_ids=["1"])
    store.upsert(record)
    assert store.get("default", "alice") is record
    assert store.get("default", "bob") is None


def test_upsert_defaults_tenant_id_when_blank() -> None:
    service, store = _service(tenant_id="acme")
    record = PermissionRecord(user_id="alice", tenant_id="", accessible_project_ids=["1", "2"])

    saved = service.upsert(record)

    assert saved.tenant_id == "acme"
    assert saved.accessible_project_ids == ["1", "2"]
    assert store.get("acme", "alice") is saved


def test_resolve_intersects_requested_with_synced() -> None:
    service, _ = _service()
    service.upsert(
        PermissionRecord(user_id="alice", tenant_id="default", accessible_project_ids=["1", "2"])
    )

    assert service.resolve_allowed_projects("default", "alice", ["2", "3"]) == ["2"]
    # No request filter returns the full sorted allow-list.
    assert service.resolve_allowed_projects("default", "alice", []) == ["1", "2"]


def test_resolve_raises_when_user_has_no_cache() -> None:
    service, _ = _service()
    with pytest.raises(HTTPException) as excinfo:
        service.resolve_allowed_projects("default", "ghost", [])
    assert excinfo.value.status_code == 403


def test_resolve_requires_user_id_by_default() -> None:
    service, _ = _service()
    with pytest.raises(HTTPException) as excinfo:
        service.resolve_allowed_projects("default", None, ["1"])
    assert excinfo.value.status_code == 403


def test_resolve_allows_request_supplied_permissions_when_enabled() -> None:
    service, _ = _service(allow_request_supplied_permissions=True)
    assert service.resolve_allowed_projects("default", None, ["1", "2"]) == ["1", "2"]
