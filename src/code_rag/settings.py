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

    clone_cache_dir: Path = Path(".cache/repos")
    worktree_dir: Path = Path(".cache/worktrees")
    repo_metadata_path: Path | None = None

    embedding_dimension: int = 384
    embedding_model: str = "hash-embedding-v1"

    max_file_bytes: int = 750_000
    max_chunk_chars: int = 7_000
    min_chunk_chars: int = 300
    max_index_workers: int = 2
    allow_request_supplied_permissions: bool = False
    secret_scanning_enabled: bool = True
    skip_chunks_with_high_confidence_secrets: bool = False

    index_prefix: str = ""

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
