from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from code_rag.adapters.gitlab.gitlab_client import GitLabClient
from code_rag.apps.eval.retrieval_evaluator import RetrievalEvaluator
from code_rag.config.logging import configure_logging
from code_rag.config.settings import get_settings
from code_rag.domain.models import ChangedFile, GitLabProject, PermissionRecord, SearchRequest
from code_rag.interfaces.rest.dependencies import (
    get_answer_provider,
    get_gitlab,
    get_index,
    get_indexing_service,
    get_job_store,
    get_permission_service,
    get_permission_store,
    get_retrieval_service,
)

app = typer.Typer(help="GitLab code RAG indexer and retrieval service.")


@app.callback()
def _configure() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)


@app.command("init-indices")
def init_indices() -> None:
    get_index().ensure_indices()
    get_permission_store().ensure_index()
    typer.echo("Elasticsearch indices are ready.")


@app.command("reindex")
def reindex(
    only: str | None = typer.Option(
        None, help="Restrict to a single alias, e.g. the configured code_chunks index."
    ),
) -> None:
    """Migrate managed indices to the current CODE_RAG_INDEX_VERSION.

    Creates the current-version backing index from its mapping, copies documents
    from the alias's existing backing, and atomically swaps the alias. Safe to
    re-run. Bump CODE_RAG_INDEX_VERSION before running to roll a mapping change.
    """
    results = get_index().reindex(only=only)
    typer.echo(json.dumps({"reindexed": results}, indent=2))


@app.command("index-project")
def index_project(
    project_id: str = typer.Option(..., help="GitLab project id."),
    repo_path_with_namespace: str | None = typer.Option(
        None, help="GitLab namespace/project path."
    ),
    repo_url: str | None = typer.Option(None, help="Clone URL. If omitted, GitLab API is used."),
    repo_name: str | None = typer.Option(None, help="Human repo name."),
    branch: str | None = typer.Option(None, help="Branch to index."),
    commit_sha: str | None = typer.Option(None, help="Commit SHA to check out."),
) -> None:
    gitlab = get_gitlab()
    project = _project(gitlab, project_id, repo_path_with_namespace, repo_url, repo_name)
    service = get_indexing_service()
    result = service.full_index_project(project, branch, commit_sha)
    get_job_store().record_job(result)
    typer.echo(result.model_dump_json(indent=2))
    raise typer.Exit(0 if result.status == "succeeded" else 1)


@app.command("incremental-index")
def incremental_index(
    project_id: str = typer.Option(..., help="GitLab project id."),
    old_sha: str = typer.Option(..., help="Previous commit SHA."),
    new_sha: str = typer.Option(..., help="New commit SHA."),
    repo_path_with_namespace: str | None = typer.Option(None),
    repo_url: str | None = typer.Option(None),
    repo_name: str | None = typer.Option(None),
    branch: str | None = typer.Option(None),
) -> None:
    gitlab = get_gitlab()
    project = _project(gitlab, project_id, repo_path_with_namespace, repo_url, repo_name)
    changes = gitlab.compare(project_id, old_sha, new_sha)
    service = get_indexing_service()
    result = service.incremental_index_project(project, old_sha, new_sha, changes, branch)
    get_job_store().record_job(result)
    typer.echo(result.model_dump_json(indent=2))
    raise typer.Exit(0 if result.status == "succeeded" else 1)


@app.command("search")
def search(
    query: str,
    user_id: str | None = typer.Option(None, help="Synced permission user id."),
    allowed_project_id: list[str] | None = typer.Option(None, help="Optional project filter."),
    branch: str | None = typer.Option(None),
    repo_path_with_namespace: str | None = typer.Option(None),
    top_k: int = typer.Option(8, min=1, max=50),
) -> None:
    result = asyncio.run(
        get_retrieval_service().search(
            SearchRequest(
                query=query,
                user_id=user_id,
                allowed_project_ids=allowed_project_id or [],
                branch=branch,
                repo_path_with_namespace=repo_path_with_namespace,
                top_k=top_k,
            )
        )
    )
    typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))


