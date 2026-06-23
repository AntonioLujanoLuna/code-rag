from __future__ import annotations

from typing import Any

from elasticsearch import Elasticsearch, helpers

from code_rag.models import CodeChunk, CodeEdge, CodeSymbol, FileMetadata, IndexJobResult, SearchHit
from code_rag.settings import Settings


class ElasticsearchCodeIndex:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        kwargs: dict[str, Any] = {}
        if settings.elasticsearch_api_key:
            kwargs["api_key"] = settings.elasticsearch_api_key
        self.client = Elasticsearch(settings.elasticsearch_url, **kwargs)

    @property
    def chunks_index(self) -> str:
        return f"{self.settings.index_prefix}code_chunks_v1"

    @property
    def symbols_index(self) -> str:
        return f"{self.settings.index_prefix}code_symbols_v1"

    @property
    def edges_index(self) -> str:
        return f"{self.settings.index_prefix}code_edges_v1"

    @property
    def files_index(self) -> str:
        return f"{self.settings.index_prefix}code_files_v1"

    @property
    def repos_index(self) -> str:
        return f"{self.settings.index_prefix}code_repos_v1"

    @property
    def jobs_index(self) -> str:
        return f"{self.settings.index_prefix}code_index_jobs_v1"

    def ensure_indices(self) -> None:
        self._ensure(self.chunks_index, self._chunks_mapping())
        self._ensure(self.symbols_index, self._symbols_mapping())
        self._ensure(self.edges_index, self._edges_mapping())
        self._ensure(self.files_index, self._files_mapping())
        self._ensure(self.repos_index, self._repos_mapping())
        self._ensure(self.jobs_index, self._jobs_mapping())

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
        body = {
            "query": {
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
            },
            "size": size,
        }
        response = self.client.search(index=self.chunks_index, **body)
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
            item["_source"]["definition_chunk_id"] for item in response["hits"]["hits"] if item["_source"]
        ]
        if not chunk_ids:
            return []
        chunk_response = self.client.search(
            index=self.chunks_index,
            query={"ids": {"values": chunk_ids}},
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
                                "fields": ["source_symbol_text^2", "target_symbol_text^3", "edge_type"],
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
            query={"ids": {"values": chunk_ids}},
            size=len(chunk_ids),
        )
        hits = [self._hit(item) for item in chunk_response["hits"]["hits"]]
        for hit in hits:
            hit.metadata["edge_match"] = True
        return hits

    def _ensure(self, index: str, mapping: dict) -> None:
        if not self.client.indices.exists(index=index):
            self.client.indices.create(index=index, mappings=mapping["mappings"], settings=mapping["settings"])

    def _chunks_mapping(self) -> dict:
        dim = self.settings.embedding_dimension
        return {
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {
                "dynamic": True,
                "properties": {
                    "tenant_id": {"type": "keyword"},
                    "gitlab_project_id": {"type": "keyword"},
                    "repo_path_with_namespace": {"type": "keyword"},
                    "repo_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "team_owner": {"type": "keyword"},
                    "business_domain": {"type": "keyword"},
                    "service_name": {"type": "keyword"},
                    "slack_channel": {"type": "keyword"},
                    "jira_project": {"type": "keyword"},
                    "service_type": {"type": "keyword"},
                    "deployment_name": {"type": "keyword"},
                    "branch": {"type": "keyword"},
                    "commit_sha": {"type": "keyword"},
                    "active_snapshot": {"type": "boolean"},
                    "file_path": {"type": "keyword"},
                    "file_path_text": {"type": "text"},
                    "language": {"type": "keyword"},
                    "chunk_kind": {"type": "keyword"},
                    "symbol_role": {"type": "keyword"},
                    "symbol_name": {"type": "keyword"},
                    "symbol_name_text": {"type": "text"},
                    "symbol_fqn": {"type": "keyword"},
                    "symbol_fqn_text": {"type": "text"},
                    "text": {"type": "text"},
                    "summary": {"type": "text"},
                    "imports": {"type": "keyword"},
                    "defines_symbols": {"type": "keyword"},
                    "references_symbols": {"type": "keyword"},
                    "calls_symbols": {"type": "keyword"},
                    "secret_findings_count": {"type": "integer"},
                    "secret_redactions_count": {"type": "integer"},
                    "secret_high_confidence_count": {"type": "integer"},
                    "secret_types": {"type": "keyword"},
                    "embedding_dense": {
                        "type": "dense_vector",
                        "dims": dim,
                        "index": True,
                        "similarity": "cosine",
                    },
                    "embedding_late_interaction": {"type": "object", "enabled": False},
                    "indexed_at": {"type": "date"},
                },
            },
        }

    def _symbols_mapping(self) -> dict:
        return {
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {
                "dynamic": True,
                "properties": {
                    "tenant_id": {"type": "keyword"},
                    "gitlab_project_id": {"type": "keyword"},
                    "repo_path_with_namespace": {"type": "keyword"},
                    "branch": {"type": "keyword"},
                    "commit_sha": {"type": "keyword"},
                    "language": {"type": "keyword"},
                    "symbol_name": {"type": "keyword"},
                    "symbol_name_text": {"type": "text"},
                    "symbol_fqn": {"type": "keyword"},
                    "symbol_fqn_text": {"type": "text"},
                    "symbol_kind": {"type": "keyword"},
                    "definition_file_path": {"type": "keyword"},
                    "signature": {"type": "text"},
                    "indexed_at": {"type": "date"},
                },
            },
        }

    def _edges_mapping(self) -> dict:
        return {
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {
                "dynamic": True,
                "properties": {
                    "tenant_id": {"type": "keyword"},
                    "branch": {"type": "keyword"},
                    "commit_sha": {"type": "keyword"},
                    "source_symbol_fqn": {"type": "keyword"},
                    "source_symbol_text": {"type": "text"},
                    "target_symbol_fqn": {"type": "keyword"},
                    "target_symbol_text": {"type": "text"},
                    "source_repo_project_id": {"type": "keyword"},
                    "source_file_path": {"type": "keyword"},
                    "target_file_path": {"type": "keyword"},
                    "edge_type": {"type": "keyword"},
                    "confidence": {"type": "float"},
                    "indexed_at": {"type": "date"},
                },
            },
        }

    def _files_mapping(self) -> dict:
        return {
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {
                "dynamic": True,
                "properties": {
                    "tenant_id": {"type": "keyword"},
                    "gitlab_project_id": {"type": "keyword"},
                    "repo_path_with_namespace": {"type": "keyword"},
                    "branch": {"type": "keyword"},
                    "commit_sha": {"type": "keyword"},
                    "file_path": {"type": "keyword"},
                    "language": {"type": "keyword"},
                    "file_hash": {"type": "keyword"},
                    "team_owner": {"type": "keyword"},
                    "business_domain": {"type": "keyword"},
                    "service_name": {"type": "keyword"},
                    "secret_findings_count": {"type": "integer"},
                    "secret_redactions_count": {"type": "integer"},
                    "defined_symbols": {"type": "keyword"},
                    "chunk_ids": {"type": "keyword"},
                },
            },
        }

    def _repos_mapping(self) -> dict:
        return {
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {
                "dynamic": True,
                "properties": {
                    "repo_id": {"type": "keyword"},
                    "gitlab_project_id": {"type": "keyword"},
                    "repo_path_with_namespace": {"type": "keyword"},
                    "repo_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "indexed_branch": {"type": "keyword"},
                    "active_commit_sha": {"type": "keyword"},
                    "team_owner": {"type": "keyword"},
                    "business_domain": {"type": "keyword"},
                    "service_name": {"type": "keyword"},
                    "slack_channel": {"type": "keyword"},
                    "jira_project": {"type": "keyword"},
                    "primary_language": {"type": "keyword"},
                    "service_type": {"type": "keyword"},
                    "deployment_name": {"type": "keyword"},
                    "tags": {"type": "keyword"},
                    "index_status": {"type": "keyword"},
                    "last_successful_index_at": {"type": "date"},
                },
            },
        }

    def _jobs_mapping(self) -> dict:
        return {
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {
                "dynamic": True,
                "properties": {
                    "job_id": {"type": "keyword"},
                    "job_type": {"type": "keyword"},
                    "gitlab_project_id": {"type": "keyword"},
                    "branch": {"type": "keyword"},
                    "status": {"type": "keyword"},
                    "started_at": {"type": "date"},
                    "finished_at": {"type": "date"},
                },
            },
        }

    def _filters(self, filters: dict) -> list[dict]:
        clauses = [
            {"term": {"tenant_id": filters["tenant_id"]}},
            {"term": {"branch": filters["branch"]}},
            {"term": {"active_snapshot": True}},
            {"terms": {"gitlab_project_id": [str(item) for item in filters["allowed_project_ids"]]}},
        ]
        if filters.get("repo_path_with_namespace"):
            clauses.append({"term": {"repo_path_with_namespace": filters["repo_path_with_namespace"]}})
        return clauses

    def _edge_filters(self, filters: dict) -> list[dict]:
        clauses = [
            {"term": {"tenant_id": filters["tenant_id"]}},
            {"term": {"branch": filters["branch"]}},
            {"terms": {"source_repo_project_id": [str(item) for item in filters["allowed_project_ids"]]}},
        ]
        if filters.get("repo_path_with_namespace"):
            # Edge docs do not carry repo path yet; chunk lookup enforces the same allowed projects.
            pass
        return clauses

    def _symbol_filters(self, filters: dict) -> list[dict]:
        clauses = [
            {"term": {"tenant_id": filters["tenant_id"]}},
            {"term": {"branch": filters["branch"]}},
            {"terms": {"gitlab_project_id": [str(item) for item in filters["allowed_project_ids"]]}},
        ]
        if filters.get("repo_path_with_namespace"):
            clauses.append({"term": {"repo_path_with_namespace": filters["repo_path_with_namespace"]}})
        return clauses

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
