"""Per-request correlation id, propagated to logs and error responses.

A ``ContextVar`` carries the id through the async request so every log record
emitted while handling a request is automatically tagged with ``request_id``
(via :class:`RequestIdFilter`), and handlers can echo it back to clients for
end-to-end tracing.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("code_rag_request_id", default=None)


def set_request_id(value: str | None) -> str:
    """Set the current request id, generating one when ``value`` is falsy."""
    request_id = value or uuid.uuid4().hex
    _request_id.set(request_id)
    return request_id


def get_request_id() -> str | None:
    """Return the request id bound to the current context, if any."""
    return _request_id.get()


class RequestIdFilter(logging.Filter):
    """Attach the contextual ``request_id`` to every log record that lacks one."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            request_id = _request_id.get()
            if request_id is not None:
                record.request_id = request_id
        return True
