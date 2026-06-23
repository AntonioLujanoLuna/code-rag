from __future__ import annotations

from enum import StrEnum


class ChunkKind(StrEnum):
    FILE = "file"
    FUNCTION_DEFINITION = "function_definition"
    METHOD_DEFINITION = "method_definition"
    CLASS_DEFINITION = "class_definition"
    CONFIG_BLOCK = "config_block"
    DOCUMENTATION_SECTION = "documentation_section"
    TEST_CASE = "test_case"
