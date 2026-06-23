FROM python:3.11-slim

# git is required by the repo clone/fetch cache.
RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "code_rag.interfaces.rest.main:app", "--host", "0.0.0.0", "--port", "8000"]
