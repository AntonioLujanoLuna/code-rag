# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Graph RAG retrieval: after RRF fusion, the strongest hits seed a
  query-type-aware traversal of the code-edge graph (calls/imports/tests/...) to
  pull in structurally related definitions. Neighbour symbols are resolved
  through the symbols index across all allowed projects, so neighbours can be
  cross-repository. Configurable via `CODE_RAG_GRAPH_EXPANSION_*`.
- Community detection at index time: the symbol/edge graph is clustered with
  label propagation and each cluster is stored in a new `code_communities` index
  with an extractive summary and embedding. A community-search retrieval leg
  surfaces these for global, architecture-level questions. New
  `code-rag rebuild-communities` CLI command.
- Optional cross-encoder rerank service (`CODE_RAG_RERANK_SERVICE_URL`) whose
  scores are blended into the heuristic reranker.
- Retrieval evaluation harness and `code-rag evaluate` CLI command reporting
  recall@k, precision@k, MRR, nDCG@k, and hit-rate against a golden dataset.
- `source_repo_path_with_namespace` is now stored on code edges, fixing the
  repo-path filter on edge search and enabling cross-repo edge resolution.
- Tests for the graph expander, community detector, retrieval evaluator, and
  cross-encoder reranker.
- Readiness probe at `GET /ready` that verifies Elasticsearch connectivity and
  returns 503 when the dependency is unreachable. `GET /health` remains a cheap
  liveness probe.
- Structured logging configuration (`CODE_RAG_LOG_LEVEL`, `CODE_RAG_LOG_FORMAT`)
  with a JSON formatter that preserves `extra` context fields. Wired into both
  the API and CLI entry points.
- Optional per-identity rate limiting on `/search` and `/answer`
  (`CODE_RAG_RATE_LIMIT_REQUESTS_PER_MINUTE`, disabled by default).
- `LICENSE` (MIT), `CONTRIBUTING.md`, `SECURITY.md`, and this changelog.
- CI now runs a Python 3.11/3.12 matrix, a minimal-install job exercising the
  regex-chunker fallback, and a Docker image build. Concurrent runs on the same
  ref are cancelled.
- Tests covering the GitLab webhook, indexing service, CLI commands, and the
  health/readiness endpoints.
- Expanded unit coverage for the permission service/store, query expander and
  classifier, answer grounding, reranker, HTTP retry helper, extractive answer
  provider, embedding-response parsing, and the indexing routes. Overall
  coverage 73% -> 82%.

### Changed
- The Docker image runs as a non-root user and declares a `HEALTHCHECK`.

## [0.1.0]

- Initial GitLab Code RAG indexer and retrieval service.
