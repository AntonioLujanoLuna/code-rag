from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CODE_RAG_", env_file=".env", extra="ignore")

    tenant_id: str = "default"
    branch: str = "develop"

    gitlab_base_url: str = "https://gitlab.com"
    gitlab_token: str = ""
    gitlab_webhook_secret: str = ""

    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_api_key: str = ""

    embedding_service_url: str = ""
    embedding_service_timeout_seconds: float = 30.0
    late_interaction_dimension: int = 128

    llm_answer_service_url: str = ""
    llm_answer_service_timeout_seconds: float = 60.0
    min_answer_sources: int = 1
    min_answer_score: float = 0.0
    http_retries: int = 3
    http_retry_backoff_seconds: float = 0.25

    # Answer generation. ``extractive`` (default) builds a grounded source list
    # locally; ``anthropic`` calls the Claude Messages API with the same
    # citation/refusal gates; ``http`` posts to ``llm_answer_service_url``.
    answer_provider: str = "extractive"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"
    anthropic_max_tokens: int = 2_048

    clone_cache_dir: Path = Path(".cache/repos")
    worktree_dir: Path = Path(".cache/worktrees")
    repo_metadata_path: Path | None = None

    embedding_dimension: int = 384
    embedding_model: str = "hash-embedding-v1"

    max_file_bytes: int = 750_000
    max_chunk_chars: int = 7_000
    min_chunk_chars: int = 300
    max_index_workers: int = 2
    # Parallelism for processing files within a single indexing job.
    index_file_workers: int = 4
    # Cap on how many references/calls a single chunk records, to bound index size.
    max_symbol_references: int = 100
    # Use tree-sitter AST chunking for non-Python languages when a grammar is
    # installed; falls back to regex chunking otherwise.
    use_tree_sitter: bool = True
    # Reuse stored embeddings when a chunk's embedding input hash is unchanged.
    reuse_existing_embeddings: bool = True

    allow_request_supplied_permissions: bool = False
    secret_scanning_enabled: bool = True
    skip_chunks_with_high_confidence_secrets: bool = False

    # API authentication. Maps API key -> trusted user_id. When empty, the API
    # runs in development mode: no key is required and request-supplied user_ids
    # are trusted. When populated, every protected endpoint requires a valid
    # ``X-API-Key`` header and the resolved identity overrides request bodies.
    api_keys: dict[str, str] = Field(default_factory=dict)

    # Retrieval rerank weights (made configurable instead of magic numbers).
    rerank_identifier_boost: float = 0.15
    rerank_definition_boost: float = 0.2
    rerank_usage_boost: float = 0.2
    rerank_test_boost: float = 0.15
    rerank_config_boost: float = 0.05
    rerank_late_interaction_weight: float = 0.1

    index_prefix: str = ""
    index_version: int = 1

    # Split large embed batches into sub-batches sent concurrently. 0 = disabled.
    max_embedding_batch_size: int = 0

    # HyDE: generate a hypothetical code snippet to augment the vector query.
    hyde_enabled: bool = False
    hyde_model: str = ""  # falls back to anthropic_model when empty

    # Lines of context carried forward between consecutive fixed-size chunks.
    chunk_overlap_lines: int = 3

    # Expand short BM25 queries with CamelCase/snake_case splits and synonyms.
    query_expansion_enabled: bool = True

    source_extensions: set[str] = Field(
        default_factory=lambda: {
            ".py",
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".java",
            ".kt",
            ".go",
            ".rs",
            ".cs",
            ".cpp",
            ".c",
            ".h",
            ".hpp",
            ".rb",
            ".php",
            ".scala",
        }
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
