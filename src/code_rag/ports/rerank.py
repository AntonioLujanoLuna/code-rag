from __future__ import annotations

from typing import Protocol


class RerankProvider(Protocol):
    """Re-scores candidate documents against a query (e.g. a cross-encoder)."""

    @property
    def enabled(self) -> bool:
        """Whether a backing rerank service is configured."""

    def score(self, query: str, documents: list[str]) -> list[float]:
        """Return one relevance score per document, aligned by index.

        Implementations must return an empty list when scoring is unavailable so
        callers can fall back to their existing ordering.
        """
