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
- Syntax-aware chunking: Python via the stdlib AST, and tree-sitter AST
  chunking for JS/TS, Java, Go, Rust, C/C++, C#, Ruby and PHP (one definition
  per chunk, with parent nesting, calls, imports and references). Regex chunking
  is the fallback when a grammar is unavailable, and text chunking covers
  docs/config.
- Elasticsearch mappings for:
  - `code_chunks_v1`
  - `code_symbols_v1`
  - `code_edges_v1`
  - `code_communities_v1`
  - `code_files_v1`
  - `code_repos_v1`
  - `code_index_jobs_v1`
- Bulk indexing and delete-by-file replacement.
- Durable Elasticsearch-backed indexing job queue for full and incremental
  indexing across API restarts and multiple workers.
- Incremental indexing from GitLab push webhooks or CLI `old_sha -> new_sha`,
  including stale deletion for removed or newly unindexable files.
- Query classification, identifier extraction, BM25 + kNN retrieval, symbol
  search, graph edge search, RRF fusion, and source-linked context assembly.
- Graph RAG: after fusion, the strongest hits seed a query-type-aware traversal
  of the code-edge graph (calls/imports/tests/...) to pull in structurally
  related definitions — including across repositories, since edge targets are
  resolved through the symbols index for all allowed projects.
- Community detection: the symbol/edge graph is clustered per repo at index time
  (label propagation) and each cluster gets an extractive summary, so global,
  architecture-level questions ("what subsystems exist?") can retrieve cluster
  overviews instead of only chunk-level matches.
- Optional cross-encoder rerank service that re-scores the top fused candidates,
  blended with the heuristic reranker (which remains the local fallback).
- Retrieval evaluation harness computing recall@k, precision@k, MRR, nDCG@k and
  hit-rate against a golden dataset.
- Permission cache with server-side `user_id -> project_ids` enforcement.
- Late-interaction embedding adapter with deterministic local fallback.
- Secret scanning and redaction before embedding/indexing.
- Repo metadata enrichment for ownership, domain, and deployment context.
- Grounded answer endpoint with mandatory source citations and refusal gates.
- Prometheus-format `/metrics` endpoint with retrieval-leg histograms.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d elasticsearch
cp .env.example .env
code-rag init-indices
uvicorn code_rag.interfaces.rest.main:app --reload
```

On Windows PowerShell, use `.\.venv\Scripts\Activate.ps1` and `copy .env.example .env`.

To build and run the API in Docker:

```bash
docker build -t code-rag .
docker run --rm -p 8000:8000 --env-file .env code-rag
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
- `CODE_RAG_EMBEDDING_BACKEND=auto`
- `CODE_RAG_LATE_INTERACTION_DIMENSION=128`
- `CODE_RAG_MAX_INDEX_WORKERS=2`
- `CODE_RAG_INDEX_JOB_POLL_INTERVAL_SECONDS=0.5`
- `CODE_RAG_INDEX_JOB_LOCK_TTL_SECONDS=900`
- `CODE_RAG_ALLOW_REQUEST_SUPPLIED_PERMISSIONS=false`
- `CODE_RAG_QUERY_EMBEDDING_CACHE_TTL_SECONDS=300`
- `CODE_RAG_PERMISSION_CACHE_TTL_SECONDS=60`
- `CODE_RAG_SECRET_SCANNING_ENABLED=true`
- `CODE_RAG_SKIP_CHUNKS_WITH_HIGH_CONFIDENCE_SECRETS=false`
- `CODE_RAG_MIN_ANSWER_SOURCES=1`
- `CODE_RAG_LOG_LEVEL=INFO`
- `CODE_RAG_LOG_FORMAT=json` (`json` for aggregators, `text` for local dev)
- `CODE_RAG_RATE_LIMIT_REQUESTS_PER_MINUTE=0` (0 disables per-identity rate
  limiting on `/search` and `/answer`)

Every retrieval should pass `user_id`. The service resolves allowed GitLab
project IDs from its permission cache and intersects them with optional request
project filters. Set `CODE_RAG_ALLOW_REQUEST_SUPPLIED_PERMISSIONS=true` only for
local development.

