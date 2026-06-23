from __future__ import annotations

from fastapi import HTTPException, status

from code_rag.config.settings import Settings
from code_rag.domain.models import AuthContext


class Authenticator:
    """Resolves a trusted identity from an API key.

    When ``settings.api_keys`` is empty the service runs in development mode:
    requests are not authenticated and request-supplied ``user_id`` values are
    trusted. When keys are configured, a valid ``X-API-Key`` is required and the
    identity it maps to overrides any request-supplied ``user_id``.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.api_keys)

    def authenticate(self, api_key: str | None) -> AuthContext:
        if not self.enabled:
            return AuthContext(user_id=None, authenticated=False)
        if not api_key or api_key not in self.settings.api_keys:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid API key",
            )
        return AuthContext(user_id=self.settings.api_keys[api_key], authenticated=True)

    def resolve_user_id(self, context: AuthContext, requested_user_id: str | None) -> str | None:
        """Bind the effective user id.

        With authentication enabled the key's identity wins and a mismatching
        request-supplied id is rejected; in dev mode the request value is used.
        """

        if not context.authenticated:
            return requested_user_id
        if requested_user_id and requested_user_id != context.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="user_id does not match authenticated identity",
            )
        return context.user_id
