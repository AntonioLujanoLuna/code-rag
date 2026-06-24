"""Shared Elasticsearch connection, index lifecycle, and document helpers.

``ElasticsearchCodeIndex`` is composed from focused mixins (search, indexing,
job store) that all build on this base. Splitting the formerly 900-line adapter
this way keeps each concern in its own module while the facade still implements
the combined search/job-store/repo-store ports the rest of the app depends on.
"""

from __future__ import annotations

from typing import Any

try:
    from elasticsearch import ConflictError, Elasticsearch, helpers
except ImportError:  # pragma: no cover - exercised only without the optional dep
    ConflictError = None  # type: ignore[assignment,misc]
    Elasticsearch = None  # type: ignore[assignment,misc]
    helpers = None  # type: ignore[assignment]

from code_rag.adapters.elasticsearch import mappings
from code_rag.config.settings import Settings
from code_rag.config.tracing import get_tracer
from code_rag.domain.models import FileMetadata, IndexJobRecord, JobStatus, SearchHit

tracer = get_tracer(__name__)

# Conflict errors only occur when the elasticsearch package is installed, so an
# empty tuple (no package) safely matches nothing. This lets callers write a
# narrow ``except _CONFLICT_ERRORS`` instead of catching every ``Exception`` and
# re-checking the type.
_CONFLICT_ERRORS: tuple[type[BaseException], ...] = (
    (ConflictError,) if ConflictError is not None else ()
)


