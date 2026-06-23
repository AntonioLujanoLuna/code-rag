from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from code_rag.adapters.elasticsearch.index import ElasticsearchCodeIndex
from code_rag.adapters.git.git_repo_cache import GitRepoCache
from code_rag.config.settings import Settings
from code_rag.domain import (
    AnswerRequest,
    GitLabProject,
    IndexJobResult,
    SearchRequest,
    utcnow,
)
from code_rag.interfaces.rest.routers.jobs import get_job


def test_delete_file_scopes_edge_deletion_to_project() -> None:
    index = _es_index()
    index.client = DeleteCaptureClient()

    index.delete_file("tenant", "123", "develop", "README.md")

    edge_call = index.client.calls[-1]
    filters = edge_call["query"]["bool"]["filter"]
    assert {"term": {"source_repo_project_id": "123"}} in filters


def test_edge_search_applies_chunk_filters_for_repo_path() -> None:
    index = _es_index()
    client = EdgeSearchCaptureClient(index)
    index.client = client

    index.edge_search(
        ["PaymentService"],
        {
            "tenant_id": "tenant",
            "branch": "develop",
            "allowed_project_ids": ["123"],
            "repo_path_with_namespace": "group/payments",
        },
        10,
    )

    chunk_filters = client.chunk_query["bool"]["filter"]
    assert {"ids": {"values": ["chunk-1"]}} in chunk_filters
    assert {"term": {"repo_path_with_namespace": "group/payments"}} in chunk_filters
    assert {"term": {"active_snapshot": True}} in chunk_filters


def test_get_job_falls_back_to_persisted_result() -> None:
    result = _job_result("job-1")
    status = get_job("job-1", queue=EmptyQueue(), job_store=FakeJobStore(result))

    assert status.job_id == "job-1"
    assert status.status == "succeeded"
    assert status.result == result


def test_get_job_404s_when_queue_and_index_miss() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_job("missing", queue=EmptyQueue(), job_store=FakeJobStore(None))

    assert exc_info.value.status_code == 404


def test_request_models_bound_expensive_inputs() -> None:
    with pytest.raises(ValidationError):
        SearchRequest(query="", allowed_project_ids=["123"])
    with pytest.raises(ValidationError):
        SearchRequest(query="find service", allowed_project_ids=["123"], top_k=0)
    with pytest.raises(ValidationError):
        SearchRequest(query="find service", allowed_project_ids=["123"], top_k=51)
    with pytest.raises(ValidationError):
        AnswerRequest(query="find service", allowed_project_ids=["123"], max_context_chars=999)


def test_git_repo_cache_uses_unique_temporary_worktrees(tmp_path: Path) -> None:
    settings = Settings(clone_cache_dir=tmp_path / "repos", worktree_dir=tmp_path / "worktrees")
    cache = GitRepoCache(settings)
    cache._run = lambda *args, **kwargs: ""
    project = GitLabProject(
        gitlab_project_id="123",
        repo_path_with_namespace="group/payments",
        repo_name="payments",
        repo_url="https://gitlab.example.com/group/payments.git",
    )

    first = cache.checkout(project, "develop")
    second = cache.checkout(project, "develop")

    assert first != second
    assert first.exists()
    assert second.exists()
    cache.cleanup(first)
    cache.cleanup(second)
    assert not first.exists()
    assert not second.exists()


def _es_index() -> ElasticsearchCodeIndex:
    index = object.__new__(ElasticsearchCodeIndex)
    index.settings = Settings()
    return index


def _job_result(job_id: str) -> IndexJobResult:
    now = utcnow()
    return IndexJobResult(
        job_id=job_id,
        job_type="full_repo_index",
        gitlab_project_id="123",
        repo_path_with_namespace="group/payments",
        branch="develop",
        new_sha="abc123",
        status="succeeded",
        started_at=now,
        finished_at=now,
    )


class DeleteCaptureClient:
    def __init__(self) -> None:
        self.calls = []

    def delete_by_query(self, **kwargs):
        self.calls.append(kwargs)
        return {"deleted": 0}


class EdgeSearchCaptureClient:
    def __init__(self, index: ElasticsearchCodeIndex) -> None:
        self.index = index
        self.chunk_query = None

    def search(self, index: str, **kwargs):
        if index == self.index.edges_index:
            return {"hits": {"hits": [{"_source": {"source_symbol_id": "chunk-1"}}]}}
        self.chunk_query = kwargs["query"]
        return {"hits": {"hits": []}}


class EmptyQueue:
    def get(self, job_id: str):
        return None


class FakeJobStore:
    def __init__(self, result: IndexJobResult | None) -> None:
        self.result = result

    def get_job(self, job_id: str) -> IndexJobResult | None:
        return self.result if self.result and self.result.job_id == job_id else None
