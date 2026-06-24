"""Regex chunking: the fallback for languages without a tree-sitter grammar.

Heuristically locates class/function/test declarations and brace-delimited
bodies. Returns an empty list when nothing matches so the caller can fall back
to fixed-size text chunks.
"""

from __future__ import annotations

import re

from code_rag.apps.chunking.raw_chunk import RawChunk
from code_rag.apps.chunking.strategies.base import RawChunker
from code_rag.domain.enums.chunk_kind import ChunkKind

_DECLARATION = re.compile(
    r"^\s*(?:export\s+)?(?:public|private|protected|static|final|async|function|class|interface|type|func|def|\w[\w<>\[\],\s]+\s+)+\s*([A-Za-z_][\w]*)\s*(?:\(|\{|=|extends|implements)",
    re.MULTILINE,
)


class RegexChunker(RawChunker):
    def chunk(self, content: str) -> list[RawChunk]:
        lines = content.splitlines()
        matches = list(_DECLARATION.finditer(content))
        if not matches:
            return []
        starts = [content[: match.start()].count("\n") + 1 for match in matches]
        chunks: list[RawChunk] = []
        text_imports = self._imports(content)
        for index, match in enumerate(matches):
            start = starts[index]
            next_start = starts[index + 1] - 1 if index + 1 < len(starts) else len(lines)
            end = self._brace_block_end(lines, start, next_start)
            text = "\n".join(lines[start - 1 : end])
            declaration = match.group(0)
            is_class = any(token in declaration for token in ("class", "interface", "type"))
            symbol_name = match.group(1)
            decorators = self._leading_annotations(lines, start)
            kind = ChunkKind.CLASS_DEFINITION if is_class else ChunkKind.FUNCTION_DEFINITION
            if self._looks_like_test(symbol_name, text):
                kind = ChunkKind.TEST_CASE
            chunks.append(
                RawChunk(
                    kind=kind,
                    line_start=start,
                    line_end=end,
                    text=text,
                    symbol_name=symbol_name,
                    symbol_kind="class" if is_class else "function",
                    signature=declaration.strip(),
                    imports=text_imports,
                    calls=self._calls(text),
                    references=self._references(text),
                    decorators=decorators,
                )
            )
        return self.text.split_large_chunks(chunks)

    def _brace_block_end(self, lines: list[str], decl_line: int, fallback_end: int) -> int:
        """Find the closing line of a brace-delimited block.

        Balances ``{``/``}`` from the declaration onward (a pragmatic counter
        that ignores braces in strings/comments). Falls back to the next
        declaration's start when no opening brace is found (e.g. brace-less
        languages), preserving prior behaviour.
        """

        depth = 0
        seen_brace = False
        for line_no in range(decl_line, min(fallback_end, len(lines)) + 1):
            line = lines[line_no - 1]
            for char in line:
                if char == "{":
                    depth += 1
                    seen_brace = True
                elif char == "}":
                    depth -= 1
                    if seen_brace and depth <= 0:
                        return line_no
        return fallback_end

    def _leading_annotations(self, lines: list[str], declaration_start: int) -> list[str]:
        annotations: list[str] = []
        index = declaration_start - 2
        while index >= 0:
            stripped = lines[index].strip()
            if not stripped:
                index -= 1
                continue
            if stripped.startswith(("@", "#[", "[", "Route(", "Http")):
                annotations.append(stripped)
                index -= 1
                continue
            break
        return list(reversed(annotations))

    def _looks_like_test(self, symbol_name: str, text: str) -> bool:
        lower_name = symbol_name.lower()
        return (
            lower_name.startswith("test")
            or lower_name.endswith("test")
            or "@test" in text.lower()
            or "describe(" in text
            or "it(" in text
        )

    def _imports(self, content: str) -> list[str]:
        patterns = [
            r"^\s*import\s+(?:[\w{},*\s]+\s+from\s+)?['\"]?([@\w./-]+)['\"]?",
            r"^\s*from\s+([\w.]+)\s+import\s+",
            r"^\s*using\s+([\w.]+)",
            r"^\s*package\s+([\w.]+)",
        ]
        imports: list[str] = []
        for pattern in patterns:
            imports.extend(re.findall(pattern, content, flags=re.MULTILINE))
        return self._cap(sorted(set(imports)))

    def _calls(self, content: str) -> list[str]:
        calls = re.findall(r"\b([A-Za-z_][\w.]*)\s*\(", content)
        keywords = {"if", "for", "while", "switch", "catch", "return", "function"}
        return self._cap(sorted({call for call in calls if call.split(".")[-1] not in keywords}))

    def _references(self, content: str) -> list[str]:
        refs = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", content)
        keywords = {"class", "interface", "function", "return", "if", "else", "for", "while"}
        return self._cap(sorted({ref for ref in refs if ref not in keywords}))
