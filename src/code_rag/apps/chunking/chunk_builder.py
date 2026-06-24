from __future__ import annotations

import ast
import re
from datetime import UTC
from pathlib import Path

from code_rag.apps.chunking.raw_chunk import RawChunk
from code_rag.apps.chunking.tree_sitter_chunker import TreeSitterChunker
from code_rag.apps.classification.file_classifier import FileClassifier
from code_rag.apps.metadata.repo_metadata_provider import RepoMetadataProvider
from code_rag.apps.secrets.secret_scanner import SecretScanner
from code_rag.config.settings import Settings
from code_rag.domain.enums.chunk_kind import ChunkKind
from code_rag.domain.enums.edge_type import EdgeType
from code_rag.domain.enums.file_class import FileClass
from code_rag.domain.enums.symbol_role import SymbolRole
from code_rag.domain.ids import content_hash, stable_id
from code_rag.domain.languages import path_language
from code_rag.domain.models import (
    CodeChunk,
    CodeEdge,
    CodeSymbol,
    FileMetadata,
    GitLabProject,
)
from code_rag.domain.time import utcnow


class ChunkBuilder:
    def __init__(
        self,
        settings: Settings,
        classifier: FileClassifier,
        secret_scanner: SecretScanner | None = None,
        repo_metadata: RepoMetadataProvider | None = None,
        tree_sitter_chunker: TreeSitterChunker | None = None,
    ) -> None:
        self.settings = settings
        self.classifier = classifier
        self.secret_scanner = secret_scanner
        self.repo_metadata = repo_metadata
        self.tree_sitter: TreeSitterChunker | None
        if tree_sitter_chunker is not None:
            self.tree_sitter = tree_sitter_chunker
        elif settings.use_tree_sitter:
            self.tree_sitter = TreeSitterChunker(settings)
        else:
            self.tree_sitter = None

    def build_file(
        self,
        root: Path,
        file_path: Path,
        project: GitLabProject,
        branch: str,
        commit_sha: str,
    ) -> tuple[FileMetadata, list[CodeChunk], list[CodeSymbol], list[CodeEdge]]:
        relative_path = file_path.relative_to(root).as_posix()
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        repo_metadata = self.repo_metadata.get(project) if self.repo_metadata else None
        file_hash = content_hash(content)
        lines = content.splitlines()
        file_class = self.classifier.classify(file_path, root)
        metadata = FileMetadata(
            tenant_id=self.settings.tenant_id,
            gitlab_instance_url=self.settings.gitlab_base_url.rstrip("/"),
            gitlab_project_id=project.gitlab_project_id,
            repo_path_with_namespace=project.repo_path_with_namespace,
            repo_name=project.repo_name,
            repo_url=project.repo_url,
            branch=branch,
            commit_sha=commit_sha,
            file_path=relative_path,
            file_name=file_path.name,
            file_extension=file_path.suffix.lower(),
            language=path_language(relative_path),
            file_hash=file_hash,
            size_bytes=file_path.stat().st_size,
            line_count=len(lines),
            file_class=file_class,
            is_test=file_class == FileClass.TEST,
            is_generated=file_class == FileClass.GENERATED,
            is_vendor=file_class == FileClass.VENDOR,
            is_config=file_class
            in {FileClass.CONFIG, FileClass.CI_CD, FileClass.DEPLOYMENT, FileClass.SCHEMA},
            is_migration=file_class == FileClass.MIGRATION,
            is_binary=file_class == FileClass.BINARY,
            is_large=file_class == FileClass.LARGE_UNKNOWN,
            team_owner=repo_metadata.team_owner if repo_metadata else None,
            business_domain=repo_metadata.business_domain if repo_metadata else None,
            service_name=repo_metadata.service_name if repo_metadata else None,
            slack_channel=repo_metadata.slack_channel if repo_metadata else None,
            jira_project=repo_metadata.jira_project if repo_metadata else None,
            service_type=repo_metadata.service_type if repo_metadata else None,
            deployment_name=repo_metadata.deployment_name if repo_metadata else None,
        )
        raw_chunks = self._raw_chunks(metadata, content)
        chunks = [self._to_chunk(metadata, raw) for raw in raw_chunks]
        chunks = [self._redact_chunk(chunk) for chunk in chunks]
        metadata.secret_findings_count = sum(chunk.secret_findings_count for chunk in chunks)
        metadata.secret_redactions_count = sum(chunk.secret_redactions_count for chunk in chunks)
        metadata.secret_high_confidence_count = sum(
            chunk.secret_high_confidence_count for chunk in chunks
        )
        chunks = self._link_parent_chunks(chunks)
        symbols = [
            self._to_symbol(metadata, chunk, raw)
            for chunk, raw in zip(chunks, raw_chunks, strict=True)
            if raw.symbol_name
        ]
        edges = [
            edge
            for chunk, raw in zip(chunks, raw_chunks, strict=True)
            for edge in self._to_edges(metadata, chunk, raw)
        ]
        return metadata, chunks, symbols, edges

    def _cap(self, values: list[str]) -> list[str]:
        return values[: self.settings.max_symbol_references]

    def _raw_chunks(self, metadata: FileMetadata, content: str) -> list[RawChunk]:
        if metadata.language == "python":
            chunks = self._python_chunks(content)
        elif metadata.file_class == FileClass.DOCUMENTATION:
            chunks = self._markdown_chunks(content)
        elif metadata.file_class in {FileClass.CONFIG, FileClass.CI_CD, FileClass.DEPLOYMENT}:
            chunks = self._fixed_size_chunks(content, ChunkKind.CONFIG_BLOCK)
        else:
            chunks = self._ast_or_regex_chunks(metadata.language, content)
        if not chunks:
            chunks = self._fixed_size_chunks(content, ChunkKind.FILE)
        return chunks

    def _ast_or_regex_chunks(self, language: str, content: str) -> list[RawChunk]:
        if self.tree_sitter is not None:
            ts_chunks = self.tree_sitter.chunk(language, content)
            if ts_chunks is not None:
                return self._split_large_chunks(ts_chunks)
        return self._regex_code_chunks(content)

    def _python_chunks(self, content: str) -> list[RawChunk]:
        lines = content.splitlines()
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return self._fixed_size_chunks(content, ChunkKind.FILE)
        chunks: list[RawChunk] = []
        parents: list[str] = []
        module_imports = self._python_imports(tree)

        def visit(node: ast.AST) -> None:
            if isinstance(node, ast.ClassDef):
                end = getattr(node, "end_lineno", node.lineno)
                decorators = [self._python_expr_name(item) for item in node.decorator_list]
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
                        references=self._python_references(node),
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
                decorators = [self._python_expr_name(item) for item in node.decorator_list]
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
                        calls=self._python_calls(node),
                        references=self._python_references(node),
                        decorators=[item for item in decorators if item],
                        docstring=ast.get_docstring(node),
                    )
                )
            else:
                for child in ast.iter_child_nodes(node):
                    visit(child)

        visit(tree)
        return self._split_large_chunks(chunks)

    def _python_imports(self, tree: ast.AST) -> list[str]:
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.extend(f"{module}.{alias.name}".strip(".") for alias in node.names)
        return self._cap(sorted(set(imports)))

    def _python_calls(self, node: ast.AST) -> list[str]:
        calls: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                name = self._python_expr_name(child.func)
                if name:
                    calls.append(name)
        return self._cap(sorted(set(calls)))

    def _python_references(self, node: ast.AST) -> list[str]:
        references: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                references.append(child.id)
            elif isinstance(child, ast.Attribute):
                name = self._python_expr_name(child)
                if name:
                    references.append(name)
        return self._cap(sorted(set(references)))

    def _python_expr_name(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            value = self._python_expr_name(node.value)
            return f"{value}.{node.attr}" if value else node.attr
        if isinstance(node, ast.Call):
            return self._python_expr_name(node.func)
        return None

    def _regex_code_chunks(self, content: str) -> list[RawChunk]:
        lines = content.splitlines()
        pattern = re.compile(
            r"^\s*(?:export\s+)?(?:public|private|protected|static|final|async|function|class|interface|type|func|def|\w[\w<>\[\],\s]+\s+)+\s*([A-Za-z_][\w]*)\s*(?:\(|\{|=|extends|implements)",
            re.MULTILINE,
        )
        matches = list(pattern.finditer(content))
        if not matches:
            return []
        starts = [content[: match.start()].count("\n") + 1 for match in matches]
        chunks: list[RawChunk] = []
        text_imports = self._regex_imports(content)
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
                    calls=self._regex_calls(text),
                    references=self._regex_references(text),
                    decorators=decorators,
                )
            )
        return self._split_large_chunks(chunks)

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

    def _regex_imports(self, content: str) -> list[str]:
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

    def _regex_calls(self, content: str) -> list[str]:
        calls = re.findall(r"\b([A-Za-z_][\w.]*)\s*\(", content)
        keywords = {"if", "for", "while", "switch", "catch", "return", "function"}
        return self._cap(sorted({call for call in calls if call.split(".")[-1] not in keywords}))

    def _regex_references(self, content: str) -> list[str]:
        refs = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", content)
        keywords = {"class", "interface", "function", "return", "if", "else", "for", "while"}
        return self._cap(sorted({ref for ref in refs if ref not in keywords}))

    def _markdown_chunks(self, content: str) -> list[RawChunk]:
        lines = content.splitlines()
        starts = [index + 1 for index, line in enumerate(lines) if line.startswith("#")]
        if not starts:
            return self._fixed_size_chunks(content, ChunkKind.DOCUMENTATION_SECTION)
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
        return self._split_large_chunks(chunks)

    def _fixed_size_chunks(self, content: str, kind: ChunkKind) -> list[RawChunk]:
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

    def _split_large_chunks(self, chunks: list[RawChunk]) -> list[RawChunk]:
        result: list[RawChunk] = []
        for chunk in chunks:
            if len(chunk.text) <= self.settings.max_chunk_chars:
                result.append(chunk)
                continue
            result.extend(self._fixed_size_chunks(chunk.text, chunk.kind))
        return result

    def _link_parent_chunks(self, chunks: list[CodeChunk]) -> list[CodeChunk]:
        class_ids: dict[str, str] = {
            c.symbol_name: c.chunk_id
            for c in chunks
            if c.chunk_kind == ChunkKind.CLASS_DEFINITION and c.symbol_name
        }
        if not class_ids:
            return chunks
        result: list[CodeChunk] = []
        for chunk in chunks:
            if chunk.parent_symbol_fqn:
                top_parent = chunk.parent_symbol_fqn.split(".")[0]
                parent_id = class_ids.get(top_parent)
                if parent_id:
                    chunk = chunk.model_copy(update={"parent_chunk_id": parent_id})
            result.append(chunk)
        return result

    def _to_chunk(self, metadata: FileMetadata, raw: RawChunk) -> CodeChunk:
        symbol_fqn = None
        if raw.symbol_name:
            symbol_fqn = ".".join(
                part
                for part in [
                    metadata.repo_path_with_namespace.replace("/", "."),
                    metadata.file_path.replace("/", ".").removesuffix(metadata.file_extension),
                    raw.parent_symbol,
                    raw.symbol_name,
                ]
                if part
            )
        blob_url = self._blob_url(metadata, raw.line_start, raw.line_end)
        header = self._context_header(metadata, raw, symbol_fqn)
        enriched_text = f"{header}\n\nCode:\n{raw.text}"
        return CodeChunk(
            chunk_id=stable_id(
                metadata.tenant_id,
                metadata.gitlab_project_id,
                metadata.branch,
                metadata.file_path,
                metadata.file_hash,
                raw.line_start,
                raw.line_end,
                raw.symbol_name,
            ),
            tenant_id=metadata.tenant_id,
            gitlab_instance_url=metadata.gitlab_instance_url,
            gitlab_project_id=metadata.gitlab_project_id,
            repo_path_with_namespace=metadata.repo_path_with_namespace,
            repo_name=metadata.repo_name,
            repo_url=metadata.repo_url,
            team_owner=metadata.team_owner,
            business_domain=metadata.business_domain,
            service_name=metadata.service_name,
            slack_channel=metadata.slack_channel,
            jira_project=metadata.jira_project,
            service_type=metadata.service_type,
            deployment_name=metadata.deployment_name,
            branch=metadata.branch,
            commit_sha=metadata.commit_sha,
            file_path=metadata.file_path,
            file_name=metadata.file_name,
            file_extension=metadata.file_extension,
            language=metadata.language,
            file_hash=metadata.file_hash,
            is_test=metadata.is_test,
            is_generated=metadata.is_generated,
            is_vendor=metadata.is_vendor,
            is_config=metadata.is_config,
            is_migration=metadata.is_migration,
            chunk_kind=raw.kind,
            symbol_role=SymbolRole.DEFINITION if raw.symbol_name else SymbolRole.NONE,
            symbol_name=raw.symbol_name,
            symbol_fqn=symbol_fqn,
            symbol_kind=raw.symbol_kind,
            parent_symbol_fqn=raw.parent_symbol,
            line_start=raw.line_start,
            line_end=raw.line_end,
            gitlab_blob_url=blob_url,
            gitlab_raw_url=self._raw_url(metadata),
            text=enriched_text,
            text_for_embedding=enriched_text,
            imports=raw.imports or [],
            defines_symbols=[symbol_fqn] if symbol_fqn else [],
            references_symbols=raw.references or [],
            calls_symbols=raw.calls or [],
        )

    def _redact_chunk(self, chunk: CodeChunk) -> CodeChunk:
        if not self.settings.secret_scanning_enabled or not self.secret_scanner:
            return chunk
        text, findings = self.secret_scanner.redact(chunk.text)
        if not findings:
            return chunk
        secret_types = sorted({finding.secret_type for finding in findings})
        high_confidence_count = sum(1 for finding in findings if finding.confidence == "high")
        return chunk.model_copy(
            update={
                "text": text,
                "text_for_embedding": text,
                "secret_findings_count": len(findings),
                "secret_redactions_count": len(findings),
                "secret_high_confidence_count": high_confidence_count,
                "secret_types": secret_types,
            }
        )

    def _to_symbol(self, metadata: FileMetadata, chunk: CodeChunk, raw: RawChunk) -> CodeSymbol:
        return CodeSymbol(
            symbol_id=stable_id(
                metadata.tenant_id, metadata.gitlab_project_id, metadata.branch, chunk.symbol_fqn
            ),
            tenant_id=metadata.tenant_id,
            gitlab_project_id=metadata.gitlab_project_id,
            repo_path_with_namespace=metadata.repo_path_with_namespace,
            branch=metadata.branch,
            commit_sha=metadata.commit_sha,
            language=metadata.language,
            symbol_name=raw.symbol_name or "",
            symbol_fqn=chunk.symbol_fqn or raw.symbol_name or "",
            symbol_kind=raw.symbol_kind or "symbol",
            definition_file_path=metadata.file_path,
            definition_line_start=raw.line_start,
            definition_line_end=raw.line_end,
            definition_chunk_id=chunk.chunk_id,
            definition_gitlab_url=chunk.gitlab_blob_url,
            parent_symbol_fqn=raw.parent_symbol,
            module_path=metadata.file_path,
            docstring=raw.docstring,
            signature=raw.signature,
            decorators=raw.decorators or [],
            indexed_at=utcnow().astimezone(UTC),
        )

    def _to_edges(self, metadata: FileMetadata, chunk: CodeChunk, raw: RawChunk) -> list[CodeEdge]:
        edges: list[CodeEdge] = []
        source = chunk.symbol_fqn or f"{metadata.repo_path_with_namespace}:{metadata.file_path}"
        for target in raw.imports or []:
            edges.append(self._edge(metadata, chunk, source, target, EdgeType.IMPORTS, 0.65))
        for target in raw.calls or []:
            edges.append(self._edge(metadata, chunk, source, target, EdgeType.CALLS, 0.55))
        for target in raw.references or []:
            edges.append(self._edge(metadata, chunk, source, target, EdgeType.REFERENCES, 0.35))
        if metadata.is_test and raw.symbol_name:
            edges.append(self._edge(metadata, chunk, source, raw.symbol_name, EdgeType.TESTS, 0.45))
        if metadata.is_config:
            edges.append(
                self._edge(metadata, chunk, source, metadata.file_path, EdgeType.CONFIGURES, 0.4)
            )
        for route in self._route_patterns(raw):
            edges.append(self._edge(metadata, chunk, source, route, EdgeType.EXPOSES_ENDPOINT, 0.7))
        return edges

    def _edge(
        self,
        metadata: FileMetadata,
        chunk: CodeChunk,
        source: str,
        target: str,
        edge_type: EdgeType,
        confidence: float,
    ) -> CodeEdge:
        return CodeEdge(
            edge_id=stable_id(
                metadata.tenant_id,
                metadata.gitlab_project_id,
                metadata.branch,
                metadata.file_path,
                chunk.chunk_id,
                edge_type,
                target,
            ),
            tenant_id=metadata.tenant_id,
            branch=metadata.branch,
            commit_sha=metadata.commit_sha,
            source_symbol_id=chunk.chunk_id,
            source_symbol_fqn=source,
            source_repo_project_id=metadata.gitlab_project_id,
            source_repo_path_with_namespace=metadata.repo_path_with_namespace,
            source_file_path=metadata.file_path,
            source_line_start=chunk.line_start,
            target_symbol_fqn=target,
            edge_type=edge_type,
            confidence=confidence,
        )

    def _route_patterns(self, raw: RawChunk) -> list[str]:
        routes: set[str] = set()
        for decorator in raw.decorators or []:
            if any(
                token in decorator.lower()
                for token in ("route", "get", "post", "put", "delete", "patch")
            ):
                routes.add(decorator)
        routes.update(re.findall(r"['\"](/[A-Za-z0-9_./{}:-]*)['\"]", raw.text))
        return sorted(routes)

    def _context_header(self, metadata: FileMetadata, raw: RawChunk, symbol_fqn: str | None) -> str:
        lines = [
            f"Repository: {metadata.repo_path_with_namespace}",
            f"Path: {metadata.file_path}",
            f"Language: {metadata.language}",
            f"Kind: {raw.kind.value}",
            f"Line range: {raw.line_start}-{raw.line_end}",
        ]
        if raw.symbol_name:
            lines.extend(
                [
                    f"Symbol: {raw.symbol_name}",
                    f"Symbol FQN: {symbol_fqn}",
                    f"Symbol kind: {raw.symbol_kind}",
                ]
            )
        if raw.parent_symbol:
            lines.append(f"Parent: {raw.parent_symbol}")
        if raw.signature:
            lines.append(f"Signature: {raw.signature}")
        if raw.decorators:
            lines.append(f"Decorators/annotations: {', '.join(raw.decorators)}")
        if metadata.team_owner:
            lines.append(f"Team owner: {metadata.team_owner}")
        if metadata.business_domain:
            lines.append(f"Business domain: {metadata.business_domain}")
        if metadata.service_name:
            lines.append(f"Service: {metadata.service_name}")
        return "\n".join(lines)

    def _blob_url(self, metadata: FileMetadata, line_start: int, line_end: int) -> str:
        encoded_path = metadata.file_path
        return (
            f"{metadata.gitlab_instance_url}/{metadata.repo_path_with_namespace}"
            f"/-/blob/{metadata.commit_sha}/{encoded_path}#L{line_start}-L{line_end}"
        )

    def _raw_url(self, metadata: FileMetadata) -> str:
        return (
            f"{metadata.gitlab_instance_url}/{metadata.repo_path_with_namespace}"
            f"/-/raw/{metadata.commit_sha}/{metadata.file_path}"
        )
