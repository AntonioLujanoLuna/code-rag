from __future__ import annotations

import json

import pytest

try:
    import importlib

    from typer.testing import CliRunner

    # The cli package __init__ re-exports the Typer instance as ``app``, which
    # shadows the ``app`` submodule on attribute access; load it explicitly.
    cli_app = importlib.import_module("code_rag.interfaces.cli.app")
except Exception:  # pragma: no cover - optional test deps
    CliRunner = None


runner = CliRunner() if CliRunner is not None else None


@pytest.fixture(autouse=True)
def _skip_without_typer():
    if CliRunner is None:  # pragma: no cover
        pytest.skip("typer test runner unavailable")


def test_app_help_lists_commands() -> None:
    result = runner.invoke(cli_app.app, ["--help"])
    assert result.exit_code == 0
    for command in ("index-project", "search", "answer", "sync-permissions"):
        assert command in result.output


def test_search_help_documents_options() -> None:
    # Exercises the command wiring and the root callback without touching any
    # external service.
    result = runner.invoke(cli_app.app, ["search", "--help"])
    assert result.exit_code == 0
    assert "--user-id" in result.output
    assert "--top-k" in result.output


def test_webhook_payload_changes_command(tmp_path) -> None:
    payload = {
        "commits": [
            {"new_path": "a.py", "new_file": True},
            {"old_path": "b.py", "deleted_file": True},
        ]
    }
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(cli_app.app, ["webhook-payload-changes", str(payload_file)])

    assert result.exit_code == 0, result.output
    changes = json.loads(result.output)
    assert changes[0]["new_path"] == "a.py"
    assert changes[0]["added"] is True
    assert changes[1]["deleted"] is True
