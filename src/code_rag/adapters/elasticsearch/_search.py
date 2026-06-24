"""Query-time search methods for the Elasticsearch adapter."""

from __future__ import annotations

from code_rag.adapters.elasticsearch._base import EsClientBase, tracer
from code_rag.domain.models import CodeEdge, CodeSymbol, SearchHit


class SearchMixin(EsClientBase):
    """BM25, vector, symbol, edge, neighbour, and community search."""

    def lexical_search(self, query: str, filters: dict, size: int) -> list[SearchHit]:
        with tracer.start_as_current_span("es.lexical_search"):
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
        with tracer.start_as_current_span("es.vector_search"):
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
        with tracer.start_as_current_span("es.symbol_search"):
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
                                    "fields": [
                                        "symbol_name_text^3",
                                        "symbol_fqn_text^2",
                                        "signature",
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
        with tracer.start_as_current_span("es.edge_search"):
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
