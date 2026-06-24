from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status

from code_rag.apps.auth.authenticator import Authenticator
from code_rag.apps.ratelimit.rate_limiter import SlidingWindowRateLimiter
from code_rag.domain.models import AuthContext
from code_rag.interfaces.rest.dependencies import get_authenticator, get_rate_limiter


def require_auth(
    x_api_key: str | None = Header(default=None),
    authenticator: Authenticator = Depends(get_authenticator),
) -> AuthContext:
    """FastAPI dependency that enforces API-key auth and resolves identity.

    In development (no API keys configured) this returns an unauthenticated
    context and request-supplied identities are trusted downstream.
    """

    return authenticator.authenticate(x_api_key)


def enforce_rate_limit(
    request: Request,
    context: AuthContext = Depends(require_auth),
    limiter: SlidingWindowRateLimiter = Depends(get_rate_limiter),
) -> AuthContext:
    """Apply per-identity rate limiting, returning the resolved auth context.

    The limiter is keyed by the authenticated ``user_id`` when present, falling
    back to the client host so anonymous/development traffic is still bounded.
    A no-op when ``rate_limit_requests_per_minute`` is 0 (the default).
    """

    key = context.user_id or (request.client.host if request.client else "anonymous")
    if not limiter.allow(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )
    return context
