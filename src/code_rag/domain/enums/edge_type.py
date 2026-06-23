from __future__ import annotations

from enum import StrEnum


class EdgeType(StrEnum):
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    REFERENCES = "REFERENCES"
    TESTS = "TESTS"
    CONFIGURES = "CONFIGURES"
    EXPOSES_ENDPOINT = "EXPOSES_ENDPOINT"
