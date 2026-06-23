from __future__ import annotations

from enum import StrEnum


class SymbolRole(StrEnum):
    DEFINITION = "definition"
    REFERENCE = "reference"
    MIXED = "mixed"
    NONE = "none"