## Authentication

`CODE_RAG_API_KEYS` is a JSON object mapping API key to a trusted `user_id`,
e.g. `{"svc-key-123":"alice"}`. When it is set, every protected endpoint
(`/search`, `/answer`, `/index/*`, `/indices/init`, `/permissions`) requires a
valid `X-API-Key` header, and the identity bound to that key overrides the
`user_id` in the request body — a request cannot act as a different user. When
`CODE_RAG_API_KEYS` is empty (the default) the service runs in development mode:
no key is required and the request-supplied `user_id` is trusted. `/health` and
the GitLab webhook (token-authenticated separately) are always open.

Permission grants are stored in Elasticsearch (`code_permissions_v1`) and index
job status in `code_job_status_v1`, so authorization and job polling stay
consistent across multiple API workers and survive restarts.

## Answer generation

`CODE_RAG_ANSWER_PROVIDER` selects the backend: `extractive` (default, builds a
grounded source list locally), `anthropic` (calls the Claude Messages API with
`CODE_RAG_ANTHROPIC_API_KEY`/`CODE_RAG_ANTHROPIC_MODEL`, requires the
`code-rag[anthropic]` extra), or set `CODE_RAG_LLM_ANSWER_SERVICE_URL` to post to
your own service. All providers apply the same citation and refusal gates.

If `CODE_RAG_EMBEDDING_SERVICE_URL` is set, the embedding adapter posts one
batched request per file instead of one request per chunk:

```json
{"texts": ["...", "..."], "input_type": "document"}
```

It accepts either a top-level list or a `results`/`data` list; each item may
carry `late_interaction`, `late_interaction_embeddings`, or `embeddings`, plus
an optional `dense`/`embedding`. If no dense vector is returned, the adapter
mean-pools the late-interaction vectors for Elasticsearch kNN. Unchanged chunks
reuse their previously stored embeddings (keyed by an input-content hash) so
re-indexing avoids redundant embedding calls.

For a real local semantic embedding backend, install
`pip install -e ".[local-embeddings]"` and set
`CODE_RAG_EMBEDDING_BACKEND=fastembed`. The hash backend remains the default
zero-dependency fallback for development and tests.

If `CODE_RAG_API_KEYS`, `CODE_RAG_API_KEY_USERS`, or
`CODE_RAG_ADMIN_API_KEYS` is configured, API routes require `X-API-Key`. Store
SHA-256 hashes, not plaintext keys:

```json
{"alice":[{"sha256":"<sha256-hex>","expires_at":"2027-01-01T00:00:00Z"}]}
```

Admin keys use either an object or list shape:

```json
[{"id":"ops","sha256":"<sha256-hex>"}]
```

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

```bash
uvicorn code_rag.interfaces.rest.main:app --host 0.0.0.0 --port 8000
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

Jobs are stored in Elasticsearch with their payloads. Any API worker can claim
queued jobs, and abandoned running jobs are claimable again after
`CODE_RAG_INDEX_JOB_LOCK_TTL_SECONDS`.

GitLab push webhook:

```http
POST /webhooks/gitlab
X-Gitlab-Token: <CODE_RAG_GITLAB_WEBHOOK_SECRET>
```

The webhook indexes only pushes to the configured branch.

## Health checks

Two probes are exposed for load balancers and orchestrators:

- `GET /health` — liveness. Cheap, no I/O; returns `200` whenever the process
  is serving.
- `GET /ready` — readiness. Pings Elasticsearch and returns `503` when it is
  unreachable so traffic is not routed to an instance that cannot serve.

Per-identity rate limiting can be enabled on `/search` and `/answer` with
`CODE_RAG_RATE_LIMIT_REQUESTS_PER_MINUTE`. Requests are keyed by the
authenticated `user_id` (falling back to the client host), and exceeding the
limit returns `429`.

Logs are emitted to stdout. `CODE_RAG_LOG_FORMAT=json` produces single-line
structured JSON (with `extra` context fields preserved) for log aggregators;
`text` is human-readable for local development.

## Project structure

The package follows a hexagonal (ports-and-adapters) layout, one class per file:

```
src/code_rag/
  config/        Settings
  domain/        Models, enums, value objects, ids (framework-free)
  ports/         Protocols: SearchPort, JobStorePort, RepoStorePort,
                 EmbeddingProvider, AnswerProvider, PermissionStorePort, ...
  apps/          Application services (use cases): indexing, retrieval,
                 chunking, classification, secrets, metadata, jobs, metrics,
                 permissions, auth
  adapters/      Concrete implementations: elasticsearch, embeddings, answer,
                 git, gitlab, http, permissions
  interfaces/
    rest/        FastAPI app
      main.py        app + middleware
      dependencies.py
      security.py    API-key auth dependency
      routers/       one router per resource + request schemas
    cli/         Typer CLI
