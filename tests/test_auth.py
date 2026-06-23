from __future__ import annotations

import pytest
from fastapi import HTTPException

from code_rag.apps.auth.authenticator import Authenticator
from code_rag.config.settings import Settings


def test_dev_mode_trusts_request_identity() -> None:
    auth = Authenticator(Settings(api_keys={}))
    context = auth.authenticate(None)

    assert not context.authenticated
    assert auth.resolve_user_id(context, "alice") == "alice"


def test_enforced_mode_requires_valid_key() -> None:
    auth = Authenticator(Settings(api_keys={"secret-key": "alice"}))

    with pytest.raises(HTTPException) as exc_info:
        auth.authenticate(None)
    assert exc_info.value.status_code == 401

    with pytest.raises(HTTPException):
        auth.authenticate("wrong")


def test_enforced_mode_binds_identity_to_key() -> None:
    auth = Authenticator(Settings(api_keys={"secret-key": "alice"}))
    context = auth.authenticate("secret-key")

    assert context.authenticated
    assert context.user_id == "alice"
    # Request omits user_id -> resolved from the key.
    assert auth.resolve_user_id(context, None) == "alice"
    # Matching id is allowed; a spoofed id is rejected.
    assert auth.resolve_user_id(context, "alice") == "alice"
    with pytest.raises(HTTPException) as exc_info:
        auth.resolve_user_id(context, "mallory")
    assert exc_info.value.status_code == 403
