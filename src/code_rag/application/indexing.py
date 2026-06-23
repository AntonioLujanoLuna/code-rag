from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from code_rag.application.chunking import ChunkBuilder
from code_rag.application.file_classifier import FileClassifier
from code_rag.application.repo_metadata import RepoMetadataProvider
from code_rag.domain.ids import content_hash, stable_id
from code_rag.models import ChangedFile, GitLabProject, IndexJobResult, utcnow
from code_rag.ports.embedding import EmbeddingProvider
from code_rag.ports.repository import RepoCachePort
from code_rag.ports.search import SearchIndexPort
from code_rag.settings import Settings


class IndexingService:
    def __init__(
        self,
        settings: Settings,
        repo_cache: RepoCachePort,
        index: SearchIndexPort,
        embeddings: EmbeddingProvider,
        classifier: FileClassifier,
        chunk_builder: ChunkBuilder,
        repo_metadata: RepoMetadataProvider | None = None,
    ) -> None:
        self.settings = settings
        self.repo_cache = repo_cache
        self.index = index
        self.embeddings = embeddings
        self.classifier = classifier
        self.chunk_builder = chunk_builder
        self.repo_metadata = repo_metadata

    def full_index_project(
        self,
        project: GitLabProject,
        branch: str | None = None,
        commit_sha: str | None = None,
    ) -> IndexJobResult:
        branch = branch or self.settings.branch
        started_at = utcnow()
        new_sha = commit_sha or ""
        job = self._job("full_repo_index", project, branch, None, new_sha, started_at)
        try:
            worktree = self.repo_cache.checkout(project, branch, commit_sha)
            try:
                new_sha = self.repo_cache.head_sha(worktree)
                stats = self._index_paths(project, branch, new_sha, worktree, self._walk(worktree))
            finally:
                self.repo_cache.cleanup(worktree)
            self._index_repo(project, branch, new_sha, "indexed")
            return job.model_copy(
                update={
                    **stats,
                    "new_sha": new_sha,
                    "status": "succeeded",
                    "finished_at": utcnow(),
                }
            )
        except Exception as exc:
            return job.model_copy(
                update={"status": "failed", "finished_at": utcnow(), "error_message": str(exc)}
            )

    def incremental_index_project(
        self,
        project: GitLabProject,
        old_sha: str,
        new_sha: str,
        changes: list[ChangedFile],
        branch: str | None = None,
    ) -> IndexJobResult:
        branch = branch or self.settings.branch
        started_at = utcnow()
        job = self._job("incremental_repo_index", project, branch, old_sha, new_sha, started_at)
        try:
            worktree = self.repo_cache.checkout(project, branch, new_sha)
            try:
                files_deleted = 0
                files_renamed = 0
                paths_to_index: list[Path] = []
                old_paths_to_delete: list[str] = []
                for change in changes:
                    if change.deleted:
                        files_deleted += 1
                        self.index.delete_file(
                            self.settings.tenant_id,
                            project.gitlab_project_id,
                            branch,
                            change.old_path,
                        )
                        continue
                    if change.renamed:
                        files_renamed += 1
                        old_paths_to_delete.append(change.old_path)
                    candidate = worktree / change.new_path
                    if candidate.exists() and candidate.is_file():
                        if change.renamed and self._renamed_content_unchanged(
                            project.gitlab_project_id,
                            branch,
                            change.old_path,
                            candidate,
                        ):
                            old_paths_to_delete.append(change.old_path)
                        paths_to_index.append(candidate)
                    else:
                        self.index.delete_file(
                            self.settings.tenant_id,
                            project.gitlab_project_id,
                            branch,
                            change.new_path,
                        )
                for old_path in sorted(set(old_paths_to_delete)):
                    self.index.delete_file(
                        self.settings.tenant_id,
                        project.gitlab_project_id,
                        branch,
                        old_path,
                    )
                stats = self._index_paths(project, branch, new_sha, worktree, paths_to_index)
            finally:
                self.repo_cache.cleanup(worktree)
            self._index_repo(project, branch, new_sha, "indexed")
            return job.model_copy(
                update={
                    **stats,
                    "files_deleted": files_deleted,
                    "files_renamed": files_renamed,
                    "status": "succeeded",
                    "finished_at": utcnow(),
                }
            )
        except Exception as exc:
            return job.model_copy(
                update={"status": "failed", "finished_at": utcnow(), "error_message": str(exc)}
            )

    def _index_paths(
        self,
        project: GitLabProject,
        branch: str,
        commit_sha: str,
        worktree: Path,
        paths: list[Path],
    ) -> dict:
        files_seen = 0
        files_added = 0
        chunks_added = 0
        chunks_deleted = 0
        for path in paths:
            if not path.exists() or not path.is_file():
                continue
            files_seen += 1
            if not self.classifier.should_index(path, worktree):
                relative = path.relative_to(worktree).as_posix()
                self.index.delete_file(
                    self.settings.tenant_id,
                    project.gitlab_project_id,
                    branch,
                    relative,
                )
                continue
            metadata, chunks, symbols, edges = self.chunk_builder.build_file(
                worktree, path, project, branch, commit_sha
            )
            if self.settings.skip_chunks_with_high_confidence_secrets:
                skipped_chunk_ids = {
                    chunk.chunk_id for chunk in chunks if chunk.secret_high_confidence_count > 0
                }
                chunks = [chunk for chunk in chunks if chunk.chunk_id not in skipped_chunk_ids]
                symbols = [
                    symbol for symbol in symbols if symbol.definition_chunk_id not in skipped_chunk_ids
                ]
                edges = [
                    edge for edge in edges if edge.source_symbol_id not in skipped_chunk_ids
                ]
            embeddings = self.embeddings.embed_documents([chunk.text_for_embedding for chunk in chunks])
            now = datetime.now(timezone.utc)
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                chunk.embedding_dense = embedding.dense
                chunk.embedding_late_interaction = embedding.late_interaction
                chunk.embedding_model = self.embeddings.model_name
                chunk.embedding_dimension = self.embeddings.dimension
                chunk.embedding_created_at = now
                chunk.embedding_input_hash = stable_id(chunk.text_for_embedding)
            added, deleted = self.index.replace_file(metadata, chunks, symbols, edges)
            files_added += 1
            chunks_added += added
            chunks_deleted += deleted
        return {
            "files_seen": files_seen,
            "files_added": files_added,
            "files_modified": files_added,
            "chunks_added": chunks_added,
            "chunks_deleted": chunks_deleted,
        }

    def _walk(self, worktree: Path) -> list[Path]:
        return [path for path in worktree.rglob("*") if path.is_file()]

    def _renamed_content_unchanged(
        self,
        project_id: str,
        branch: str,
        old_path: str,
        new_path: Path,
    ) -> bool:
        indexed_hash = self.index.file_hash(self.settings.tenant_id, project_id, branch, old_path)
        if not indexed_hash:
            return False
        return indexed_hash == content_hash(new_path.read_bytes())

    def _index_repo(self, project: GitLabProject, branch: str, commit_sha: str, status: str) -> None:
        metadata = self.repo_metadata.get(project) if self.repo_metadata else None
        self.index.index_repo(
            {
                "repo_id": stable_id(self.settings.tenant_id, project.gitlab_project_id, branch),
                "gitlab_project_id": project.gitlab_project_id,
                "repo_path_with_namespace": project.repo_path_with_namespace,
                "repo_name": project.repo_name,
                "default_branch": project.default_branch,
                "indexed_branch": branch,
                "active_commit_sha": commit_sha,
                "last_indexed_commit_sha": commit_sha,
                "last_successful_index_at": utcnow().isoformat(),
                "description": project.description,
                "team_owner": metadata.team_owner if metadata else None,
                "business_domain": metadata.business_domain if metadata else None,
                "service_name": metadata.service_name if metadata else None,
                "slack_channel": metadata.slack_channel if metadata else None,
                "jira_project": metadata.jira_project if metadata else None,
                "primary_language": metadata.primary_language if metadata else None,
                "service_type": metadata.service_type if metadata else None,
                "deployment_name": metadata.deployment_name if metadata else None,
                "tags": metadata.tags if metadata else [],
                "index_status": status,
            }
        )

    def _job(
        self,
        job_type: str,
        project: GitLabProject,
        branch: str,
        old_sha: str | None,
        new_sha: str,
        started_at: datetime,
    ) -> IndexJobResult:
        return IndexJobResult(
            job_id=stable_id(job_type, project.gitlab_project_id, branch, old_sha, new_sha),
            job_type=job_type,
            gitlab_project_id=project.gitlab_project_id,
            repo_path_with_namespace=project.repo_path_with_namespace,
            branch=branch,
            old_sha=old_sha,
            new_sha=new_sha,
            status="running",
            started_at=started_at,
            finished_at=started_at,
        )
