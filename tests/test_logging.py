from __future__ import annotations

import json
import logging

from code_rag.config.logging import JsonLogFormatter, configure_logging


def _record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="code_rag.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_includes_core_fields_and_extra() -> None:
    formatted = JsonLogFormatter().format(_record(job_id="job-1", duration_seconds=0.5))
    payload = json.loads(formatted)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "code_rag.test"
    assert payload["message"] == "hello world"
    assert payload["job_id"] == "job-1"
    assert payload["duration_seconds"] == 0.5


def test_configure_logging_is_idempotent() -> None:
    root = logging.getLogger()
    configure_logging("DEBUG", "json")
    managed = [h for h in root.handlers if getattr(h, "_code_rag_managed", False)]
    configure_logging("INFO", "text")
    managed_after = [h for h in root.handlers if getattr(h, "_code_rag_managed", False)]
    # Re-configuring replaces the managed handler rather than stacking duplicates.
    assert len(managed) == 1
    assert len(managed_after) == 1
    assert root.level == logging.INFO
