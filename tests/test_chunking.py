from __future__ import annotations

from pathlib import Path

from code_rag.application.chunking import ChunkBuilder
from code_rag.application.file_classifier import FileClassifier
from code_rag.application.repo_metadata import RepoMetadataProvider
from code_rag.application.secrets import SecretScanner
from code_rag.models import ChunkKind, GitLabProject, SymbolRole
from code_rag.settings import Settings


def test_python_chunking_extracts_definitions(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    source = root / "payments.py"
    source.write_text(
        "\n".join(
            [
                "class PaymentService:",
                "    def authorize(self, request):",
                "        return helper()",
                "",
                "def helper():",
                "    return 'ok'",
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(clone_cache_dir=tmp_path / "cache", worktree_dir=tmp_path / "worktrees")
    builder = ChunkBuilder(settings, FileClassifier(settings))
    metadata, chunks, symbols, edges = builder.build_file(
        root,
        source,
        GitLabProject(
            gitlab_project_id="123",
            repo_path_with_namespace="group/payments",
            repo_name="payments",
            repo_url="https://gitlab.example.com/group/payments.git",
        ),
        "develop",
        "abc123",
    )

    assert metadata.file_path == "payments.py"
    assert {chunk.symbol_name for chunk in chunks} >= {"PaymentService", "authorize", "helper"}
    assert any(chunk.chunk_kind == ChunkKind.METHOD_DEFINITION for chunk in chunks)
    assert all(chunk.symbol_role == SymbolRole.DEFINITION for chunk in chunks)
    assert {symbol.symbol_name for symbol in symbols} >= {"PaymentService", "authorize", "helper"}
    assert any(edge.edge_type == "CALLS" and edge.target_symbol_fqn == "helper" for edge in edges)
    assert chunks[0].gitlab_blob_url.endswith("/-/blob/abc123/payments.py#L1-L3")


def test_chunking_redacts_secrets_and_applies_repo_metadata(tmp_path: Path) -> None:
    metadata_file = tmp_path / "repos.json"
    metadata_file.write_text(
        """
        {
          "repos": [
            {
              "repo_path_with_namespace": "group/payments",
              "service_name": "payments-api",
              "team_owner": "payments",
              "business_domain": "commerce"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    root = tmp_path / "repo"
    root.mkdir()
    source = root / "config.py"
    source.write_text('API_TOKEN = "ghp_abcdefghijklmnopqrstuvwxyzABCDEFGHIJ"\n', encoding="utf-8")
    settings = Settings(
        clone_cache_dir=tmp_path / "cache",
        worktree_dir=tmp_path / "worktrees",
        repo_metadata_path=metadata_file,
    )
    builder = ChunkBuilder(
        settings,
        FileClassifier(settings),
        secret_scanner=SecretScanner(),
        repo_metadata=RepoMetadataProvider(settings),
    )

    metadata, chunks, _, _ = builder.build_file(
        root,
        source,
        GitLabProject(
            gitlab_project_id="123",
            repo_path_with_namespace="group/payments",
            repo_name="payments",
            repo_url="https://gitlab.example.com/group/payments.git",
        ),
        "develop",
        "abc123",
    )

    assert metadata.team_owner == "payments"
    assert metadata.service_name == "payments-api"
    assert chunks[0].team_owner == "payments"
    assert "[REDACTED_SECRET]" in chunks[0].text
    assert "ghp_" not in chunks[0].text
    assert chunks[0].secret_redactions_count == 1


def test_regex_parser_extracts_decorated_route_handler(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    source = root / "controller.ts"
    source.write_text(
        "\n".join(
            [
                "import { Router } from 'express';",
                "@Get('/payments/:id')",
                "export async function getPayment(req, res) {",
                "  return service.loadPayment(req.params.id);",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(clone_cache_dir=tmp_path / "cache", worktree_dir=tmp_path / "worktrees")
    builder = ChunkBuilder(settings, FileClassifier(settings))

    _, chunks, _, edges = builder.build_file(
        root,
        source,
        GitLabProject(
            gitlab_project_id="123",
            repo_path_with_namespace="group/payments",
            repo_name="payments",
            repo_url="https://gitlab.example.com/group/payments.git",
        ),
        "develop",
        "abc123",
    )

    assert chunks[0].symbol_name == "getPayment"
    assert "@Get('/payments/:id')" in (chunks[0].text or "")
    assert any(edge.edge_type == "EXPOSES_ENDPOINT" for edge in edges)
