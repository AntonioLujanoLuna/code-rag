from __future__ import annotations

from code_rag.apps.ratelimit.rate_limiter import SlidingWindowRateLimiter


def test_disabled_limiter_always_allows() -> None:
    limiter = SlidingWindowRateLimiter(max_requests=0)
    assert not limiter.enabled
    for _ in range(100):
        assert limiter.allow("alice")


def test_limit_is_enforced_per_key() -> None:
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
    # Use an explicit clock so the test is deterministic.
    assert limiter.allow("alice", now=1000.0)
    assert limiter.allow("alice", now=1000.5)
    assert not limiter.allow("alice", now=1001.0)
    # A different key has its own budget.
    assert limiter.allow("bob", now=1001.0)


def test_window_slides_and_frees_budget() -> None:
    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=10.0)
    assert limiter.allow("alice", now=100.0)
    assert not limiter.allow("alice", now=105.0)
    # Once the first hit ages out of the window, the budget is available again.
    assert limiter.allow("alice", now=111.0)
