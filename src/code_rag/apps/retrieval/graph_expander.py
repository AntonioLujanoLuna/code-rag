from __future__ import annotations

from code_rag.config.settings import Settings
from code_rag.domain.enums.edge_type import EdgeType
from code_rag.domain.enums.query_type import QueryType
from code_rag.domain.models import SearchHit
from code_rag.ports.search import SearchPort

# Which edge types are most informative to traverse for each kind of question.
# Traversal is direction-agnostic at the storage layer (we match the seed symbol
# as either edge endpoint), so this map only selects *which* relationships to
# follow, e.g. follow TESTS edges for a "where is the test for X" question.
_EDGE_TYPES_BY_QUERY: dict[QueryType, tuple[EdgeType, ...]] = {
    QueryType.DEFINITION_LOOKUP: (EdgeType.CALLS, EdgeType.REFERENCES, EdgeType.IMPORTS),
    QueryType.USAGE_LOOKUP: (EdgeType.CALLS, EdgeType.REFERENCES),
    QueryType.ARCHITECTURE_QUESTION: (EdgeType.CALLS, EdgeType.IMPORTS, EdgeType.REFERENCES),
    QueryType.DEBUGGING_QUESTION: (EdgeType.CALLS, EdgeType.REFERENCES),
    QueryType.API_QUESTION: (EdgeType.EXPOSES_ENDPOINT, EdgeType.CALLS),
    QueryType.CONFIG_QUESTION: (EdgeType.CONFIGURES, EdgeType.IMPORTS),
    QueryType.TEST_QUESTION: (EdgeType.TESTS, EdgeType.CALLS),
    QueryType.DEPLOYMENT_QUESTION: (EdgeType.CONFIGURES,),
    QueryType.MIGRATION_QUESTION: (EdgeType.REFERENCES, EdgeType.CALLS),
    QueryType.OWNERSHIP_QUESTION: (EdgeType.IMPORTS,),
}
_DEFAULT_EDGE_TYPES: tuple[EdgeType, ...] = (EdgeType.CALLS, EdgeType.IMPORTS)


class GraphExpander:
    """Expand a fused result set with structurally related chunks.

    Starting from the strongest fused hits, this follows code-graph edges
    (calls, imports, tests, ...) to definitions the lexical and vector legs may
    have missed — the call chain behind a match rather than just the keyword
    hit. Because edge targets are resolved through the symbols index across all
    allowed projects, traversal naturally crosses repository boundaries.
    """

    def __init__(self, settings: Settings, index: SearchPort) -> None:
        self.settings = settings
        self.index = index

    def expand(
        self,
        hits: list[SearchHit],
        query_type: QueryType,
        filters: dict,
    ) -> list[SearchHit]:
        neighbor_chunks = getattr(self.index, "neighbor_chunks", None)
        if not callable(neighbor_chunks):
            return []
        edge_types = [edge.value for edge in self._edge_types(query_type)]
        max_neighbors = self.settings.graph_expansion_max_neighbors
        if max_neighbors <= 0:
            return []
        seen: set[str] = {hit.chunk_id for hit in hits}
        collected: list[SearchHit] = []
        frontier = self._seed_fqns(hits)
        for _ in range(max(1, self.settings.graph_expansion_hops)):
            if not frontier or len(collected) >= max_neighbors:
                break
            results = neighbor_chunks(
                sorted(frontier), edge_types, filters, max_neighbors - len(collected)
            )
            next_frontier: set[str] = set()
            for hit in results:
                if hit.chunk_id in seen:
                    continue
                seen.add(hit.chunk_id)
                hit.metadata["graph_expanded"] = True
                collected.append(hit)
                if hit.symbol_fqn:
                    next_frontier.add(hit.symbol_fqn)
                if len(collected) >= max_neighbors:
                    break
            frontier = next_frontier
        return collected

    def _seed_fqns(self, hits: list[SearchHit]) -> set[str]:
        fqns: set[str] = set()
        for hit in hits[: self.settings.graph_expansion_seed_hits]:
            if hit.symbol_fqn:
                fqns.add(hit.symbol_fqn)
        return fqns

    def _edge_types(self, query_type: QueryType) -> tuple[EdgeType, ...]:
        return _EDGE_TYPES_BY_QUERY.get(query_type, _DEFAULT_EDGE_TYPES)
