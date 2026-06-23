from __future__ import annotations

from enum import StrEnum


class FileClass(StrEnum):
    SOURCE = "source_code"
    TEST = "test_code"
    CONFIG = "config"
    CI_CD = "ci_cd"
    DEPLOYMENT = "deployment"
    SCHEMA = "schema"
    MIGRATION = "migration"
    DOCUMENTATION = "documentation"
    GENERATED = "generated"
    VENDOR = "vendor"
    BINARY = "binary"
    LARGE_UNKNOWN = "large_unknown"
    UNKNOWN = "unknown"
