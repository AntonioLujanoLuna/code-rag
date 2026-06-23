from __future__ import annotations

from functools import lru_cache

from code_rag.adapters.answer import ExtractiveAnswerProvider
from code_rag.adapters.elasticsearch_index import ElasticsearchCodeIndex
from code_rag.adapters.embeddings import HttpLateInteractionEmbeddingProvider
from code_rag.adapters.git_repo_cache import GitRepoCache
from code_rag.adapters.gitlab_client import GitLabClient
from code_rag.adapters.permissions import InMemoryPermissionStore
from code_rag.application.chunking import ChunkBuilder
from code_rag.application.file_classifier import FileClassifier
from code_rag.application.indexing import IndexingService
from code_rag.application.jobs import IndexJobQueue
from code_rag.application.metrics import MetricsRegistry
from code_rag.application.permissions import PermissionService
from code_rag.application.repo_metadata import RepoMetadataProvider
from code_rag.application.retrieval import RetrievalService
from code_rag.application.secrets import SecretScanner
from code_rag.settings import get_settings


@lru_cache
def get_index() -> ElasticsearchCodeIndex:
    return ElasticsearchCodeIndex(get_settings())


@lru_cache
def get_embeddings() -> HttpLateInteractionEmbeddingProvider:
    settings = get_settings()
    return HttpLateInteractionEmbeddingProvider(settings)


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
def get_permission_store() -> InMemoryPermissionStore:
    return InMemoryPermissionStore()


@lru_cache
def get_permission_service() -> PermissionService:
    return PermissionService(get_settings(), get_permission_store())


@lru_cache
def get_job_queue() -> IndexJobQueue:
    return IndexJobQueue(get_settings().max_index_workers)


@lru_cache
def get_answer_provider() -> ExtractiveAnswerProvider:
    return ExtractiveAnswerProvider(get_settings())


@lru_cache
def get_metrics() -> MetricsRegistry:
    return MetricsRegistry()


def get_indexing_service() -> IndexingService:
    settings = get_settings()
    return IndexingService(
        settings=settings,
        repo_cache=get_repo_cache(),
        index=get_index(),
        embeddings=get_embeddings(),
        classifier=get_classifier(),
        chunk_builder=get_chunk_builder(),
        repo_metadata=get_repo_metadata_provider(),
    )


def get_retrieval_service() -> RetrievalService:
    settings = get_settings()
    return RetrievalService(
        settings=settings,
        index=get_index(),
        embeddings=get_embeddings(),
        permissions=get_permission_service(),
    )
