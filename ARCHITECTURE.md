# Architecture

This document explains how the service is structured and *why*. For usage and
configuration see the [README](README.md); for schema migrations see
[docs/MIGRATIONS.md](docs/MIGRATIONS.md).

## Goals that shaped the design

- **Swappable infrastructure.** Elasticsearch, the embedding backend, the answer
  LLM, and GitLab are all details. The core logic must not import them directly.
- **Runnable with zero external services.** Defaults (hash embeddings, extractive
  answers, regex chunking) let the whole pipeline run in tests and locally.
- **Measurable retrieval.** Retrieval quality is gated by an evaluation harness,
  not eyeballed, so changes can be defended with numbers.
- **Operable in production.** Auth, permissions, rate limiting, structured logs,
  metrics, tracing, health probes, and online schema migration are first-class.

## Hexagonal (ports-and-adapters) layering

Dependencies point inwards only: `interfaces → apps → ports ← adapters`, with
`domain` at the centre depended on by everything and depending on nothing.

```
            ┌─────────────────────────────────────────────┐
 inbound    │ interfaces/   REST (FastAPI) + CLI (Typer)   │
            └───────────────┬─────────────────────────────┘
                            │ calls use-cases
            ┌───────────────▼─────────────────────────────┐
            │ apps/         application services           │
            │   indexing, retrieval, chunking, eval,       │
            │   permissions, jobs, secrets, metrics, auth  │
            └───────────────┬─────────────────────────────┘
                            │ depends on Protocols
            ┌───────────────▼─────────────────────────────┐
            │ ports/        SearchPort, JobStorePort,      │
            │   EmbeddingProvider, AnswerProvider, ...      │
            └───────────────▲─────────────────────────────┘
                            │ implemented by
            ┌───────────────┴─────────────────────────────┐
 outbound   │ adapters/     elasticsearch, embeddings,     │
            │   answer, git, gitlab, http, rerank,         │
            │   permissions                                 │
            └─────────────────────────────────────────────┘

            domain/  models, enums, value objects, ids — framework-free,
                     imported by every layer, importing none.
```

- **`domain/`** — Pydantic models and value objects (`CodeChunk`, `SearchHit`,
  `IndexJobRecord`, …). No I/O, no framework imports. One class per file.
- **`ports/`** — `typing.Protocol` interfaces describing what the application
  needs from the outside world. The overloaded index surface is deliberately
  split into focused `SearchPort`, `JobStorePort`, and `RepoStorePort` so each
  service depends only on the slice it uses.
- **`apps/`** — Application services (use cases). They orchestrate domain objects
  through ports and contain the business logic; they never import an adapter.
- **`adapters/`** — Concrete implementations of ports against real systems.
- **`interfaces/`** — Delivery mechanisms. `rest/` is a FastAPI app (one router
  per resource); `cli/` is a Typer app. Both are thin and wire dependencies via
  `interfaces/rest/dependencies.py`, which is the single composition root
  (cached singletons selected from `Settings`).

### Why Protocols instead of ABCs

Ports are structural (`Protocol`) so adapters and test fakes satisfy them by
shape without inheriting. Tests pass plain fakes (e.g. `FakeIndex`) and the
real Elasticsearch adapter is never imported in unit tests.

## Indexing pipeline

`apps/indexing/IndexingService` drives a full or incremental index:

1. **Clone/fetch** the repo at the target branch/commit via `adapters/git`
   (a local cache with per-repo locks).
2. **Classify** each file (`apps/classification`) — skip binary/generated/vendor.
3. **Chunk** (`apps/chunking`): Python via the stdlib AST; other languages via
   tree-sitter when a grammar is installed, else a regex fallback, else plain
   text. Each chunk carries symbols, calls, imports, and references.
4. **Redact secrets** (`apps/secrets`) before any text leaves for embedding.
5. **Embed** (`ports/EmbeddingProvider`): dense + late-interaction vectors,
   reusing stored vectors when a chunk's content hash is unchanged.
6. **Write** chunks/symbols/edges/files via `SearchPort.replace_file`
   (delete-by-file then bulk insert — active-snapshot semantics).
7. **Detect communities** (`apps/communities`): cluster the symbol/edge graph
   with label propagation and store an extractive summary per cluster.

Indexing runs through a **durable Elasticsearch-backed job queue**
(`apps/jobs`), so jobs survive restarts and any worker can claim queued or
abandoned-but-expired jobs. The REST API enqueues; the CLI runs synchronously.

## Retrieval pipeline

`apps/retrieval/RetrievalService.search` (see `retrieval_service.py`):

1. **Classify** the query and extract identifiers.
2. **Resolve permissions** — `user_id → allowed project ids` from the cache,
   intersected with any request filter. Every leg is filtered by this set.
3. **Run legs concurrently** on a shared bounded thread pool: BM25, dense kNN,
   symbol lookup, edge lookup, and (optionally) community search. The query
   embedding is cached in a bounded LRU; HyDE can augment the vector query.
4. **Fuse** the legs with Reciprocal Rank Fusion (RRF).
5. **Graph-expand**: the top fused hits seed a query-type-aware traversal of the
   code-edge graph, resolving neighbours through the symbols index across all
   allowed projects (so neighbours can be cross-repository).
6. **Rerank**: a heuristic reranker (deterministic, always available) optionally
   blended with a remote cross-encoder, plus late-interaction scoring.
7. **Assemble context** with commit-pinned source links.

The `/answer` endpoint adds grounding gates (`adapters/answer`): it refuses
rather than answer unsupported, and every answer carries source citations.

### Concurrency model

The Elasticsearch client is synchronous. `search` offloads to a thread and fans
the independent legs out over one shared `ThreadPoolExecutor` owned by the
(singleton) service — not a pool per request. CPU-light fusion/rerank run inline.

## Observability & operations

- **Logging** — structured JSON (`config/logging.py`) with `extra` context; a
  `RequestIdFilter` tags every in-request record with the correlation id.
- **Request ids** — a pure-ASGI middleware binds an id (inbound `X-Request-ID`
  or generated), echoes it in the response header, and exception handlers return
  `{detail, request_id}` JSON so failures are traceable end to end.
- **Metrics** — Prometheus exposition at `/metrics`, including per-leg latency
  histograms and cache hit/miss counters.
- **Tracing** — OpenTelemetry spans wrap the search pipeline, each leg, and the
  Elasticsearch calls. No-op until an exporter is configured.
- **Health** — `/health` (cheap liveness) and `/ready` (pings Elasticsearch).
- **Schema migration** — aliases over versioned backing indices; `code-rag
  reindex` rebuilds and atomically swaps. See docs/MIGRATIONS.md.

## The Elasticsearch adapter

`adapters/elasticsearch/` is split by responsibility rather than living in one
class: `_base.py` (connection, index lifecycle, filters, document mapping),
`_search.py` (query-time search), `_indexing.py` (write path), and `_jobs.py`
(job queue). `ElasticsearchCodeIndex` (in `index.py`) composes them; each mixin
is itself a usable adapter for its port slice.

## Testing strategy

- **Unit tests** use in-memory fakes for every port — no Elasticsearch, no
  network — and are what the coverage gate measures.
- **Integration tests** (`tests/test_elasticsearch_integration.py`) run against
  a real Elasticsearch service container in CI.
- **A `test-minimal` job** installs without optional extras to prove the regex
  chunker fallback path.
- **A retrieval-quality gate** seeds a corpus and asserts recall/MRR/nDCG floors
  so retrieval regressions fail the build.
