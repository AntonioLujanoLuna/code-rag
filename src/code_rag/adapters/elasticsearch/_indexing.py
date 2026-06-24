"""Index-mutation methods for the Elasticsearch adapter.

File replacement/deletion, embedding reuse lookups, repo metadata upserts, and
community persistence/graph maintenance.
"""

from __future__ import annotations

from typing import Any

from code_rag.adapters.elasticsearch._base import EsClientBase, helpers
from code_rag.domain.models import (
    CodeChunk,
    CodeCommunity,
    CodeEdge,
    CodeSymbol,
    FileMetadata,
)


class IndexingMixin(EsClientBase):
    """Write-path operations: file replacement, deletion, and graph maintenance."""

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
