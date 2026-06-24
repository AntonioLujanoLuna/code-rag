from __future__ import annotations

from functools import lru_cache

from code_rag.adapters.answer.anthropic_answer_provider import AnthropicAnswerProvider
from code_rag.adapters.answer.extractive_answer_provider import ExtractiveAnswerProvider
from code_rag.adapters.elasticsearch.index import ElasticsearchCodeIndex
from code_rag.adapters.elasticsearch.permission_store import ElasticsearchPermissionStore
from code_rag.adapters.embeddings.http_embedding_provider import (
    HttpLateInteractionEmbeddingProvider,
)
from code_rag.adapters.git.git_repo_cache import GitRepoCache
from code_rag.adapters.gitlab.gitlab_client import GitLabClient
from code_rag.apps.auth.authenticator import Authenticator
from code_rag.apps.chunking.chunk_builder import ChunkBuilder
from code_rag.apps.classification.file_classifier import FileClassifier
from code_rag.apps.indexing.indexing_service import IndexingService
from code_rag.apps.jobs.index_job_queue import IndexJobQueue
from code_rag.apps.metadata.repo_metadata_provider import RepoMetadataProvider
from code_rag.apps.metrics.metrics_registry import MetricsRegistry
from code_rag.apps.permissions.permission_service import PermissionService
from code_rag.apps.ratelimit.rate_limiter import SlidingWindowRateLimiter
from code_rag.apps.retrieval.retrieval_service import RetrievalService
from code_rag.apps.secrets.secret_scanner import SecretScanner
from code_rag.config.settings import get_settings
from code_rag.ports.answer import AnswerProvider
from code_rag.ports.job_store import JobStorePort


@lru_cache
def get_index() -> ElasticsearchCodeIndex:
    return ElasticsearchCodeIndex(get_settings())


def get_job_store() -> JobStorePort:
    # The Elasticsearch adapter implements the narrow JobStorePort.
    return get_index()


@lru_cache
def get_embeddings() -> HttpLateInteractionEmbeddingProvider:
    return HttpLateInteractionEmbeddingProvider(get_settings())


@lru_cache
def get_gitlab() -> GitLabClient:
    return GitLabClient(get_settings())


@lru_cache
def get_repo_cache() -> GitRepoCache:
    return GitRepoCache(get_settings())


@lru_cache
def get_classifier() -> FileClassifier:
    return FileClassifier(get_settings())


@lru_cache
def get_secret_scanner() -> SecretScanner:
    return SecretScanner()


@lru_cache
def get_repo_metadata_provider() -> RepoMetadataProvider:
    return RepoMetadataProvider(get_settings())


@lru_cache
def get_chunk_builder() -> ChunkBuilder:
    settings = get_settings()
    return ChunkBuilder(
        settings,
        get_classifier(),
        secret_scanner=get_secret_scanner(),
        repo_metadata=get_repo_metadata_provider(),
    )


@lru_cache
def get_permission_store() -> ElasticsearchPermissionStore:
    return ElasticsearchPermissionStore(get_settings())


@lru_cache
def get_permission_service() -> PermissionService:
    return PermissionService(get_settings(), get_permission_store())


@lru_cache
def get_authenticator() -> Authenticator:
    return Authenticator(get_settings())


@lru_cache
def get_job_queue() -> IndexJobQueue:
    settings = get_settings()
    return IndexJobQueue(settings.max_index_workers, store=get_index())


@lru_cache
def get_answer_provider() -> AnswerProvider:
    settings = get_settings()
    if settings.answer_provider == "anthropic":
        return AnthropicAnswerProvider(settings)
    return ExtractiveAnswerProvider(settings)


@lru_cache
def get_metrics() -> MetricsRegistry:
    return MetricsRegistry()


@lru_cache
def get_rate_limiter() -> SlidingWindowRateLimiter:
    return SlidingWindowRateLimiter(get_settings().rate_limit_requests_per_minute)


def get_indexing_service() -> IndexingService:
    settings = get_settings()
    index = get_index()
    return IndexingService(
        settings=settings,
        repo_cache=get_repo_cache(),
        index=index,
        embeddings=get_embeddings(),
        classifier=get_classifier(),
        chunk_builder=get_chunk_builder(),
        repo_metadata=get_repo_metadata_provider(),
        repo_store=index,
    )


def get_retrieval_service() -> RetrievalService:
    settings = get_settings()
    return RetrievalService(
        settings=settings,
        index=get_index(),
        embeddings=get_embeddings(),
        permissions=get_permission_service(),
    )
