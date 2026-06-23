from __future__ import annotations

from fastapi import Depends, Header

from code_rag.apps.auth.authenticator import Authenticator
from code_rag.domain.models import AuthContext
from code_rag.interfaces.rest.dependencies import get_authenticator


def require_auth(
    x_api_key: str | None = Header(default=None),
    authenticator: Authenticator = Depends(get_authenticator),
) -> AuthContext:
    """FastAPI dependency that enforces API-key auth and resolves identity.

    In development (no API keys configured) this returns an unauthenticated
    context and request-supplied identities are trusted downstream.
    """

    return authenticator.authenticate(x_api_key)
