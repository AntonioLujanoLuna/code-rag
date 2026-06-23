from __future__ import annotations

from enum import StrEnum


class QueryType(StrEnum):
    DEFINITION_LOOKUP = "definition_lookup"
    USAGE_LOOKUP = "usage_lookup"
    ARCHITECTURE_QUESTION = "architecture_question"
    DEBUGGING_QUESTION = "debugging_question"
    API_QUESTION = "api_question"
    CONFIG_QUESTION = "config_question"
    TEST_QUESTION = "test_question"
    DEPLOYMENT_QUESTION = "deployment_question"
    OWNERSHIP_QUESTION = "ownership_question"
    MIGRATION_QUESTION = "migration_question"
