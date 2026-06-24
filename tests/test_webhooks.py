from __future__ import annotations

from datetime import UTC, datetime

import pytest

from code_rag.config.settings import Settings, get_settings
from code_rag.domain.models import GitLabProject, JobStatus

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
    def __init__(self) -> None:
        self.compare_calls: list[tuple[str, str, str]] = []

    def compare(self, project_id, old_sha, new_sha):
        self.compare_calls.append((project_id, old_sha, new_sha))
        return []

    def get_project(self, project_id):  # pragma: no cover - exercised via fallback only
        return GitLabProject(
            gitlab_project_id=project_id,
            repo_path_with_namespace="group/payments",
            repo_name="payments",
            repo_url="https://gitlab.example.com/group/payments.git",
        )


class FakeQueue:
    def __init__(self) -> None:
        self.submitted: list[str] = []

    def submit(self, job_id, job_type, work):
        self.submitted.append(job_id)
        return JobStatus(
            job_id=job_id,
            job_type=job_type,
            status="queued",
            submitted_at=datetime.now(UTC),
        )


class FakeJobStore:
    def get_job(self, job_id):
        return None


@pytest.fixture()
def client():
    if TestClient is None:  # pragma: no cover
        pytest.skip("fastapi test client unavailable")
    app.dependency_overrides[get_settings] = lambda: Settings(
        branch="develop", gitlab_webhook_secret="topsecret"
    )
    app.dependency_overrides[get_gitlab] = lambda: FakeGitLab()
    app.dependency_overrides[get_indexing_service] = lambda: object()
    app.dependency_overrides[get_job_queue] = lambda: FakeQueue()
    app.dependency_overrides[get_job_store] = lambda: FakeJobStore()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _push_payload(branch: str = "develop") -> dict:
    return {
        "ref": f"refs/heads/{branch}",
        "before": "aaa",
        "after": "bbb",
        "project": {
            "id": 123,
            "path_with_namespace": "group/payments",
            "name": "payments",
            "git_http_url": "https://gitlab.example.com/group/payments.git",
        },
    }


def test_webhook_rejects_invalid_token(client) -> None:
    response = client.post(
        "/webhooks/gitlab", json=_push_payload(), headers={"X-Gitlab-Token": "wrong"}
    )
    assert response.status_code == 401


def test_webhook_ignores_other_branches(client) -> None:
    response = client.post(
        "/webhooks/gitlab",
        json=_push_payload(branch="feature/x"),
        headers={"X-Gitlab-Token": "topsecret"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_webhook_queues_job_for_configured_branch(client) -> None:
    response = client.post(
        "/webhooks/gitlab", json=_push_payload(), headers={"X-Gitlab-Token": "topsecret"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["job_type"] == "incremental_repo_index"


def test_webhook_requires_before_and_after(client) -> None:
    payload = _push_payload()
    del payload["after"]
    response = client.post(
        "/webhooks/gitlab", json=payload, headers={"X-Gitlab-Token": "topsecret"}
    )
    assert response.status_code == 400
