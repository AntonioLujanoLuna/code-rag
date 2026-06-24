from __future__ import annotations

import pytest

try:
    from fastapi.testclient import TestClient

    from code_rag.interfaces.rest.dependencies import get_index
    from code_rag.interfaces.rest.main import app
except Exception:  # pragma: no cover - optional test deps
    TestClient = None


class FakeIndex:
    def __init__(self, reachable: bool) -> None:
        self._reachable = reachable

    def ping(self) -> bool:
        if isinstance(self._reachable, Exception):
            raise self._reachable
        return self._reachable


@pytest.fixture()
def client():
    if TestClient is None:  # pragma: no cover
        pytest.skip("fastapi test client unavailable")
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_is_cheap_liveness(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_200_when_elasticsearch_reachable(client) -> None:
    app.dependency_overrides[get_index] = lambda: FakeIndex(reachable=True)
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_ready_returns_503_when_elasticsearch_unreachable(client) -> None:
    app.dependency_overrides[get_index] = lambda: FakeIndex(reachable=False)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["elasticsearch"] == "unreachable"


def test_ready_returns_503_when_ping_raises(client) -> None:
    app.dependency_overrides[get_index] = lambda: FakeIndex(reachable=RuntimeError("boom"))
    response = client.get("/ready")
    assert response.status_code == 503
