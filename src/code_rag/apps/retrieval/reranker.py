from __future__ import annotations

import numpy as np

from code_rag.config.settings import Settings
from code_rag.domain.enums.query_type import QueryType
from code_rag.domain.models import SearchHit
from code_rag.ports.rerank import RerankProvider


class Reranker:
    """Heuristic reranker with configurable boosts and numpy MaxSim scoring.

    An optional cross-encoder ``RerankProvider`` re-scores the strongest fused
    candidates; its scores are min-max normalised and blended into the heuristic
    score so a real reranker can dominate ordering when one is configured, while
    the heuristic remains the deterministic local fallback.
    """

    def __init__(self, settings: Settings, cross_encoder: RerankProvider | None = None) -> None:
        self.settings = settings
        self.cross_encoder = cross_encoder

    def rerank(
        self,
        hits: list[SearchHit],
        query_type: QueryType,
        identifiers: list[str],
        query_late_embedding: list[list[float]],
        query: str = "",
    ) -> list[SearchHit]:
        identifier_text = " ".join(identifiers).lower()
        query_matrix = self._matrix(query_late_embedding)

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
            if identifier_text and any(
                identifier.lower() in haystack for identifier in identifiers
            ):
                value += self.settings.rerank_identifier_boost
            if (
                query_type == QueryType.DEFINITION_LOOKUP
                and hit.metadata.get("symbol_role") == "definition"
            ):
                value += self.settings.rerank_definition_boost
            if query_type == QueryType.USAGE_LOOKUP and hit.metadata.get("edge_match"):
                value += self.settings.rerank_usage_boost
            if query_type == QueryType.TEST_QUESTION and (
                "test" in hit.file_path.lower() or hit.chunk_kind == "test_case"
            ):
                value += self.settings.rerank_test_boost
            if (
                query_type in {QueryType.CONFIG_QUESTION, QueryType.DEPLOYMENT_QUESTION}
                and hit.metadata.get("symbol_role") == "none"
            ):
                value += self.settings.rerank_config_boost
            if hit.metadata.get("graph_expanded"):
                value += self.settings.rerank_graph_neighbor_boost
            if hit.chunk_kind == "community_summary":
                value += self.settings.rerank_community_boost
            late = hit.metadata.get("embedding_late_interaction") or []
            if query_matrix is not None and late:
                similarity = self._maxsim(query_matrix, self._matrix(late))
                value += min(similarity, 1.0) * self.settings.rerank_late_interaction_weight
            return value

        for hit in hits:
            hit.score = score(hit)
        self._apply_cross_encoder(query, hits)
        return sorted(hits, key=lambda hit: hit.score, reverse=True)

    def _apply_cross_encoder(self, query: str, hits: list[SearchHit]) -> None:
        if not query or self.cross_encoder is None or not self.cross_encoder.enabled:
            return
        candidates = hits[: self.settings.rerank_cross_encoder_candidates]
        scores = self.cross_encoder.score(query, [hit.text for hit in candidates])
        if len(scores) != len(candidates):
            return
        lo, hi = min(scores), max(scores)
        span = hi - lo or 1.0
        weight = self.settings.rerank_cross_encoder_weight
        for hit, raw in zip(candidates, scores, strict=True):
            hit.score += weight * (raw - lo) / span
            hit.metadata["cross_encoder_score"] = raw

    def _matrix(self, vectors: list[list[float]]) -> np.ndarray | None:
        if not vectors:
            return None
        return np.asarray(vectors[:128], dtype=np.float64)

    def _maxsim(self, query_matrix: np.ndarray, document_matrix: np.ndarray | None) -> float:
        if document_matrix is None or query_matrix.size == 0 or document_matrix.size == 0:
            return 0.0
        query = query_matrix[:32]
        # For each query token vector, take the max dot product over document tokens.
        similarities = query @ document_matrix.T
        return float(similarities.max(axis=1).mean())