class EsClientBase:
    """Holds the Elasticsearch client, index names, and shared helpers."""

    def __init__(self, settings: Settings) -> None:
        if Elasticsearch is None:
            raise RuntimeError(
                "The elasticsearch package is required to use ElasticsearchCodeIndex"
            )
        self.settings = settings
        kwargs: dict[str, Any] = {}
        if settings.elasticsearch_api_key:
            kwargs["api_key"] = settings.elasticsearch_api_key
        self.client = Elasticsearch(settings.elasticsearch_url, **kwargs)

    # --- Alias names (used for all reads and writes) ---

    @property
    def chunks_index(self) -> str:
        return f"{self.settings.index_prefix}code_chunks"

    @property
    def symbols_index(self) -> str:
        return f"{self.settings.index_prefix}code_symbols"

    @property
    def edges_index(self) -> str:
        return f"{self.settings.index_prefix}code_edges"

    @property
    def communities_index(self) -> str:
        return f"{self.settings.index_prefix}code_communities"

    @property
    def files_index(self) -> str:
        return f"{self.settings.index_prefix}code_files"

    @property
    def repos_index(self) -> str:
        return f"{self.settings.index_prefix}code_repos"

    @property
    def jobs_index(self) -> str:
        return f"{self.settings.index_prefix}code_index_jobs"

    @property
    def job_status_index(self) -> str:
        return f"{self.settings.index_prefix}code_job_status"

    # --- Versioned backing index names ---

    def _backing(self, alias: str) -> str:
        return f"{alias}_v{self.settings.index_version}"

    def _index_specs(self) -> list[tuple[str, dict]]:
        """Return ``(alias, mapping)`` pairs for every managed index."""
        dim = self.settings.embedding_dimension
        return [
            (self.chunks_index, mappings.chunks_mapping(dim)),
            (self.symbols_index, mappings.symbols_mapping()),
            (self.edges_index, mappings.edges_mapping()),
            (self.communities_index, mappings.communities_mapping(dim)),
            (self.files_index, mappings.files_mapping()),
            (self.repos_index, mappings.repos_mapping()),
            (self.jobs_index, mappings.jobs_mapping()),
            (self.job_status_index, mappings.job_status_mapping()),
        ]

    def ensure_indices(self) -> None:
        for alias, mapping in self._index_specs():
            self._ensure(alias, self._backing(alias), mapping)

    def reindex(self, only: str | None = None) -> dict[str, int]:
        """Migrate managed indices to the current ``index_version``.

        For each alias (optionally restricted to ``only``) this creates the
        current-version backing index from its mapping, copies documents from
        the alias's existing backing into it, and atomically swaps the alias.
        Returns a per-alias count of documents reindexed. Safe to re-run: an
        alias already pointing at the current backing is skipped.
        """
        if helpers is None:  # pragma: no cover - requires the optional dep
            raise RuntimeError("The elasticsearch package is required for reindexing")
        results: dict[str, int] = {}
        for alias, mapping in self._index_specs():
            if only and alias != only:
                continue
            results[alias] = self._reindex_one(alias, mapping)
        return results

    def _reindex_one(self, alias: str, mapping: dict) -> int:
        new_backing = self._backing(alias)
        if not self.client.indices.exists(index=new_backing):
            self.client.indices.create(
                index=new_backing, mappings=mapping["mappings"], settings=mapping["settings"]
            )
        if not self.client.indices.exists_alias(name=alias):
            self.client.indices.put_alias(index=new_backing, name=alias)
            return 0
        current_backings = list(self.client.indices.get_alias(name=alias).keys())
        if current_backings == [new_backing]:
            return 0
        response = self.client.reindex(
            body={"source": {"index": alias}, "dest": {"index": new_backing}},
            wait_for_completion=True,
            refresh=True,
        )
        for old_backing in current_backings:
            if old_backing != new_backing:
                self.swap_alias(alias, old_backing, new_backing)
        return int(response.get("total", 0))

    def ping(self) -> bool:
        """Return True if the Elasticsearch cluster is reachable."""
        return bool(self.client.ping())

    def refresh_search_indices(self) -> None:
        """Make recent writes visible (chunks/symbols/edges are bulk-indexed
        with refresh disabled; community detection reads them back)."""
        self.client.indices.refresh(
            index=f"{self.chunks_index},{self.symbols_index},{self.edges_index}"
        )

    def swap_alias(self, alias: str, old_backing: str, new_backing: str) -> None:
        """Atomically move an alias from one backing index to another."""
        self.client.indices.update_aliases(
            body={
                "actions": [
                    {"remove": {"index": old_backing, "alias": alias}},
                    {"add": {"index": new_backing, "alias": alias}},
                ]
            }
        )

    def _ensure(self, alias: str, backing: str, mapping: dict) -> None:
        if not self.client.indices.exists(index=backing):
            self.client.indices.create(
                index=backing, mappings=mapping["mappings"], settings=mapping["settings"]
            )
        if not self.client.indices.exists_alias(name=alias):
            self.client.indices.put_alias(index=backing, name=alias)

    def _scan(self, index: str, query: dict, batch_size: int = 1_000) -> list[dict]:
        if helpers is None:
            raise RuntimeError("The elasticsearch package is required for scanning")
        return [
            doc["_source"]
            for doc in helpers.scan(
                self.client, index=index, query={"query": query}, size=batch_size
            )
        ]

    # --- Query filter builders ---

    def _filters(self, filters: dict) -> list[dict]:
        clauses = [
            {"term": {"tenant_id": filters["tenant_id"]}},
            {"term": {"branch": filters["branch"]}},
            {"term": {"active_snapshot": True}},
            {
                "terms": {
                    "gitlab_project_id": [str(item) for item in filters["allowed_project_ids"]]
                }
            },
        ]
        repo_paths = filters.get("repo_paths_with_namespace")
        if repo_paths:
            clauses.append({"terms": {"repo_path_with_namespace": repo_paths}})
        return clauses

    def _edge_filters(self, filters: dict) -> list[dict]:
        clauses = [
            {"term": {"tenant_id": filters["tenant_id"]}},
            {"term": {"branch": filters["branch"]}},
            {
                "terms": {
                    "source_repo_project_id": [str(item) for item in filters["allowed_project_ids"]]
                }
            },
        ]
        repo_paths = filters.get("repo_paths_with_namespace")
        if repo_paths:
            clauses.append({"terms": {"source_repo_path_with_namespace": repo_paths}})
        return clauses

    def _symbol_filters(self, filters: dict) -> list[dict]:
        clauses = [
            {"term": {"tenant_id": filters["tenant_id"]}},
            {"term": {"branch": filters["branch"]}},
            {
                "terms": {
                    "gitlab_project_id": [str(item) for item in filters["allowed_project_ids"]]
                }
            },
        ]
        repo_paths = filters.get("repo_paths_with_namespace")
        if repo_paths:
            clauses.append({"terms": {"repo_path_with_namespace": repo_paths}})
        return clauses

    def _community_filters(self, filters: dict) -> list[dict]:
        clauses = [
            {"term": {"tenant_id": filters["tenant_id"]}},
            {"term": {"branch": filters["branch"]}},
            {
                "terms": {
                    "gitlab_project_id": [str(item) for item in filters["allowed_project_ids"]]
                }
            },
        ]
        repo_paths = filters.get("repo_paths_with_namespace")
        if repo_paths:
            clauses.append({"terms": {"repo_path_with_namespace": repo_paths}})
        return clauses

    def _chunk_ids_query(self, chunk_ids: list[str], filters: dict) -> dict:
        return {
            "bool": {
                "filter": [
                    {"ids": {"values": chunk_ids}},
                    *self._filters(filters),
                ]
            }
        }

    # --- Document <-> model mapping ---

    def _hit(self, item: dict) -> SearchHit:
        source = item["_source"]
        return SearchHit(
            chunk_id=source["chunk_id"],
            score=float(item.get("_score") or 0.0),
            repo_path_with_namespace=source["repo_path_with_namespace"],
            file_path=source["file_path"],
            line_start=int(source["line_start"]),
            line_end=int(source["line_end"]),
            language=source["language"],
            chunk_kind=source["chunk_kind"],
            symbol_name=source.get("symbol_name"),
            symbol_fqn=source.get("symbol_fqn"),
            gitlab_blob_url=source["gitlab_blob_url"],
            text=source["text"],
            metadata={
                "gitlab_project_id": source.get("gitlab_project_id"),
                "branch": source.get("branch"),
                "commit_sha": source.get("commit_sha"),
                "symbol_role": source.get("symbol_role"),
                "repo_name": source.get("repo_name"),
                "team_owner": source.get("team_owner"),
                "business_domain": source.get("business_domain"),
                "service_name": source.get("service_name"),
                "secret_redactions_count": source.get("secret_redactions_count"),
                "embedding_late_interaction": source.get("embedding_late_interaction"),
            },
        )

    def _community_hit(self, item: dict) -> SearchHit:
        source = item["_source"]
        return SearchHit(
            chunk_id=source["community_id"],
            score=float(item.get("_score") or 0.0),
            repo_path_with_namespace=source["repo_path_with_namespace"],
            file_path=(source.get("member_file_paths") or ["<community>"])[0],
            line_start=0,
            line_end=0,
            language=source.get("dominant_language") or "text",
            chunk_kind="community_summary",
            symbol_name=source.get("label"),
            symbol_fqn=None,
            gitlab_blob_url=source.get("representative_gitlab_url") or "",
            text=source.get("summary") or "",
            metadata={
                "gitlab_project_id": source.get("gitlab_project_id"),
                "branch": source.get("branch"),
                "community_size": source.get("size"),
                "community_label": source.get("label"),
                "member_file_paths": source.get("member_file_paths"),
                "is_community": True,
            },
        )

    def _dump(self, model: Any) -> dict:
        data = model.model_dump(mode="json")
        if "file_path" in data:
            data["file_path_text"] = data["file_path"].replace("/", " ")
        if "symbol_name" in data and data.get("symbol_name"):
            data["symbol_name_text"] = data["symbol_name"]
        if "symbol_fqn" in data and data.get("symbol_fqn"):
            data["symbol_fqn_text"] = data["symbol_fqn"].replace(".", " ")
        if "source_symbol_fqn" in data and data.get("source_symbol_fqn"):
            data["source_symbol_text"] = data["source_symbol_fqn"].replace(".", " ")
        if "target_symbol_fqn" in data and data.get("target_symbol_fqn"):
            data["target_symbol_text"] = data["target_symbol_fqn"].replace(".", " ")
        return data

    def _file_id(self, metadata: FileMetadata) -> str:
        return "|".join(
            [
                metadata.tenant_id,
                metadata.gitlab_project_id,
                metadata.branch,
                metadata.file_path,
            ]
        )

    def _job_status(self, record: IndexJobRecord) -> JobStatus:
        return JobStatus(
            job_id=record.job_id,
            job_type=record.job_type,
            status=record.status,
            submitted_at=record.submitted_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            result=record.result,
            error_message=record.error_message,
        )
