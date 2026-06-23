from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from code_rag.apps.permissions.permission_service import PermissionService
from code_rag.apps.retrieval.query_classifier import QueryClassifier
from code_rag.apps.retrieval.reranker import Reranker
from code_rag.config.settings import Settings
from code_rag.domain.models import SearchHit, SearchRequest, SearchResponse
from code_rag.ports.embedding import EmbeddingProvider
from code_rag.ports.search import SearchPort

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(
        self,
        settings: Settings,
        index: SearchPort,
        embeddings: EmbeddingProvider,
        permissions: PermissionService | None = None,
        classifier: QueryClassifier | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self.settings = settings
        self.index = index
        self.embeddings = embeddings
        self.permissions = permissions
        self.classifier = classifier or QueryClassifier()
        self.reranker = reranker or Reranker(settings)

    def search(self, request: SearchRequest) -> SearchResponse:
        started = time.perf_counter()
        query_type = self.classifier.classify(request.query)
        identifiers = self.classifier.identifiers(request.query)
        tenant_id = request.tenant_id or self.settings.tenant_id
        allowed_projects = (
            self.permissions.resolve_allowed_projects(
                tenant_id, request.user_id, request.allowed_project_ids
            )
            if self.permissions
            else request.allowed_project_ids
        )
        filters = {
            "tenant_id": tenant_id,
            "branch": request.branch or self.settings.branch,
            "allowed_project_ids": allowed_projects,
            "repo_path_with_namespace": request.repo_path_with_namespace,
        }
        # Run the independent retrieval legs concurrently to cut latency. The
        # dense vector search depends on the query embedding, so it is issued
        # once that future resolves.
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="code-rag-search") as pool:
            lexical_future = pool.submit(
                self.index.lexical_search, request.query, filters, request.top_k * 2
            )
            symbol_future = pool.submit(
                self.index.symbol_search, identifiers, filters, request.top_k
            )
            edge_future = pool.submit(
                self.index.edge_search, identifiers, filters, request.top_k * 2
            )
            embedding_future = pool.submit(self.embeddings.embed_query, request.query)
            query_embedding = embedding_future.result()
            vector_future = pool.submit(
                self.index.vector_search, query_embedding.dense, filters, request.top_k * 2
            )
            lexical_hits = lexical_future.result()
            symbol_hits = symbol_future.result()
            edge_hits = edge_future.result()
            vector_hits = vector_future.result()
        hits = self.reranker.rerank(
            self._rrf([symbol_hits, edge_hits, lexical_hits, vector_hits]),
            query_type,
            identifiers,
            query_embedding.late_interaction,
        )[: request.top_k]
        duration = time.perf_counter() - started
        logger.info(
            "Search completed",
            extra={
                "query_type": query_type.value,
                "hit_count": len(hits),
                "duration_seconds": duration,
                "tenant_id": tenant_id,
            },
        )
        return SearchResponse(
            query=request.query,
            query_type=query_type,
            identifiers=identifiers,
            hits=hits,
            context=self._context(hits),
        )

    def _rrf(self, result_sets: list[list[SearchHit]], k: int = 60) -> list[SearchHit]:
        scores: dict[str, float] = {}
        hits: dict[str, SearchHit] = {}
        for result_set in result_sets:
            for rank, hit in enumerate(result_set, start=1):
                hits.setdefault(hit.chunk_id, hit)
                scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank)
        fused = list(hits.values())
        for hit in fused:
            hit.score = scores[hit.chunk_id]
        return sorted(fused, key=lambda item: item.score, reverse=True)

    def _context(self, hits: list[SearchHit]) -> str:
        blocks: list[str] = []
        for index, hit in enumerate(hits, start=1):
            snippet = hit.text
            if len(snippet) > 2500:
                snippet = snippet[:2500].rstrip() + "\n..."
            location = (
                f"[{index}] {hit.repo_path_with_namespace}:{hit.file_path}"
                f":{hit.line_start}-{hit.line_end}"
            )
            blocks.append(
                "\n".join(
                    [
                        location,
                        f"Source: {hit.gitlab_blob_url}",
                        snippet,
                    ]
                )
            )
        return "\n\n---\n\n".join(blocks)
