# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
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

### Changed
- The Docker image runs as a non-root user and declares a `HEALTHCHECK`.

## [0.1.0]

- Initial GitLab Code RAG indexer and retrieval service.
