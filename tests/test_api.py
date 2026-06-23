from __future__ import annotations

import pytest

from code_rag.apps.auth.authenticator import Authenticator
from code_rag.config.settings import Settings
from code_rag.domain import QueryType, SearchResponse

try:
    from fastapi.testclient import TestClient

    from code_rag.interfaces.rest.dependencies import get_authenticator, get_retrieval_service
    from code_rag.interfaces.rest.main import app
except Exception:  # pragma: no cover - optional test deps
    TestClient = None


class FakeRetrieval:
    def search(self, request):
        return SearchResponse(
            query=request.query,
            query_type=QueryType.ARCHITECTURE_QUESTION,
            identifiers=[],
            hits=[],
            context="",
        )


@pytest.fixture()
def client():
    if TestClient is None:  # pragma: no cover
        pytest.skip("fastapi test client unavailable")
    app.dependency_overrides[get_authenticator] = lambda: Authenticator(
        Settings(api_keys={"secret-key": "alice"})
    )
    app.dependency_overrides[get_retrieval_service] = lambda: FakeRetrieval()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_is_open(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_search_requires_api_key(client) -> None:
    response = client.post("/search", json={"query": "where is PaymentService"})
    assert response.status_code == 401


def test_search_succeeds_with_api_key(client) -> None:
    response = client.post(
        "/search",
        json={"query": "where is PaymentService"},
        headers={"X-API-Key": "secret-key"},
    )
    assert response.status_code == 200
    assert response.json()["query"] == "where is PaymentService"
