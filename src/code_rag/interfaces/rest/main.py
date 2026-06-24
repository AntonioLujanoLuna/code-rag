from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from code_rag.config.logging import configure_logging
from code_rag.config.settings import get_settings
from code_rag.interfaces.rest.dependencies import (
    get_gitlab,
    get_indexing_service,
    get_job_queue,
    get_metrics,
)
from code_rag.interfaces.rest.routers import ROUTERS

_settings = get_settings()
configure_logging(_settings.log_level, _settings.log_format)

logger = logging.getLogger(__name__)


def _dependency(app: FastAPI, provider):
    return app.dependency_overrides.get(provider, provider)()


@asynccontextmanager
async def lifespan(app: FastAPI):
    queue = None
    try:
        queue = _dependency(app, get_job_queue)
        if hasattr(queue, "start"):
            queue.start(_dependency(app, get_indexing_service), _dependency(app, get_gitlab))
    except RuntimeError:
        logger.warning("Index workers were not started", exc_info=True)
    try:
        yield
    finally:
        if queue is not None and hasattr(queue, "stop"):
            queue.stop()


app = FastAPI(title="GitLab Code RAG", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    started = time.perf_counter()
    metrics = get_metrics()
    try:
        response = await call_next(request)
    except Exception:
        duration = time.perf_counter() - started
        metrics.increment("http_requests_failed_total")
        metrics.observe("http_request_duration_seconds", duration)
        logger.exception(
            "HTTP request failed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "duration_seconds": duration,
            },
        )
        raise
    duration = time.perf_counter() - started
    metrics.increment("http_requests_total")
    metrics.observe("http_request_duration_seconds", duration)
    response.headers["X-Process-Time-Ms"] = f"{duration * 1000:.2f}"
    logger.info(
        "HTTP request completed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_seconds": duration,
        },
    )
    return response


for _router in ROUTERS:
    app.include_router(_router)
