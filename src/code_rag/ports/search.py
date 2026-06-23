from __future__ import annotations

from typing import Protocol

from code_rag.models import CodeChunk, CodeEdge, CodeSymbol, FileMetadata, IndexJobResult, SearchHit


class SearchIndexPort(Protocol):
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

    def index_repo(self, repo_doc: dict) -> None:
        """Upsert repository metadata."""

    def record_job(self, job: IndexJobResult) -> None:
        """Store an index job result."""

    def get_job(self, job_id: str) -> IndexJobResult | None:
        """Fetch a persisted index job result."""

    def file_hash(self, tenant_id: str, project_id: str, branch: str, file_path: str) -> str | None:
        """Return the current indexed file hash if present."""

    def lexical_search(
        self,
        query: str,
        filters: dict,
        size: int,
    ) -> list[SearchHit]:
        """Run BM25 search."""

    def vector_search(
        self,
        vector: list[float],
        filters: dict,
        size: int,
    ) -> list[SearchHit]:
        """Run dense vector search."""

    def symbol_search(self, identifiers: list[str], filters: dict, size: int) -> list[SearchHit]:
        """Search symbol definitions and return their definition chunks."""

    def edge_search(self, identifiers: list[str], filters: dict, size: int) -> list[SearchHit]:
        """Search graph edges and return related chunks."""
