from __future__ import annotations

import hashlib


def stable_id(*parts: object) -> str:
    normalized = "\x1f".join(str(part or "") for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def content_hash(content: bytes | str) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8", errors="ignore")
    return hashlib.sha256(content).hexdigest()

