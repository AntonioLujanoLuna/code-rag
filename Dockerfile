FROM python:3.11-slim

# git is required by the repo clone/fetch cache. curl is used by HEALTHCHECK.
RUN apt-get update \
    && apt-get install --no-install-recommends -y git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

# Run as an unprivileged user. Create after install so site-packages stay
# root-owned (read-only to the runtime user).
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "code_rag.interfaces.rest.main:app", "--host", "0.0.0.0", "--port", "8000"]
