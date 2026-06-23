from __future__ import annotations

import json
import tomllib
from pathlib import Path

from code_rag.config.settings import Settings
from code_rag.domain.models import GitLabProject, RepoMetadata


class RepoMetadataProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._metadata: dict[str, RepoMetadata] | None = None

    def get(self, project: GitLabProject) -> RepoMetadata | None:
        metadata = self._load()
        return metadata.get(project.repo_path_with_namespace)

    def enrich_project(self, project: GitLabProject) -> GitLabProject:
        metadata = self.get(project)
        if metadata and metadata.service_name:
            return project.model_copy(update={"repo_name": metadata.service_name})
        return project

    def _load(self) -> dict[str, RepoMetadata]:
        if self._metadata is not None:
            return self._metadata
        path = self.settings.repo_metadata_path
        if not path or not path.exists():
            self._metadata = {}
            return self._metadata
        data = self._read(path)
        entries = data if isinstance(data, list) else data.get("repos", [])
        metadata: dict[str, RepoMetadata] = {}
        for item in entries:
            record = RepoMetadata.model_validate(item)
            metadata[record.repo_path_with_namespace] = record
        self._metadata = metadata
        return metadata

    def _read(self, path: Path) -> dict | list:
        if path.suffix.lower() == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        if path.suffix.lower() == ".toml":
            return tomllib.loads(path.read_text(encoding="utf-8"))
        raise ValueError("Repo metadata must be JSON or TOML")
