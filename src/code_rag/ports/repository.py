from __future__ import annotations

from pathlib import Path
from typing import Protocol

from code_rag.models import GitLabProject


class RepoCachePort(Protocol):
    def checkout(self, project: GitLabProject, branch: str, commit_sha: str | None = None) -> Path:
        """Return a local worktree path checked out at branch or commit."""

    def head_sha(self, worktree: Path) -> str:
        """Return the HEAD commit SHA for a checked-out worktree."""

    def changed_files(self, worktree: Path, old_sha: str, new_sha: str) -> list[str]:
        """Return changed file paths from git diff."""

