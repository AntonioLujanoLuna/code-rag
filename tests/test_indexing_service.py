from __future__ import annotations

from pathlib import Path

from code_rag.apps.indexing.indexing_service import IndexingService
from code_rag.config.settings import Settings
from code_rag.domain.enums.file_class import FileClass
from code_rag.domain.models import FileMetadata, GitLabProject


def _project() -> GitLabProject:
    return GitLabProject(
        gitlab_project_id="123",
        repo_path_with_namespace="group/payments",
        repo_name="payments",
        repo_url="https://gitlab.example.com/group/payments.git",
    )


class FakeRepoCache:
    def __init__(self, worktree: Path, head: str = "deadbeef") -> None:
        self._worktree = worktree
        self._head = head
        self.cleaned: list[Path] = []

    def checkout(self, project, branch, commit_sha):
        return self._worktree

    def head_sha(self, worktree):
        return self._head

    def cleanup(self, worktree):
        self.cleaned.append(worktree)


class FailingRepoCache(FakeRepoCache):
    def checkout(self, project, branch, commit_sha):
        raise RuntimeError("clone failed")


class RecordingIndex:
    def __init__(self) -> None:
        self.replaced: list[FileMetadata] = []
        self.pruned = False
        self.repo_docs: list[dict] = []

    def replace_file(self, metadata, chunks, symbols, edges):
        self.replaced.append(metadata)
        return len(chunks), 0

    def delete_file(self, tenant_id, project_id, branch, path):
        return 0

    def existing_embeddings(self, chunk_ids):
        return {}

    def prune_orphaned_edges(self, tenant_id, project_id, branch):
        self.pruned = True

    def index_repo(self, doc):
        self.repo_docs.append(doc)


class AcceptAllClassifier:
    def should_index(self, path, worktree):
        return True


class StubChunkBuilder:
    def build_file(self, worktree, path, project, branch, commit_sha):
        relative = path.relative_to(worktree).as_posix()
        metadata = FileMetadata(
            tenant_id="default",
            gitlab_instance_url="https://gitlab.example.com",
            gitlab_project_id=project.gitlab_project_id,
            repo_path_with_namespace=project.repo_path_with_namespace,
            repo_name=project.repo_name,
            repo_url=project.repo_url,
            branch=branch,
            commit_sha=commit_sha,
            file_path=relative,
            file_name=path.name,
            file_extension=path.suffix,
            language="python",
            file_hash="hash",
            size_bytes=path.stat().st_size,
            line_count=1,
            file_class=FileClass.SOURCE,
        )
        return metadata, [], [], []


def _service(settings: Settings, repo_cache, index) -> IndexingService:
    service = object.__new__(IndexingService)
    service.settings = settings
    service.repo_cache = repo_cache
    service.index = index
    service.embeddings = None  # no chunks are produced, so embeddings are unused
    service.classifier = AcceptAllClassifier()
    service.chunk_builder = StubChunkBuilder()
    service.repo_metadata = None
    service.repo_store = index
    return service


def test_full_index_succeeds_and_indexes_repo(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    index = RecordingIndex()
    repo_cache = FakeRepoCache(tmp_path, head="cafe1234")
    service = _service(Settings(index_file_workers=1), repo_cache, index)

    result = service.full_index_project(_project(), branch="develop")

    assert result.status == "succeeded"
    assert result.new_sha == "cafe1234"
    assert result.files_seen == 1
    assert index.pruned is True
    assert index.repo_docs and index.repo_docs[0]["active_commit_sha"] == "cafe1234"
    # The worktree is always cleaned up on success.
    assert repo_cache.cleaned == [tmp_path]


def test_full_index_returns_failed_status_on_error() -> None:
    index = RecordingIndex()
    service = _service(Settings(), FailingRepoCache(Path(".")), index)

    result = service.full_index_project(_project(), branch="develop")

    assert result.status == "failed"
    assert "clone failed" in (result.error_message or "")
    assert index.repo_docs == []
