from __future__ import annotations

import httpx
import pytest

from code_rag.adapters.http.retries import request_with_retries


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_returns_first_successful_response() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"ok": True})

    with _client(handler) as client:
        response = request_with_retries(client, "GET", "https://x.test", retries=3)

    assert response.status_code == 200
    assert calls["n"] == 1


def test_retries_on_retryable_status_then_succeeds() -> None:
    statuses = iter([503, 503, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(next(statuses))

    with _client(handler) as client:
        response = request_with_retries(
            client, "GET", "https://x.test", retries=3, backoff_seconds=0.0
        )

    assert response.status_code == 200


def test_returns_last_response_when_retries_exhausted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with _client(handler) as client:
        response = request_with_retries(
            client, "GET", "https://x.test", retries=2, backoff_seconds=0.0
        )

    assert response.status_code == 503


def test_transport_errors_are_retried_then_raised() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        raise httpx.ConnectError("boom", request=request)

    with _client(handler) as client, pytest.raises(httpx.ConnectError):
        request_with_retries(client, "GET", "https://x.test", retries=3, backoff_seconds=0.0)

    assert attempts["n"] == 3
