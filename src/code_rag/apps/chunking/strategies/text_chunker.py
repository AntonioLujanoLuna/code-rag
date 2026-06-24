"""Generic text chunking: fixed-size windows, large-chunk splitting, markdown.

These language-agnostic strategies are shared by the language-aware chunkers
(Python, regex, tree-sitter) as their fallback and overflow-splitting path.
"""

from __future__ import annotations

from code_rag.apps.chunking.raw_chunk import RawChunk
from code_rag.config.settings import Settings
from code_rag.domain.enums.chunk_kind import ChunkKind


class TextChunker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def fixed_size_chunks(self, content: str, kind: ChunkKind) -> list[RawChunk]:
        lines = content.splitlines()
        chunks: list[RawChunk] = []
        overlap = max(0, self.settings.chunk_overlap_lines)
        start = 0
        while start < len(lines):
            current: list[str] = []
            char_count = 0
            end = start
            while end < len(lines) and char_count < self.settings.max_chunk_chars:
                current.append(lines[end])
                char_count += len(lines[end]) + 1
                end += 1
            chunks.append(
                RawChunk(
                    kind=kind,
                    line_start=start + 1,
                    line_end=max(start + 1, end),
                    text="\n".join(current),
                )
            )
            # Advance start but carry `overlap` lines of context into the next chunk.
            start = max(start + 1, end - overlap)
        return chunks

    def split_large_chunks(self, chunks: list[RawChunk]) -> list[RawChunk]:
        result: list[RawChunk] = []
        for chunk in chunks:
            if len(chunk.text) <= self.settings.max_chunk_chars:
                result.append(chunk)
                continue
            result.extend(self.fixed_size_chunks(chunk.text, chunk.kind))
        return result

    def markdown_chunks(self, content: str) -> list[RawChunk]:
        lines = content.splitlines()
        starts = [index + 1 for index, line in enumerate(lines) if line.startswith("#")]
        if not starts:
            return self.fixed_size_chunks(content, ChunkKind.DOCUMENTATION_SECTION)
        chunks: list[RawChunk] = []
        for index, start in enumerate(starts):
            end = starts[index + 1] - 1 if index + 1 < len(starts) else len(lines)
            title = lines[start - 1].lstrip("#").strip() or None
            chunks.append(
                RawChunk(
                    kind=ChunkKind.DOCUMENTATION_SECTION,
                    line_start=start,
                    line_end=end,
                    text="\n".join(lines[start - 1 : end]),
                    symbol_name=title,
                    symbol_kind="section" if title else None,
                )
            )
        return self.split_large_chunks(chunks)
