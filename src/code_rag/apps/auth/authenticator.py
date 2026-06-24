from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Any

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
        return bool(
            self.settings.api_keys or self.settings.api_key_users or self.settings.admin_api_keys
        )

    def authenticate(self, api_key: str | None) -> AuthContext:
        if not self.enabled:
            return AuthContext(user_id=None, authenticated=False)
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid API key",
            )
        user_id = self._match_user_key(api_key)
        if user_id:
            return AuthContext(user_id=user_id, authenticated=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
        )

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

    def _match_user_key(self, api_key: str) -> str | None:
        # Backward compatible plaintext mapping: {"secret": "alice"}.
        if isinstance(self.settings.api_keys, dict):
            user_id = self.settings.api_keys.get(api_key)
            if user_id:
                return user_id
            for identity, value in self.settings.api_keys.items():
                if isinstance(value, str):
                    continue
                for entry in self._entries(value):
                    if self._entry_matches(entry, api_key):
                        return str(identity)
        for entry in self._entries(self.settings.api_keys):
            if self._entry_matches(entry, api_key):
                return str(entry.get("user_id") or entry.get("identity") or entry.get("id"))
        for identity, entries in self.settings.api_key_users.items():
            for entry in self._entries(entries):
                if self._entry_matches(entry, api_key):
                    return identity
        for entry in self._entries(self.settings.admin_api_keys):
            if self._entry_matches(entry, api_key):
                return str(
                    entry.get("user_id") or entry.get("identity") or entry.get("id") or "admin"
                )
        return None

    def _entry_matches(self, entry: dict[str, Any], api_key: str) -> bool:
        digest = entry.get("sha256") or entry.get("key_sha256") or entry.get("hash")
        if not digest:
            return False
        actual = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        if not secrets.compare_digest(str(digest), actual):
            return False
        expires_at = entry.get("expires_at")
        return not (expires_at and self._parse_datetime(str(expires_at)) <= datetime.now(UTC))

    def _entries(self, value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [entry for entry in value if isinstance(entry, dict)]
        if isinstance(value, dict):
            return [value]
        return []

    def _parse_datetime(self, value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
