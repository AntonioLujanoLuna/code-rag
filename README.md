# GitLab Code RAG

An MVP implementation of GitLab codebase RAG using Elasticsearch as the hybrid
lexical/vector search engine.

The service indexes selected GitLab repositories on a canonical branch
(`develop` by default), chunks source files with code-aware metadata, stores
commit-backed source links, and exposes a retrieval API that combines BM25,
vector search, symbol/edge lookup, late-interaction reranking, and metadata
reranking.

## What is included

- GitLab project discovery and compare API client.
- Local clone/fetch cache using `git`.
- File classification, ignore rules, binary/generated/vendor detection.
- Syntax-aware chunking for Python plus pragmatic regex chunking for common
  JVM/JS/TS/C-like languages, with text fallback for docs/config.
- Elasticsearch mappings for:
  - `code_chunks_v1`
  - `code_symbols_v1`
  - `code_edges_v1`
  - `code_files_v1`
  - `code_repos_v1`
  - `code_index_jobs_v1`
- Bulk indexing and delete-by-file replacement.
- Async indexing job queue for full and incremental indexing.
- Incremental indexing from GitLab push webhooks or CLI `old_sha -> new_sha`,
  including stale deletion for removed or newly unindexable files.
- Query classification, identifier extraction, BM25 + kNN retrieval, symbol
  search, graph edge search, RRF fusion, and source-linked context assembly.
- Permission cache with server-side `user_id -> project_ids` enforcement.
- Late-interaction embedding adapter with deterministic local fallback.
- Secret scanning and redaction before embedding/indexing.
- Repo metadata enrichment for ownership, domain, and deployment context.
- Grounded answer endpoint with mandatory source citations and refusal gates.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
docker compose up -d elasticsearch
copy .env.example .env
code-rag init-indices
uvicorn code_rag.api:app --reload
```

Index a selected project. The API queues indexing jobs; the CLI still runs
indexing synchronously for local operations.

```powershell
code-rag index-project --project-id 123 --repo-path-with-namespace group/service
```

Query:

```powershell
code-rag sync-permissions --user-id alice --project-id 123
code-rag search "Where is PaymentService implemented?" --user-id alice --allowed-project-id 123
code-rag answer "Where is PaymentService implemented?" --user-id alice --allowed-project-id 123
```

## Configuration

Environment variables are defined in `.env.example`.

Important defaults:

- `CODE_RAG_BRANCH=develop`
- `CODE_RAG_TENANT_ID=default`
- `CODE_RAG_EMBEDDING_DIMENSION=384`
- `CODE_RAG_LATE_INTERACTION_DIMENSION=128`
- `CODE_RAG_MAX_INDEX_WORKERS=2`
- `CODE_RAG_ALLOW_REQUEST_SUPPLIED_PERMISSIONS=false`
- `CODE_RAG_SECRET_SCANNING_ENABLED=true`
- `CODE_RAG_SKIP_CHUNKS_WITH_HIGH_CONFIDENCE_SECRETS=false`
- `CODE_RAG_MIN_ANSWER_SOURCES=1`

Every retrieval should pass `user_id`. The service resolves allowed GitLab
project IDs from its permission cache and intersects them with optional request
project filters. Set `CODE_RAG_ALLOW_REQUEST_SUPPLIED_PERMISSIONS=true` only for
local development.

If `CODE_RAG_EMBEDDING_SERVICE_URL` is set, the embedding adapter posts:

```json
{"text": "...", "input_type": "document"}
```

It expects either `late_interaction`, `late_interaction_embeddings`, or
`embeddings` in the response. If no dense vector is returned, the adapter
mean-pools the late-interaction vectors for Elasticsearch kNN.

Repo metadata can be provided with `CODE_RAG_REPO_METADATA_PATH` pointing to a
JSON or TOML file. JSON shape:

```json
{
  "repos": [
    {
      "repo_path_with_namespace": "group/payments",
      "service_name": "payments-api",
      "team_owner": "payments",
      "business_domain": "commerce",
      "slack_channel": "#payments",
      "jira_project": "PAY",
      "primary_language": "python",
      "service_type": "api",
      "deployment_name": "payments-api"
    }
  ]
}
```

Secret scanning redacts common high-risk tokens before embeddings are created.
Set `CODE_RAG_SKIP_CHUNKS_WITH_HIGH_CONFIDENCE_SECRETS=true` to omit chunks with
high-confidence findings entirely.

## API

Start the API:

```powershell
uvicorn code_rag.api:app --host 0.0.0.0 --port 8000
```

Search:

```http
POST /search
{
  "query": "Where is FooClient implemented?",
  "user_id": "alice",
  "allowed_project_ids": ["123"],
  "branch": "develop"
}
```

Answer:

```http
POST /answer
{
  "query": "How does PaymentService authorize payments?",
  "user_id": "alice",
  "allowed_project_ids": ["123"]
}
```

The answer response includes `grounded`, `refusal_reason`, `source_coverage`,
and source citations. If retrieval does not meet the configured evidence
thresholds, the service returns a refusal instead of an unsupported answer.

Permissions:

```http
POST /permissions
{
  "user_id": "alice",
  "tenant_id": "default",
  "accessible_project_ids": ["123"]
}
```

Indexing:

```http
POST /index/project
```

returns a queued `job_id`. Poll it with:

```http
GET /jobs/{job_id}
```

GitLab push webhook:

```http
POST /webhooks/gitlab
X-Gitlab-Token: <CODE_RAG_GITLAB_WEBHOOK_SECRET>
```

The webhook indexes only pushes to the configured branch.

## Production notes

The default embedding backend is deterministic and local so the system is
runnable immediately. In production, configure `CODE_RAG_EMBEDDING_SERVICE_URL`
to call your embedding service and store late-interaction vectors alongside the
dense vector used by Elasticsearch kNN.

The first version stores only active snapshots. Historical snapshots can be
added by changing replacement semantics from delete-and-insert to
`active_snapshot=false` plus insert.
