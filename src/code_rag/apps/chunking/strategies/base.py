"""Shared base for language-aware raw chunkers."""

from __future__ import annotations

from code_rag.apps.chunking.strategies.text_chunker import TextChunker
from code_rag.config.settings import Settings


class RawChunker:
    """Holds settings and the shared text chunker used for fallback/overflow."""

    def __init__(self, settings: Settings, text_chunker: TextChunker) -> None:
        self.settings = settings
        self.text = text_chunker

    def _cap(self, values: list[str]) -> list[str]:
        """Bound a reference/call/import list to keep index size in check."""
        return values[: self.settings.max_symbol_references]
