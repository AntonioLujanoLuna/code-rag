from __future__ import annotations

from datetime import UTC, datetime

import pytest

from code_rag.domain.models import GitLabProject, IndexJobResult, JobStatus

try:
    from fastapi.testclient import TestClient

    from code_rag.interfaces.rest.dependencies import (
        get_gitlab,
        get_indexing_service,
        get_job_queue,
        get_job_store,
    )
    from code_rag.interfaces.rest.main import app
except Exception:  # pragma: no cover - optional test deps
    TestClient = None


class FakeGitLab:
    def get_project(self, project_id):
        return GitLabProject(
            gitlab_project_id=project_id,
            repo_path_with_namespace="group/payments",
            repo_name="payments",
            repo_url="https://gitlab.example.com/group/payments.git",
        )

    def compare(self, project_id, old_sha, new_sha):  # pragma: no cover - changes supplied
        return []


class FakeQueue:
    def __init__(self) -> None:
        self.submitted: list[tuple[str, str]] = []

    def submit(self, job_id, job_type, work):
        self.submitted.append((job_id, job_type))
        return JobStatus(
            job_id=job_id, job_type=job_type, status="queued", submitted_at=datetime.now(UTC)
        )


class FakeJobStore:
    def __init__(self, existing: IndexJobResult | None = None) -> None:
        self.existing = existing

    def get_job(self, job_id):
        return self.existing


@pytest.fixture()
def overrides():
    if TestClient is None:  # pragma: no cover
        pytest.skip("fastapi test client unavailable")
    queue = FakeQueue()
    store = FakeJobStore()
    app.dependency_overrides[get_gitlab] = lambda: FakeGitLab()
    app.dependency_overrides[get_indexing_service] = lambda: object()
    app.dependency_overrides[get_job_queue] = lambda: queue
    app.dependency_overrides[get_job_store] = lambda: store
    with TestClient(app) as client:
        yield client, queue, store
    app.dependency_overrides.clear()


def test_index_project_queues_job(overrides) -> None:
    client, queue, _ = overrides
    response = client.post("/index/project", json={"project_id": "123"})
    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert queue.submitted and queue.submitted[0][1] == "full_repo_index"


def test_index_incremental_queues_job(overrides) -> None:
    client, queue, _ = overrides
    response = client.post(
        "/index/incremental",
        json={"project_id": "123", "old_sha": "aaa", "new_sha": "bbb", "changes": []},
    )
    assert response.status_code == 200
    assert queue.submitted and queue.submitted[0][1] == "incremental_repo_index"


def test_index_project_short_circuits_when_already_succeeded(overrides) -> None:
    client, queue, store = overrides
    now = datetime.now(UTC)
    store.existing = IndexJobResult(
        job_id="existing",
        job_type="full_repo_index",
        gitlab_project_id="123",
        repo_path_with_namespace="group/payments",
        branch="develop",
        old_sha=None,
        new_sha="",
        status="succeeded",
        started_at=now,
        finished_at=now,
    )
    response = client.post("/index/project", json={"project_id": "123"})
    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    # The already-succeeded job is returned without re-queuing.
    assert queue.submitted == []
