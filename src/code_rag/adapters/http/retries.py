from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


def request_with_retries(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    retries: int = 3,
    backoff_seconds: float = 0.25,
    **kwargs: Any,
) -> httpx.Response:
    attempts = max(retries, 1)
    for attempt in range(1, attempts + 1):
        try:
            response = client.request(method, url, **kwargs)
            if response.status_code not in RETRYABLE_STATUS_CODES or attempt == attempts:
                return response
            logger.warning(
                "Retrying HTTP request after retryable status",
                extra={
                    "method": method,
                    "url": url,
                    "status_code": response.status_code,
                    "attempt": attempt,
                },
            )
        except (httpx.TimeoutException, httpx.TransportError):
            if attempt == attempts:
                raise
            logger.warning(
                "Retrying HTTP request after transport error",
                extra={"method": method, "url": url, "attempt": attempt},
                exc_info=True,
            )
        time.sleep(backoff_seconds * 2 ** (attempt - 1))
    raise RuntimeError("HTTP retry loop exited unexpectedly")
