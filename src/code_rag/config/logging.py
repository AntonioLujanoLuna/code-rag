from __future__ import annotations

import json
import logging
from typing import Any

from code_rag.config.request_context import RequestIdFilter

# Attributes present on every ``logging.LogRecord``. Anything outside this set
# was passed via ``extra=`` and is treated as structured context.
_RESERVED_RECORD_ATTRS = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonLogFormatter(logging.Formatter):
    """Render log records as single-line JSON for log aggregators.

    Fields supplied through ``logger.info(..., extra={...})`` are merged into
    the top-level object so structured context survives in production.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", log_format: str = "json") -> None:
    """Install a root handler so emitted logs (with ``extra`` fields) reach stdout.

    Idempotent: replaces any handlers this function previously installed instead
    of stacking duplicates when called more than once (e.g. reload, tests).
    """
    handler = logging.StreamHandler()
    if log_format == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, "_code_rag_managed", False):
            root.removeHandler(existing)
    handler._code_rag_managed = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level.upper())
