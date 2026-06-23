from __future__ import annotations

from pathlib import Path

import pytest

from code_rag.apps.chunking.chunk_builder import ChunkBuilder
from code_rag.apps.chunking.tree_sitter_chunker import TreeSitterChunker
from code_rag.apps.classification.file_classifier import FileClassifier
from code_rag.config.settings import Settings
from code_rag.domain import ChunkKind, GitLabProject

PROJECT = GitLabProject(
    gitlab_project_id="1",
    repo_path_with_namespace="group/payments",
    repo_name="payments",
    repo_url="https://gitlab.example.com/group/payments.git",
)


def _build(tmp_path: Path, name: str, code: str, settings: Settings):
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    source = root / name
    source.write_text(code, encoding="utf-8")
    builder = ChunkBuilder(settings, FileClassifier(settings))
    return builder.build_file(root, source, PROJECT, "develop", "abc123")


def _requires(language: str) -> None:
    if not TreeSitterChunker(Settings()).supports(language):
        pytest.skip(f"tree-sitter grammar for {language} not installed")


def test_tree_sitter_extracts_go_definitions(tmp_path: Path) -> None:
    _requires("go")
    code = (
        "package main\n"
        'import "fmt"\n'
        "type Server struct{}\n"
        "func (s *Server) Handle() { fmt.Println(loadPayment()) }\n"
        "func Add(a int) int { return a }\n"
    )
    _, chunks, symbols, edges = _build(tmp_path, "svc.go", code, Settings())
    names = {c.symbol_name for c in chunks}
    assert {"Server", "Handle", "Add"} <= names
    assert any(
        c.symbol_name == "Server" and c.chunk_kind == ChunkKind.CLASS_DEFINITION for c in chunks
    )
    assert {"loadPayment", "Println"} <= {t for c in chunks for t in c.calls_symbols}
    assert any(edge.edge_type == "CALLS" for edge in edges)


def test_tree_sitter_extracts_java_methods_with_parent(tmp_path: Path) -> None:
    _requires("java")
    code = (
        "package com.acme;\n"
        "public class PaymentService {\n"
        "  public int authorize(int x) { return helper(x); }\n"
        "}\n"
    )
    _, chunks, _, _ = _build(tmp_path, "PaymentService.java", code, Settings())
    method = next(c for c in chunks if c.symbol_name == "authorize")
    assert method.chunk_kind == ChunkKind.METHOD_DEFINITION
    assert method.parent_symbol_fqn == "PaymentService"


def test_tree_sitter_handles_typescript_decorated_route(tmp_path: Path) -> None:
    _requires("typescript")
    code = (
        "import { Router } from 'express';\n"
        "@Get('/payments/:id')\n"
        "export async function getPayment(req, res) {\n"
        "  return service.loadPayment(req.params.id);\n"
        "}\n"
    )
    _, chunks, _, edges = _build(tmp_path, "controller.ts", code, Settings())
    handler = next(c for c in chunks if c.symbol_name == "getPayment")
    assert "@Get('/payments/:id')" in handler.text
    assert any(edge.edge_type == "EXPOSES_ENDPOINT" for edge in edges)


def test_unsupported_language_falls_back_to_regex(tmp_path: Path) -> None:
    # Disabling tree-sitter must still produce definitions via the regex path.
    settings = Settings(use_tree_sitter=False)
    code = "export function helper() {\n  return doWork();\n}\n"
    _, chunks, _, _ = _build(tmp_path, "util.ts", code, settings)
    assert any(c.symbol_name == "helper" for c in chunks)


def test_chunker_reports_support() -> None:
    chunker = TreeSitterChunker(Settings())
    # A language we never map is never supported; chunk() returns None for it.
    assert chunker.supports("cobol") is False
    assert chunker.chunk("cobol", "IDENTIFICATION DIVISION.") is None
