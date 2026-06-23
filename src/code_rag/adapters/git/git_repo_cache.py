from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from threading import RLock

from code_rag.config.settings import Settings
from code_rag.domain.models import GitLabProject

logger = logging.getLogger(__name__)


class GitRepoCache:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.cache_dir = settings.clone_cache_dir
        self.worktree_dir = settings.worktree_dir
        self._locks: dict[str, RLock] = {}
        self._locks_guard = RLock()

    def checkout(self, project: GitLabProject, branch: str, commit_sha: str | None = None) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.worktree_dir.mkdir(parents=True, exist_ok=True)
        repo_key = self._repo_key(project)
        bare_repo = self.cache_dir / f"{repo_key}.git"
        revision = commit_sha or f"refs/heads/{branch}"
        worktree = Path(tempfile.mkdtemp(prefix=f"{repo_key}__", dir=self.worktree_dir))

        with self._repo_lock(repo_key):
            if not bare_repo.exists():
                self._run(["git", "clone", "--mirror", project.repo_url, str(bare_repo)])
            else:
                self._run(["git", "--git-dir", str(bare_repo), "fetch", "--prune", "origin"])
            self._run(["git", "clone", str(bare_repo), str(worktree)])
            self._run(["git", "checkout", revision], cwd=worktree)
        return worktree

    def head_sha(self, worktree: Path) -> str:
        return self._run(["git", "rev-parse", "HEAD"], cwd=worktree).strip()

    def changed_files(self, worktree: Path, old_sha: str, new_sha: str) -> list[str]:
        output = self._run(["git", "diff", "--name-only", old_sha, new_sha], cwd=worktree)
        return [line.strip() for line in output.splitlines() if line.strip()]

    def cleanup(self, worktree: Path) -> None:
        try:
            root = self.worktree_dir.resolve()
            target = worktree.resolve()
            if target == root or not target.is_relative_to(root):
                raise ValueError(f"Refusing to remove worktree outside cache directory: {target}")
            if target.exists():
                shutil.rmtree(target)
        except Exception:
            logger.warning("Failed to clean up worktree %s", worktree, exc_info=True)

    def _run(self, args: list[str], cwd: Path | None = None) -> str:
        completed = subprocess.run(
            args,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return completed.stdout

    def _repo_key(self, project: GitLabProject) -> str:
        return (
            project.repo_path_with_namespace.replace("/", "__")
            .replace("\\", "__")
            .replace(":", "_")
        )

    def _repo_lock(self, repo_key: str) -> RLock:
        with self._locks_guard:
            lock = self._locks.get(repo_key)
            if lock is None:
                lock = RLock()
                self._locks[repo_key] = lock
            return lock
