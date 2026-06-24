from __future__ import annotations

from typing import Protocol

from code_rag.domain.models import (
    CodeChunk,
    CodeCommunity,
    CodeEdge,
    CodeSymbol,
    FileMetadata,
    SearchHit,
)


class SearchPort(Protocol):
    def ensure_indices(self) -> None:
        """Create or update backing indices."""

    def replace_file(
        self,
        file_metadata: FileMetadata,
        chunks: list[CodeChunk],
        symbols: list[CodeSymbol],
        edges: list[CodeEdge],
    ) -> tuple[int, int]:
        """Replace active indexed documents for one file."""

    def delete_file(self, tenant_id: str, project_id: str, branch: str, file_path: str) -> int:
        """Delete active documents for a file."""

    def file_hash(self, tenant_id: str, project_id: str, branch: str, file_path: str) -> str | None:
        """Return the current indexed file hash if present."""

    def existing_embeddings(self, chunk_ids: list[str]) -> dict[str, dict]:
        """Return stored embedding payloads keyed by chunk id (dense/late/input hash)."""

    def lexical_search(self, query: str, filters: dict, size: int) -> list[SearchHit]:
        """Run BM25 search."""

    def vector_search(self, vector: list[float], filters: dict, size: int) -> list[SearchHit]:
        """Run dense vector search."""

    def symbol_search(self, identifiers: list[str], filters: dict, size: int) -> list[SearchHit]:
        """Search symbol definitions and return their definition chunks."""

    def edge_search(self, identifiers: list[str], filters: dict, size: int) -> list[SearchHit]:
        """Search graph edges and return related chunks."""

    def neighbor_chunks(
        self, symbol_fqns: list[str], edge_types: list[str], filters: dict, size: int
    ) -> list[SearchHit]:
        """Return definition chunks of symbols linked to the given symbols by edges.

        Targets are resolved through the symbols index across all allowed
        projects, so neighbours may live in other repositories.
        """

    def community_search(
        self, query: str, vector: list[float], filters: dict, size: int
    ) -> list[SearchHit]:
        """Search code-community summaries and return them as synthetic hits."""

    def read_graph(
        self, tenant_id: str, project_id: str, branch: str
    ) -> tuple[list[CodeSymbol], list[CodeEdge]]:
        """Return all active symbols and edges for a project/branch."""

    def index_communities(self, communities: list[CodeCommunity]) -> None:
        """Persist detected code communities."""

    def delete_project_communities(self, tenant_id: str, project_id: str, branch: str) -> int:
        """Delete a project's communities for a branch. Returns count deleted."""

    def prune_orphaned_edges(self, tenant_id: str, project_id: str, branch: str) -> int:
        """Delete edges whose source chunk no longer exists. Returns count deleted."""