@app.command("answer")
def answer(
    query: str,
    user_id: str | None = typer.Option(None, help="Synced permission user id."),
    allowed_project_id: list[str] | None = typer.Option(None, help="Optional project filter."),
    branch: str | None = typer.Option(None),
    top_k: int = typer.Option(8, min=1, max=50),
) -> None:
    search_result = asyncio.run(
        get_retrieval_service().search(
            SearchRequest(
                query=query,
                user_id=user_id,
                allowed_project_ids=allowed_project_id or [],
                branch=branch,
                top_k=top_k,
            )
        )
    )
    answer_text = get_answer_provider().answer(search_result, 12_000)
    typer.echo(answer_text)


@app.command("evaluate")
def evaluate(
    dataset: Path = typer.Argument(..., help="Path to a golden retrieval dataset JSON file."),
    k: int = typer.Option(10, min=1, max=100, help="Cutoff for recall@k / nDCG@k."),
    min_recall: float = typer.Option(0.0, min=0.0, max=1.0),
    min_mrr: float = typer.Option(0.0, min=0.0, max=1.0),
    min_ndcg: float = typer.Option(0.0, min=0.0, max=1.0),
) -> None:
    evaluator = RetrievalEvaluator(get_retrieval_service(), k=k)
    data = evaluator.load(dataset)
    report = asyncio.run(evaluator.aevaluate(data))
    typer.echo(json.dumps(report, indent=2))
    aggregate = report["aggregate"]
    failed = (
        aggregate["recall_at_k"] < min_recall
        or aggregate["mrr"] < min_mrr
        or aggregate["ndcg_at_k"] < min_ndcg
    )
    raise typer.Exit(1 if failed else 0)


@app.command("rebuild-communities")
def rebuild_communities(
    project_id: str = typer.Option(..., help="GitLab project id."),
    repo_path_with_namespace: str | None = typer.Option(None),
    repo_url: str | None = typer.Option(None),
    repo_name: str | None = typer.Option(None),
    branch: str | None = typer.Option(None, help="Branch to rebuild communities for."),
    commit_sha: str = typer.Option("", help="Commit SHA to stamp on communities."),
) -> None:
    gitlab = get_gitlab()
    project = _project(gitlab, project_id, repo_path_with_namespace, repo_url, repo_name)
    service = get_indexing_service()
    service.rebuild_communities(project, branch or get_settings().branch, commit_sha)
    typer.echo("Communities rebuilt.")


@app.command("sync-permissions")
def sync_permissions(
    user_id: str = typer.Option(..., help="Application/GitLab user id."),
    project_id: list[str] = typer.Option(..., help="Accessible GitLab project id."),
    tenant_id: str = typer.Option("default", help="Tenant id."),
) -> None:
    record = get_permission_service().upsert(
        PermissionRecord(
            user_id=user_id,
            tenant_id=tenant_id,
            accessible_project_ids=project_id,
        )
    )
    typer.echo(record.model_dump_json(indent=2))


@app.command("webhook-payload-changes")
def webhook_payload_changes(path: str) -> None:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    changes = [
        ChangedFile(
            old_path=item.get("old_path") or item.get("new_path"),
            new_path=item.get("new_path") or item.get("old_path"),
            added=bool(item.get("new_file")),
            deleted=bool(item.get("deleted_file")),
            renamed=bool(item.get("renamed_file")),
            modified=not any(
                [item.get("new_file"), item.get("deleted_file"), item.get("renamed_file")]
            ),
        )
        for item in payload.get("commits", [])
    ]
    typer.echo(json.dumps([change.model_dump() for change in changes], indent=2))


def _project(
    gitlab: GitLabClient,
    project_id: str,
    repo_path_with_namespace: str | None,
    repo_url: str | None,
    repo_name: str | None,
) -> GitLabProject:
    if repo_path_with_namespace and repo_url:
        return GitLabProject(
            gitlab_project_id=project_id,
            repo_path_with_namespace=repo_path_with_namespace,
            repo_name=repo_name or repo_path_with_namespace.rsplit("/", 1)[-1],
            repo_url=repo_url,
        )
    return gitlab.get_project(project_id)
