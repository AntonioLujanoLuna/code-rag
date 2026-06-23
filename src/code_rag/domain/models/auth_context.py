from __future__ import annotations

from pydantic import BaseModel


class AuthContext(BaseModel):
    """Identity resolved from an authenticated request.

    ``user_id`` is the trusted identity bound to the presented API key (when the
    key maps to one). ``authenticated`` is ``False`` only in development mode,
    where no API keys are configured and request-supplied identities are trusted.
    """

    user_id: str | None = None
    authenticated: bool = True
