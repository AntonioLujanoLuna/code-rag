from __future__ import annotations

import logging
from threading import RLock

try:
    from tree_sitter import Language, Node, Parser
except ImportError:  # pragma: no cover - exercised only without the optional dep
    Language = None  # type: ignore[assignment,misc]
    Node = None  # type: ignore[assignment,misc]
    Parser = None  # type: ignore[assignment,misc]

from code_rag.apps.chunking.raw_chunk import RawChunk
from code_rag.config.settings import Settings
from code_rag.domain.enums.chunk_kind import ChunkKind

logger = logging.getLogger(__name__)

# Our language name (see domain.languages) -> (module, language-factory attribute).
# Each grammar ships its compiled parser in the wheel, so no runtime download.
_GRAMMARS: dict[str, tuple[str, str]] = {
    "javascript": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "java": ("tree_sitter_java", "language"),
    "go": ("tree_sitter_go", "language"),
    "rust": ("tree_sitter_rust", "language"),
    "c": ("tree_sitter_c", "language"),
    "cpp": ("tree_sitter_cpp", "language"),
    "csharp": ("tree_sitter_c_sharp", "language"),
    "ruby": ("tree_sitter_ruby", "language"),
    "php": ("tree_sitter_php", "language_php"),
    "kotlin": ("tree_sitter_kotlin", "language"),
    "scala": ("tree_sitter_scala", "language"),
}

# Node types that denote a class-like container (children become its members).
_CLASS_TYPES = {
    "class_declaration",
    "class_definition",
    "class_specifier",
    "class",
    "interface_declaration",
    "struct_specifier",
    "struct_declaration",
    "struct_item",
    "type_spec",
    "enum_declaration",
    "enum_item",
    "trait_item",
    "trait_declaration",
    "impl_item",
    "module",
    "mod_item",
    "record_declaration",
    "object_declaration",
}
# Node types that denote a function/method definition.
_FUNCTION_TYPES = {
    "function_declaration",
    "function_definition",
    "function_item",
    "method_declaration",
    "method_definition",
    "method",
    "constructor_declaration",
}
_CALL_TYPES = {
    "call_expression",
    "call",
    "method_invocation",
    "invocation_expression",
    "function_call_expression",
    "member_call_expression",
    "scoped_call_expression",
}
_IMPORT_TYPES = {
    "import_statement",
    "import_declaration",
    "import_from_statement",
    "import_spec",
    "using_directive",
    "package_clause",
    "use_declaration",
    "namespace_use_declaration",
    "preproc_include",
}
_DECORATOR_TYPES = {"decorator", "annotation", "marker_annotation", "attribute", "attribute_list"}
# Field/child types whose subtrees we don't descend into when resolving a name.
_BODY_TYPES = {"block", "body", "compound_statement", "class_body", "declaration_list"}


