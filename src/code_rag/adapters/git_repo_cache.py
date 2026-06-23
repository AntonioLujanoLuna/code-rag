from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from code_rag.models import GitLabProject
from code_rag.settings import Settings


class GitRepoCache:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.cache_dir = settings.clone_cache_dir
        self.worktree_dir = settings.worktree_dir

    def checkout(self, project: GitLabProject, branch: str, commit_sha: str | None = None) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.worktree_dir.mkdir(parents=True, exist_ok=True)
        repo_key = project.repo_path_with_namespace.replace("/", "__")
        bare_repo = self.cache_dir / f"{repo_key}.git"
        if not bare_repo.exists():
            self._run(["git", "clone", "--mirror", project.repo_url, str(bare_repo)])
        else:
            self._run(["git", "--git-dir", str(bare_repo), "fetch", "--prune", "origin"])

        revision = commit_sha or f"refs/heads/{branch}"
        worktree = self.worktree_dir / repo_key
        if worktree.exists():
            shutil.rmtree(worktree)
        self._run(["git", "clone", str(bare_repo), str(worktree)])
        self._run(["git", "checkout", revision], cwd=worktree)
        return worktree

    def head_sha(self, worktree: Path) -> str:
        return self._run(["git", "rev-parse", "HEAD"], cwd=worktree).strip()

    def changed_files(self, worktree: Path, old_sha: str, new_sha: str) -> list[str]:
        output = self._run(["git", "diff", "--name-only", old_sha, new_sha], cwd=worktree)
        return [line.strip() for line in output.splitlines() if line.strip()]

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

