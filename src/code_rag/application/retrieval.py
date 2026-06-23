from __future__ import annotations

import re

from code_rag.models import QueryType, SearchHit, SearchRequest, SearchResponse
from code_rag.ports.embedding import EmbeddingProvider
from code_rag.ports.search import SearchIndexPort
from code_rag.settings import Settings
from code_rag.application.permissions import PermissionService


IDENTIFIER_RE = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9_]+|[a-zA-Z_][\w]*(?:\.[a-zA-Z_][\w]*)+|/[A-Za-z0-9_./-]+|[A-Z0-9_]{3,})\b"
)
IDENTIFIER_STOP_WORDS = {
    "A",
    "An",
    "And",
    "Are",
    "Can",
    "Does",
    "How",
    "Is",
    "The",
    "What",
    "When",
    "Where",
    "Which",
    "Who",
    "Why",
}


class QueryClassifier:
    def classify(self, query: str) -> QueryType:
        q = query.lower()
        if any(term in q for term in ("where is", "implemented", "defined", "source", "owner")):
            return QueryType.DEFINITION_LOOKUP
        if any(term in q for term in ("who calls", "where used", "references", "uses ", "called by")):
            return QueryType.USAGE_LOOKUP
        if any(term in q for term in ("endpoint", "route", "api", "http")):
            return QueryType.API_QUESTION
        if any(term in q for term in ("config", "setting", "environment", "env var", "property")):
            return QueryType.CONFIG_QUESTION
        if any(term in q for term in ("test", "spec", "coverage")):
            return QueryType.TEST_QUESTION
        if any(term in q for term in ("deploy", "helm", "kubernetes", "docker")):
            return QueryType.DEPLOYMENT_QUESTION
        if any(term in q for term in ("debug", "error", "exception", "traceback", "bug")):
            return QueryType.DEBUGGING_QUESTION
        if any(term in q for term in ("migration", "schema", "table")):
            return QueryType.MIGRATION_QUESTION
        if any(term in q for term in ("architecture", "flow", "how does", "explain")):
            return QueryType.ARCHITECTURE_QUESTION
        return QueryType.ARCHITECTURE_QUESTION

    def identifiers(self, query: str) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for match in IDENTIFIER_RE.findall(query):
            value = match.strip("`'\"")
            if value in IDENTIFIER_STOP_WORDS:
                continue
            if value and value not in seen:
                seen.add(value)
                result.append(value)
        return result


class RetrievalService:
    def __init__(
        self,
        settings: Settings,
        index: SearchIndexPort,
        embeddings: EmbeddingProvider,
        permissions: PermissionService | None = None,
        classifier: QueryClassifier | None = None,
    ) -> None:
        self.settings = settings
        self.index = index
        self.embeddings = embeddings
        self.permissions = permissions
        self.classifier = classifier or QueryClassifier()

    def search(self, request: SearchRequest) -> SearchResponse:
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
        lexical_hits = self.index.lexical_search(request.query, filters, request.top_k * 2)
        query_embedding = self.embeddings.embed_query(request.query)
        vector_hits = self.index.vector_search(query_embedding.dense, filters, request.top_k * 2)
        symbol_hits = self.index.symbol_search(identifiers, filters, request.top_k)
        edge_hits = self.index.edge_search(identifiers, filters, request.top_k * 2)
        hits = self._rerank(
            self._rrf([symbol_hits, edge_hits, lexical_hits, vector_hits]),
            query_type,
            identifiers,
            query_embedding.late_interaction,
        )[: request.top_k]
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

    def _rerank(
        self,
        hits: list[SearchHit],
        query_type: QueryType,
        identifiers: list[str],
        query_late_embedding: list[list[float]],
    ) -> list[SearchHit]:
        identifier_text = " ".join(identifiers).lower()

        def score(hit: SearchHit) -> float:
            value = hit.score
            haystack = " ".join(
                [
                    hit.symbol_name or "",
                    hit.symbol_fqn or "",
                    hit.file_path,
                    hit.repo_path_with_namespace,
                ]
            ).lower()
            if identifier_text and any(identifier.lower() in haystack for identifier in identifiers):
                value += 0.15
            if query_type == QueryType.DEFINITION_LOOKUP and hit.metadata.get("symbol_role") == "definition":
                value += 0.2
            if query_type == QueryType.USAGE_LOOKUP and hit.metadata.get("edge_match"):
                value += 0.2
            if query_type == QueryType.TEST_QUESTION and (
                "test" in hit.file_path.lower() or hit.chunk_kind == "test_case"
            ):
                value += 0.15
            if query_type in {QueryType.CONFIG_QUESTION, QueryType.DEPLOYMENT_QUESTION} and hit.metadata.get(
                "symbol_role"
            ) == "none":
                value += 0.05
            late = hit.metadata.get("embedding_late_interaction") or []
            if query_late_embedding and late:
                value += min(self._maxsim(query_late_embedding, late), 1.0) * 0.1
            return value

        return sorted(hits, key=score, reverse=True)

    def _maxsim(self, query_vectors: list[list[float]], document_vectors: list[list[float]]) -> float:
        if not query_vectors or not document_vectors:
            return 0.0
        total = 0.0
        for query_vector in query_vectors[:32]:
            total += max(self._dot(query_vector, document_vector) for document_vector in document_vectors[:128])
        return total / max(len(query_vectors[:32]), 1)

    def _dot(self, left: list[float], right: list[float]) -> float:
        return sum(a * b for a, b in zip(left, right, strict=False))

    def _context(self, hits: list[SearchHit]) -> str:
        blocks: list[str] = []
        for index, hit in enumerate(hits, start=1):
            snippet = hit.text
            if len(snippet) > 2500:
                snippet = snippet[:2500].rstrip() + "\n..."
            blocks.append(
                "\n".join(
                    [
                        f"[{index}] {hit.repo_path_with_namespace}:{hit.file_path}:{hit.line_start}-{hit.line_end}",
                        f"Source: {hit.gitlab_blob_url}",
                        snippet,
                    ]
                )
            )
        return "\n\n---\n\n".join(blocks)
