from __future__ import annotations

from dataclasses import dataclass

from code_rag.domain.enums.chunk_kind import ChunkKind


@dataclass(frozen=True)
class RawChunk:
    kind: ChunkKind
    line_start: int
    line_end: int
    text: str
    symbol_name: str | None = None
    symbol_kind: str | None = None
    parent_symbol: str | None = None
    signature: str | None = None
    imports: list[str] | None = None
    calls: list[str] | None = None
    references: list[str] | None = None
    decorators: list[str] | None = None
    docstring: str | None = None
