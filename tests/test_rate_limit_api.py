from __future__ import annotations

import pytest

from code_rag.apps.ratelimit.rate_limiter import SlidingWindowRateLimiter
from code_rag.domain import QueryType, SearchResponse

try:
    from fastapi.testclient import TestClient

    from code_rag.interfaces.rest.dependencies import get_rate_limiter, get_retrieval_service
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
    app.dependency_overrides[get_retrieval_service] = lambda: FakeRetrieval()
    # Dev mode (no API keys): identity falls back to client host. Reuse one
    # limiter instance across requests so its window state accumulates.
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_search_is_rate_limited(client) -> None:
    body = {"query": "where is PaymentService"}
    assert client.post("/search", json=body).status_code == 200
    assert client.post("/search", json=body).status_code == 200
    third = client.post("/search", json=body)
    assert third.status_code == 429
    assert third.json()["detail"] == "Rate limit exceeded"