```

The overloaded search/index port was split into focused `SearchPort`,
`JobStorePort`, and `RepoStorePort` protocols so each service depends only on
what it uses.

Tree-sitter grammars are an optional install (`pip install -e ".[tree-sitter]"`);
each grammar wheel bundles its compiled parser so there is no runtime download.
Set `CODE_RAG_USE_TREE_SITTER=false` to force the regex chunker.

## Graph RAG, communities, and reranking

Retrieval combines flat legs (BM25, kNN, symbol, edge) with two graph-aware
stages:

- **Graph expansion.** After RRF fusion, the top
  `CODE_RAG_GRAPH_EXPANSION_SEED_HITS` hits seed a traversal of the code-edge
  graph. The edge types followed depend on the classified query type (e.g.
  `TESTS` edges for test questions, `CALLS`/`REFERENCES` for usage questions),
  and `CODE_RAG_GRAPH_EXPANSION_HOPS` controls multi-hop depth. Neighbour
  symbols are resolved to their definition chunks through the symbols index for
  every allowed project, so neighbours can live in other repositories. Disable
  with `CODE_RAG_GRAPH_EXPANSION_ENABLED=false`.
- **Community summaries.** At full-index time the symbol/edge graph is clustered
  with label propagation and each cluster (≥ `CODE_RAG_COMMUNITY_MIN_SIZE`
  members) is stored in `code_communities` with an extractive summary and an
  embedding. A community-search leg surfaces these summaries for global,
  architecture-level questions. Rebuild them for an already-indexed project with
  `code-rag rebuild-communities --project-id 123`.

Set `CODE_RAG_RERANK_SERVICE_URL` to post the top fused candidates to a
cross-encoder rerank service (`{"query", "documents"}` in, a parallel `scores`
list out). Its scores are min-max normalised and blended into the heuristic
reranker, which stays the deterministic local fallback when no service is set.

## Evaluation

Measure retrieval quality against a golden dataset of queries and their relevant
chunk ids / file paths / symbol FQNs (see `eval/dataset.example.json`):

```bash
code-rag evaluate --dataset eval/dataset.example.json --k 10
```

The report includes per-case and macro-averaged recall@k, precision@k, MRR,
nDCG@k, and hit-rate so retrieval changes can be measured rather than eyeballed.

## Production notes

`/metrics` returns Prometheus exposition format by default. Send
`Accept: application/json` for the legacy JSON snapshot.

The default embedding backend is deterministic and local so the system is
runnable immediately. In production, configure `CODE_RAG_EMBEDDING_SERVICE_URL`
or `CODE_RAG_EMBEDDING_BACKEND=fastembed` and store late-interaction vectors
alongside the dense vector used by Elasticsearch kNN.

Run retrieval-quality gates with:

```powershell
code-rag evaluate tests/fixtures/retrieval_golden.json --allowed-project-id 123 --min-recall 1.0
```

CI runs the evaluator against a seeded Elasticsearch service container.

The first version stores only active snapshots. Historical snapshots can be
added by changing replacement semantics from delete-and-insert to
`active_snapshot=false` plus insert.
