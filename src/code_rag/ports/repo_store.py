from __future__ import annotations

from typing import Protocol


class RepoStorePort(Protocol):
    def index_repo(self, repo_doc: dict) -> None:
        """Upsert repository metadata."""