class TreeSitterChunker:
    """Multi-language AST chunker backed by tree-sitter grammars.

    Replaces the brittle regex chunker for any language with an installed
    grammar wheel: it walks the concrete syntax tree to extract classes,
    functions and methods with accurate line boundaries, parent nesting, calls,
    imports and references. Languages without a grammar return ``None`` so the
    caller can fall back to the regex chunker.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._languages: dict[str, Language | None] = {}
        self._lock = RLock()

    def supports(self, language: str) -> bool:
        return self._language(language) is not None

    def chunk(self, language: str, content: str) -> list[RawChunk] | None:
        ts_language = self._language(language)
        if ts_language is None:
            return None
        try:
            parser = Parser(ts_language)
            tree = parser.parse(content.encode("utf-8", errors="ignore"))
        except Exception:  # pragma: no cover - defensive against grammar quirks
            logger.warning("tree-sitter parse failed for %s", language, exc_info=True)
            return None
        lines = content.splitlines()
        imports = self._collect_imports(tree.root_node)
        chunks: list[RawChunk] = []
        self._walk(tree.root_node, [], lines, imports, chunks)
        return chunks

    def _language(self, language: str) -> Language | None:
        if Language is None:
            return None
        with self._lock:
            if language in self._languages:
                return self._languages[language]
            grammar = _GRAMMARS.get(language)
            loaded: Language | None = None
            if grammar:
                module_name, attribute = grammar
                try:
                    module = __import__(module_name, fromlist=[attribute])
                    loaded = Language(getattr(module, attribute)())
                except Exception:
                    logger.info("tree-sitter grammar unavailable for %s", language)
                    loaded = None
            self._languages[language] = loaded
            return loaded

    def _walk(
        self,
        node: Node,
        parents: list[str],
        lines: list[str],
        imports: list[str],
        out: list[RawChunk],
    ) -> None:
        is_class = node.type in _CLASS_TYPES
        is_function = node.type in _FUNCTION_TYPES
        child_parents = parents
        if is_class or is_function:
            name = self._node_name(node)
            if name:
                kind = self._kind(is_class, parents)
                out.append(self._raw_chunk(node, kind, name, parents, lines, imports))
                if is_class:
                    child_parents = [*parents, name]
        for child in node.children:
            self._walk(child, child_parents, lines, imports, out)

    def _kind(self, is_class: bool, parents: list[str]) -> ChunkKind:
        if is_class:
            return ChunkKind.CLASS_DEFINITION
        return ChunkKind.METHOD_DEFINITION if parents else ChunkKind.FUNCTION_DEFINITION

    def _raw_chunk(
        self,
        node: Node,
        kind: ChunkKind,
        name: str,
        parents: list[str],
        lines: list[str],
        imports: list[str],
    ) -> RawChunk:
        start = node.start_point[0] + 1
        end = node.end_point[0] + 1
        text = "\n".join(lines[start - 1 : end])
        calls = self._collect_calls(node)
        references = self._collect_references(node)
        decorators = self._collect_decorators(node)
        if kind == ChunkKind.CLASS_DEFINITION:
            symbol_kind = "class"
        elif kind == ChunkKind.METHOD_DEFINITION:
            symbol_kind = "method"
        else:
            symbol_kind = "function"
        return RawChunk(
            kind=kind,
            line_start=start,
            line_end=end,
            text=text,
            symbol_name=name,
            symbol_kind=symbol_kind,
            parent_symbol=".".join(parents) or None,
            signature=self._signature(node),
            imports=imports,
            calls=calls,
            references=references,
            decorators=decorators,
        )

    def _node_name(self, node: Node) -> str | None:
        named = node.child_by_field_name("name")
        if named is not None:
            return self._text(named)
        declarator = node.child_by_field_name("declarator")
        if declarator is not None:
            found = self._first_identifier(declarator)
            if found:
                return found
        for child in node.children:
            if child.type.endswith("identifier") and child.is_named:
                return self._text(child)
        return None

    def _first_identifier(self, node: Node, depth: int = 0) -> str | None:
        if depth > 6:
            return None
        if node.type.endswith("identifier") and node.is_named:
            return self._text(node)
        for child in node.children:
            if child.type in _BODY_TYPES:
                continue
            found = self._first_identifier(child, depth + 1)
            if found:
                return found
        return None

    def _signature(self, node: Node) -> str:
        text = self._text(node)
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped[:200]
        return ""

    def _collect_imports(self, root: Node) -> list[str]:
        imports: list[str] = []
        seen: set[str] = set()
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type in _IMPORT_TYPES:
                value = self._text(node).splitlines()[0].strip() if node.text else ""
                if value and value not in seen:
                    seen.add(value)
                    imports.append(value)
            stack.extend(node.children)
        return self._cap(imports)

    def _collect_calls(self, node: Node) -> list[str]:
        calls: list[str] = []
        seen: set[str] = set()
        self._collect_calls_into(node, calls, seen, top=True)
        return self._cap(calls)

    def _collect_calls_into(self, node: Node, calls: list[str], seen: set[str], top: bool) -> None:
        if not top and node.type in _FUNCTION_TYPES:
            # Calls inside a nested definition belong to that definition.
            return
        if node.type in _CALL_TYPES:
            callee = node.child_by_field_name("function") or node.child_by_field_name("name")
            name = self._leaf_name(self._text(callee)) if callee is not None else None
            if name and name not in seen:
                seen.add(name)
                calls.append(name)
        for child in node.children:
            self._collect_calls_into(child, calls, seen, top=False)

    def _collect_references(self, node: Node) -> list[str]:
        references: list[str] = []
        seen: set[str] = set()
        stack = [node]
        while stack and len(references) < self.settings.max_symbol_references:
            current = stack.pop()
            if current.type.endswith("identifier") and current.is_named:
                value = self._text(current)
                if value and value not in seen:
                    seen.add(value)
                    references.append(value)
            stack.extend(current.children)
        return references

    def _collect_decorators(self, node: Node) -> list[str]:
        decorators: list[str] = []
        sibling = node.prev_named_sibling
        while sibling is not None and sibling.type in _DECORATOR_TYPES:
            decorators.append(self._text(sibling).strip())
            sibling = sibling.prev_named_sibling
        for child in node.children:
            if child.type in _DECORATOR_TYPES or child.type == "modifiers":
                for annotation in self._iter_annotations(child):
                    decorators.append(annotation)
        # Preserve source order.
        return list(dict.fromkeys(reversed(decorators)))

    def _iter_annotations(self, node: Node) -> list[str]:
        if node.type in _DECORATOR_TYPES:
            return [self._text(node).strip()]
        results: list[str] = []
        for child in node.children:
            if child.type in _DECORATOR_TYPES:
                results.append(self._text(child).strip())
        return results

    def _leaf_name(self, value: str) -> str:
        for separator in (".", "::", "->"):
            if separator in value:
                value = value.split(separator)[-1]
        return value.strip()

    def _text(self, node: Node | None) -> str:
        if node is None or node.text is None:
            return ""
        return node.text.decode("utf-8", errors="ignore")

    def _cap(self, values: list[str]) -> list[str]:
        return values[: self.settings.max_symbol_references]
