from __future__ import annotations

import time
from collections import deque
from threading import Lock


class SlidingWindowRateLimiter:
    """In-process sliding-window rate limiter keyed by identity.

    Suitable for a single API worker or best-effort protection across a small
    pool. For strict global limits across many workers, back this with a shared
    store (e.g. Redis); the interface is intentionally narrow so the
    implementation can be swapped without touching callers.
    """

    def __init__(self, max_requests: int, window_seconds: float = 60.0) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    @property
    def enabled(self) -> bool:
        return self._max_requests > 0

    def allow(self, key: str, now: float | None = None) -> bool:
        """Record a request for ``key`` and return whether it is within the limit."""
        if not self.enabled:
            return True
        current = time.monotonic() if now is None else now
        cutoff = current - self._window_seconds
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self._max_requests:
                return False
            bucket.append(current)
            return True
