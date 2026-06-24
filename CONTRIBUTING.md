# Contributing

Thanks for your interest in improving GitLab Code RAG.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

This installs the runtime dependencies plus the dev toolchain (ruff, mypy,
pytest) and the optional tree-sitter grammars.

## Before opening a pull request

Run the same checks CI runs:

```bash
ruff check .
ruff format --check .
mypy src
pytest -q --cov=code_rag --cov-report=term-missing
```

All four must pass. CI also builds the Docker image and runs the test suite
without the optional tree-sitter extras, so make sure the regex-chunker
fallback path still works if you touch chunking.

## Project conventions

- The package follows a hexagonal (ports-and-adapters) layout, one class per
  file. See the "Project structure" section in the README.
- Domain code (`domain/`) stays framework-free. Keep Elasticsearch, FastAPI,
  GitLab, and HTTP concerns in `adapters/` and `interfaces/`.
- Add or update tests for any behavior change. Prefer fakes over mocks for the
  ports.
- Keep public behavior documented in the README when you add configuration or
  endpoints.

## Commit messages

Write clear, imperative commit messages that explain the why, not just the
what.

## Reporting security issues

Do not open public issues for security problems. See [SECURITY.md](SECURITY.md).
