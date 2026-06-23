from __future__ import annotations

from pydantic import BaseModel


class SecretFinding(BaseModel):
    secret_type: str
    line: int
    start: int
    end: int
    confidence: str
    redacted_value: str = "[REDACTED_SECRET]"
