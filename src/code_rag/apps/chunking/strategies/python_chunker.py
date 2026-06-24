"""Python chunking via the standard-library AST.

Extracts one chunk per class/function/method with accurate line boundaries,
parent nesting, imports, calls and references. Falls back to fixed-size text
chunks when the source does not parse.
"""

from __future__ import annotations

import ast

from code_rag.apps.chunking.raw_chunk import RawChunk
from code_rag.apps.chunking.strategies.base import RawChunker
from code_rag.domain.enums.chunk_kind import ChunkKind


class PythonChunker(RawChunker):
    def chunk(self, content: str) -> list[RawChunk]:
        lines = content.splitlines()
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return self.text.fixed_size_chunks(content, ChunkKind.FILE)
        chunks: list[RawChunk] = []
        parents: list[str] = []
        module_imports = self._imports(tree)

        def visit(node: ast.AST) -> None:
            if isinstance(node, ast.ClassDef):
                end = getattr(node, "end_lineno", node.lineno)
                decorators = [self._expr_name(item) for item in node.decorator_list]
                chunks.append(
                    RawChunk(
                        kind=ChunkKind.CLASS_DEFINITION,
                        line_start=node.lineno,
                        line_end=end,
                        text="\n".join(lines[node.lineno - 1 : end]),
                        symbol_name=node.name,
                        symbol_kind="class",
                        parent_symbol=".".join(parents) or None,
                        signature=f"class {node.name}",
                        imports=module_imports,
                        references=self._references(node),
                        decorators=[item for item in decorators if item],
                        docstring=ast.get_docstring(node),
                    )
                )
                parents.append(node.name)
                for member in node.body:
                    visit(member)
                parents.pop()
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = getattr(node, "end_lineno", node.lineno)
                kind = ChunkKind.METHOD_DEFINITION if parents else ChunkKind.FUNCTION_DEFINITION
                prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                decorators = [self._expr_name(item) for item in node.decorator_list]
                chunks.append(
                    RawChunk(
                        kind=kind,
                        line_start=node.lineno,
                        line_end=end,
                        text="\n".join(lines[node.lineno - 1 : end]),
                        symbol_name=node.name,
                        symbol_kind="method" if parents else "function",
                        parent_symbol=".".join(parents) or None,
                        signature=f"{prefix} {node.name}",
                        imports=module_imports,
                        calls=self._calls(node),
                        references=self._references(node),
                        decorators=[item for item in decorators if item],
                        docstring=ast.get_docstring(node),
                    )
                )
            else:
                for child in ast.iter_child_nodes(node):
                    visit(child)

        visit(tree)
        return self.text.split_large_chunks(chunks)

    def _imports(self, tree: ast.AST) -> list[str]:
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.extend(f"{module}.{alias.name}".strip(".") for alias in node.names)
        return self._cap(sorted(set(imports)))

    def _calls(self, node: ast.AST) -> list[str]:
        calls: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                name = self._expr_name(child.func)
                if name:
                    calls.append(name)
        return self._cap(sorted(set(calls)))

    def _references(self, node: ast.AST) -> list[str]:
        references: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                references.append(child.id)
            elif isinstance(child, ast.Attribute):
                name = self._expr_name(child)
                if name:
                    references.append(name)
        return self._cap(sorted(set(references)))

    def _expr_name(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            value = self._expr_name(node.value)
            return f"{value}.{node.attr}" if value else node.attr
        if isinstance(node, ast.Call):
            return self._expr_name(node.func)
        return None
