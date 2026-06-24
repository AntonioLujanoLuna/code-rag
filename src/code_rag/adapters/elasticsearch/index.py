from __future__ import annotations

from typing import Any

try:
    from elasticsearch import Elasticsearch, helpers
except ImportError:  # pragma: no cover - exercised only without the optional dep
    Elasticsearch = None  # type: ignore[assignment,misc]
    helpers = None  # type: ignore[assignment]

from code_rag.adapters.elasticsearch import mappings
from code_rag.config.settings import Settings
from code_rag.domain.models import (
    CodeChunk,
    CodeCommunity,
    CodeEdge,
    CodeSymbol,
    FileMetadata,
    IndexJobResult,
    JobStatus,
    SearchHit,
)


class ElasticsearchCodeIndex:
    """Elasticsearch adapter implementing the search, job-store and repo-store ports."""

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

    def ensure_indices(self) -> None:
        self._ensure(
            self.chunks_index,
            self._backing(self.chunks_index),
            mappings.chunks_mapping(self.settings.embedding_dimension),
        )
        self._ensure(
            self.symbols_index, self._backing(self.symbols_index), mappings.symbols_mapping()
        )
        self._ensure(self.edges_index, self._backing(self.edges_index), mappings.edges_mapping())
        self._ensure(
            self.communities_index,
            self._backing(self.communities_index),
            mappings.communities_mapping(self.settings.embedding_dimension),
        )
        self._ensure(self.files_index, self._backing(self.files_index), mappings.files_mapping())
        self._ensure(self.repos_index, self._backing(self.repos_index), mappings.repos_mapping())
        self._ensure(self.jobs_index, self._backing(self.jobs_index), mappings.jobs_mapping())
        self._ensure(
            self.job_status_index,
            self._backing(self.job_status_index),
            mappings.job_status_mapping(),
        )

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

    def replace_file(
        self,
        file_metadata: FileMetadata,
        chunks: list[CodeChunk],
        symbols: list[CodeSymbol],
        edges: list[CodeEdge],
    ) -> tuple[int, int]:
        deleted = self.delete_file(
            file_metadata.tenant_id,
            file_metadata.gitlab_project_id,
            file_metadata.branch,
            file_metadata.file_path,
        )
        actions: list[dict[str, Any]] = []
        actions.append(
            {
                "_op_type": "index",
                "_index": self.files_index,
                "_id": self._file_id(file_metadata),
                "_source": {
                    **self._dump(file_metadata),
                    "defined_symbols": [symbol.symbol_fqn for symbol in symbols],
                    "referenced_symbols": sorted(
                        {symbol for chunk in chunks for symbol in chunk.references_symbols}
                    ),
                    "imports": sorted({item for chunk in chunks for item in chunk.imports}),
                    "chunk_ids": [chunk.chunk_id for chunk in chunks],
                    "file_summary": None,
                    "indexed_at": chunks[0].indexed_at.isoformat() if chunks else None,
                },
            }
        )
        actions.extend(
            {
                "_op_type": "index",
                "_index": self.chunks_index,
                "_id": chunk.chunk_id,
                "_source": self._dump(chunk),
            }
            for chunk in chunks
        )
        actions.extend(
            {
                "_op_type": "index",
                "_index": self.symbols_index,
                "_id": symbol.symbol_id,
                "_source": self._dump(symbol),
            }
            for symbol in symbols
        )
        actions.extend(
            {
                "_op_type": "index",
                "_index": self.edges_index,
                "_id": edge.edge_id,
                "_source": self._dump(edge),
            }
            for edge in edges
        )
        if actions:
            if helpers is None:
                raise RuntimeError("The elasticsearch package is required for bulk indexing")
            helpers.bulk(self.client, actions, refresh=False)
        return len(chunks), deleted

    def delete_file(self, tenant_id: str, project_id: str, branch: str, file_path: str) -> int:
        query = {
            "bool": {
                "filter": [
                    {"term": {"tenant_id": tenant_id}},
                    {"term": {"gitlab_project_id": str(project_id)}},
                    {"term": {"branch": branch}},
                    {"term": {"file_path": file_path}},
                ]
            }
        }
        deleted = 0
        for index in (self.chunks_index, self.files_index):
            result = self.client.delete_by_query(index=index, query=query, conflicts="proceed")
            deleted += int(result.get("deleted", 0))
        symbol_query = {
            "bool": {
                "filter": [
                    {"term": {"tenant_id": tenant_id}},
                    {"term": {"gitlab_project_id": str(project_id)}},
                    {"term": {"branch": branch}},
                    {"term": {"definition_file_path": file_path}},
                ]
            }
        }
        result = self.client.delete_by_query(
            index=self.symbols_index, query=symbol_query, conflicts="proceed"
        )
        deleted += int(result.get("deleted", 0))
        edge_query = {
            "bool": {
                "filter": [
                    {"term": {"tenant_id": tenant_id}},
                    {"term": {"branch": branch}},
                    {"term": {"source_repo_project_id": str(project_id)}},
                ],
                "should": [
                    {"term": {"source_file_path": file_path}},
                    {"term": {"target_file_path": file_path}},
                ],
                "minimum_should_match": 1,
            }
        }
        self.client.delete_by_query(index=self.edges_index, query=edge_query, conflicts="proceed")
        return deleted

    def existing_embeddings(self, chunk_ids: list[str]) -> dict[str, dict]:
        if not chunk_ids:
            return {}
        response = self.client.mget(
            index=self.chunks_index,
            ids=chunk_ids,
            source=["embedding_input_hash", "embedding_dense", "embedding_late_interaction"],
        )
        result: dict[str, dict] = {}
        for doc in response.get("docs", []):
            if doc.get("found"):
                result[doc["_id"]] = doc.get("_source", {})
        return result

    def index_repo(self, repo_doc: dict) -> None:
        repo_id = repo_doc["repo_id"]
        self.client.index(index=self.repos_index, id=repo_id, document=repo_doc)

    def record_job(self, job: IndexJobResult) -> None:
        self.client.index(index=self.jobs_index, id=job.job_id, document=self._dump(job))

    def get_job(self, job_id: str) -> IndexJobResult | None:
        if not self.client.exists(index=self.jobs_index, id=job_id):
            return None
        response = self.client.get(index=self.jobs_index, id=job_id)
        return IndexJobResult.model_validate(response["_source"])

    def record_job_status(self, status: JobStatus) -> None:
        self.client.index(
            index=self.job_status_index, id=status.job_id, document=status.model_dump(mode="json")
        )

    def get_job_status(self, job_id: str) -> JobStatus | None:
        if not self.client.exists(index=self.job_status_index, id=job_id):
            return None
        response = self.client.get(index=self.job_status_index, id=job_id)
        return JobStatus.model_validate(response["_source"])

    def file_hash(self, tenant_id: str, project_id: str, branch: str, file_path: str) -> str | None:
        response = self.client.search(
            index=self.files_index,
            query={
                "bool": {
                    "filter": [
                        {"term": {"tenant_id": tenant_id}},
                        {"term": {"gitlab_project_id": str(project_id)}},
                        {"term": {"branch": branch}},
                        {"term": {"file_path": file_path}},
                    ]
                }
            },
            size=1,
        )
        hits = response["hits"]["hits"]
        return hits[0]["_source"].get("file_hash") if hits else None

    def lexical_search(self, query: str, filters: dict, size: int) -> list[SearchHit]:
        bool_query = {
            "bool": {
                "filter": self._filters(filters),
                "must": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": [
                                "text^3",
                                "symbol_name_text^4",
                                "symbol_fqn_text^4",
                                "file_path_text^2",
                                "repo_name^1.5",
                                "summary",
                            ],
                            "type": "best_fields",
                            "operator": "or",
                        }
                    }
                ],
            }
        }
        response = self.client.search(index=self.chunks_index, query=bool_query, size=size)
        return [self._hit(item) for item in response["hits"]["hits"]]

    def vector_search(self, vector: list[float], filters: dict, size: int) -> list[SearchHit]:
        if not vector:
            return []
        response = self.client.search(
            index=self.chunks_index,
            knn={
                "field": "embedding_dense",
                "query_vector": vector,
                "k": size,
                "num_candidates": max(size * 8, 50),
                "filter": self._filters(filters),
            },
            size=size,
        )
        return [self._hit(item) for item in response["hits"]["hits"]]

    def symbol_search(self, identifiers: list[str], filters: dict, size: int) -> list[SearchHit]:
        if not identifiers:
            return []
        response = self.client.search(
            index=self.symbols_index,
            query={
                "bool": {
                    "filter": self._symbol_filters(filters),
                    "should": [
                        {"terms": {"symbol_name": identifiers}},
                        {"terms": {"symbol_fqn": identifiers}},
                        {
                            "multi_match": {
                                "query": " ".join(identifiers),
                                "fields": ["symbol_name_text^3", "symbol_fqn_text^2", "signature"],
                            }
                        },
                    ],
                    "minimum_should_match": 1,
                }
            },
            size=size,
        )
        chunk_ids = [
            item["_source"]["definition_chunk_id"]
            for item in response["hits"]["hits"]
            if item["_source"]
        ]
        if not chunk_ids:
            return []
        chunk_response = self.client.search(
            index=self.chunks_index,
            query=self._chunk_ids_query(chunk_ids, filters),
            size=len(chunk_ids),
        )
        return [self._hit(item) for item in chunk_response["hits"]["hits"]]

    def edge_search(self, identifiers: list[str], filters: dict, size: int) -> list[SearchHit]:
        if not identifiers:
            return []
        response = self.client.search(
            index=self.edges_index,
            query={
                "bool": {
                    "filter": self._edge_filters(filters),
                    "should": [
                        {"terms": {"source_symbol_fqn": identifiers}},
                        {"terms": {"target_symbol_fqn": identifiers}},
                        {
                            "multi_match": {
                                "query": " ".join(identifiers),
                                "fields": [
                                    "source_symbol_text^2",
                                    "target_symbol_text^3",
                                    "edge_type",
                                ],
                            }
                        },
                    ],
                    "minimum_should_match": 1,
                }
            },
            size=size,
        )
        chunk_ids = [
            item["_source"]["source_symbol_id"]
            for item in response["hits"]["hits"]
            if item["_source"].get("source_symbol_id")
        ]
        if not chunk_ids:
            return []
        chunk_response = self.client.search(
            index=self.chunks_index,
            query=self._chunk_ids_query(chunk_ids, filters),
            size=len(chunk_ids),
        )
        hits = [self._hit(item) for item in chunk_response["hits"]["hits"]]
        for hit in hits:
            hit.metadata["edge_match"] = True
        return hits

    def neighbor_chunks(
        self, symbol_fqns: list[str], edge_types: list[str], filters: dict, size: int
    ) -> list[SearchHit]:
        if not symbol_fqns or size <= 0:
            return []
        should = [
            {"terms": {"source_symbol_fqn": symbol_fqns}},
            {"terms": {"target_symbol_fqn": symbol_fqns}},
        ]
        edge_filters = self._edge_filters(filters)
        if edge_types:
            edge_filters = [*edge_filters, {"terms": {"edge_type": edge_types}}]
        response = self.client.search(
            index=self.edges_index,
            query={
                "bool": {
                    "filter": edge_filters,
                    "should": should,
                    "minimum_should_match": 1,
                }
            },
            size=max(size * 5, 25),
        )
        seeds = set(symbol_fqns)
        neighbor_fqns: list[str] = []
        for item in response["hits"]["hits"]:
            source = item["_source"]
            for candidate in (source.get("source_symbol_fqn"), source.get("target_symbol_fqn")):
                if candidate and candidate not in seeds and candidate not in neighbor_fqns:
                    neighbor_fqns.append(candidate)
        if not neighbor_fqns:
            return []
        # Resolve neighbour FQNs to their definition chunks via the symbols index,
        # which spans all allowed projects so neighbours can be cross-repository.
        symbol_response = self.client.search(
            index=self.symbols_index,
            query={
                "bool": {
                    "filter": self._symbol_filters(filters),
                    "should": [
                        {"terms": {"symbol_fqn": neighbor_fqns}},
                        {"terms": {"symbol_name": [f.rsplit(".", 1)[-1] for f in neighbor_fqns]}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            size=max(size * 2, 20),
        )
        chunk_ids = [
            item["_source"]["definition_chunk_id"]
            for item in symbol_response["hits"]["hits"]
            if item["_source"].get("definition_chunk_id")
        ]
        if not chunk_ids:
            return []
        chunk_response = self.client.search(
            index=self.chunks_index,
            query=self._chunk_ids_query(chunk_ids, filters),
            size=len(chunk_ids),
        )
        hits = [self._hit(item) for item in chunk_response["hits"]["hits"]][:size]
        for hit in hits:
            hit.metadata["graph_expanded"] = True
        return hits

    def community_search(
        self, query: str, vector: list[float], filters: dict, size: int
    ) -> list[SearchHit]:
        if size <= 0:
            return []
        community_filters = self._community_filters(filters)
        should: list[dict] = [
            {"multi_match": {"query": query, "fields": ["summary^2", "label^3", "label.keyword"]}}
        ]
        if vector:
            should.append(
                {
                    "knn": {
                        "field": "embedding_dense",
                        "query_vector": vector,
                        "num_candidates": max(size * 8, 50),
                    }
                }
            )
        response = self.client.search(
            index=self.communities_index,
            query={
                "bool": {"filter": community_filters, "should": should, "minimum_should_match": 1}
            },
            size=size,
        )
        return [self._community_hit(item) for item in response["hits"]["hits"]]

    def read_graph(
        self, tenant_id: str, project_id: str, branch: str
    ) -> tuple[list[CodeSymbol], list[CodeEdge]]:
        symbol_query = {
            "bool": {
                "filter": [
                    {"term": {"tenant_id": tenant_id}},
                    {"term": {"gitlab_project_id": str(project_id)}},
                    {"term": {"branch": branch}},
                ]
            }
        }
        edge_query = {
            "bool": {
                "filter": [
                    {"term": {"tenant_id": tenant_id}},
                    {"term": {"branch": branch}},
                    {"term": {"source_repo_project_id": str(project_id)}},
                ]
            }
        }
        symbols = [
            CodeSymbol.model_validate(source)
            for source in self._scan(self.symbols_index, symbol_query)
        ]
        edges = [
            CodeEdge.model_validate(source) for source in self._scan(self.edges_index, edge_query)
        ]
        return symbols, edges

    def index_communities(self, communities: list[CodeCommunity]) -> None:
        if not communities:
            return
        if helpers is None:
            raise RuntimeError("The elasticsearch package is required for bulk indexing")
        actions = [
            {
                "_op_type": "index",
                "_index": self.communities_index,
                "_id": community.community_id,
                "_source": self._dump(community),
            }
            for community in communities
        ]
        helpers.bulk(self.client, actions, refresh=False)

    def delete_project_communities(self, tenant_id: str, project_id: str, branch: str) -> int:
        result = self.client.delete_by_query(
            index=self.communities_index,
            query={
                "bool": {
                    "filter": [
                        {"term": {"tenant_id": tenant_id}},
                        {"term": {"gitlab_project_id": str(project_id)}},
                        {"term": {"branch": branch}},
                    ]
                }
            },
            conflicts="proceed",
        )
        return int(result.get("deleted", 0))

    def _scan(self, index: str, query: dict, batch_size: int = 1_000) -> list[dict]:
        if helpers is None:
            raise RuntimeError("The elasticsearch package is required for scanning")
        return [
            doc["_source"]
            for doc in helpers.scan(
                self.client, index=index, query={"query": query}, size=batch_size
            )
        ]

    def prune_orphaned_edges(self, tenant_id: str, project_id: str, branch: str) -> int:
        """Delete edges whose source chunk no longer exists in the chunks index."""
        agg_response = self.client.search(
            index=self.edges_index,
            query={
                "bool": {
                    "filter": [
                        {"term": {"tenant_id": tenant_id}},
                        {"term": {"branch": branch}},
                        {"term": {"source_repo_project_id": str(project_id)}},
                    ]
                }
            },
            aggs={"source_ids": {"terms": {"field": "source_symbol_id", "size": 50_000}}},
            size=0,
        )
        all_source_ids: list[str] = [
            bucket["key"]
            for bucket in agg_response["aggregations"]["source_ids"]["buckets"]
            if bucket["key"]
        ]
        if not all_source_ids:
            return 0
        mget_response = self.client.mget(index=self.chunks_index, ids=all_source_ids, source=False)
        existing_ids = {doc["_id"] for doc in mget_response.get("docs", []) if doc.get("found")}
        orphaned = [sid for sid in all_source_ids if sid not in existing_ids]
        if not orphaned:
            return 0
        result = self.client.delete_by_query(
            index=self.edges_index,
            query={
                "bool": {
                    "filter": [
                        {"term": {"tenant_id": tenant_id}},
                        {"term": {"branch": branch}},
                        {"terms": {"source_symbol_id": orphaned}},
                    ]
                }
            },
            conflicts="proceed",
        )
        return int(result.get("deleted", 0))

    def _ensure(self, alias: str, backing: str, mapping: dict) -> None:
        if not self.client.indices.exists(index=backing):
            self.client.indices.create(
                index=backing, mappings=mapping["mappings"], settings=mapping["settings"]
            )
        if not self.client.indices.exists_alias(name=alias):
            self.client.indices.put_alias(index=backing, name=alias)

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
