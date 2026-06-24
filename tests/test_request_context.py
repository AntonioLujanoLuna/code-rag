from __future__ import annotations

import pytest

try:
    from fastapi import APIRouter
    from fastapi.testclient import TestClient

    from code_rag.interfaces.rest.main import app
except Exception:  # pragma: no cover - optional test deps
    TestClient = None


_router = APIRouter() if TestClient is not None else None

if _router is not None:

    @_router.get("/_boom")
    def _boom() -> dict:
        raise RuntimeError("kaboom")

    app.include_router(_router)


@pytest.fixture()
def client():
    if TestClient is None:  # pragma: no cover
        pytest.skip("fastapi test client unavailable")
    # raise_server_exceptions=False so the registered 500 handler runs instead
    # of the TestClient re-raising the error.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_health_response_carries_request_id_header(client) -> None:
    response = client.get("/health")
    assert response.headers.get("x-request-id")


def test_incoming_request_id_is_echoed(client) -> None:
    response = client.get("/health", headers={"X-Request-ID": "trace-123"})
    assert response.headers["x-request-id"] == "trace-123"


def test_unhandled_error_returns_json_with_request_id(client) -> None:
    response = client.get("/_boom")
    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal Server Error"
    assert body["request_id"] == response.headers["x-request-id"]


def test_validation_error_includes_request_id(client) -> None:
    response = client.post("/search", json={})
    assert response.status_code == 422
    body = response.json()
    assert "request_id" in body
    assert isinstance(body["detail"], list)
