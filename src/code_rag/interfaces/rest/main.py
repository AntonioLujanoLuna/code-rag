from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, MutableMapping
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from code_rag.config.logging import configure_logging
from code_rag.config.request_context import get_request_id, set_request_id
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

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]

REQUEST_ID_HEADER = "x-request-id"


class RequestContextMiddleware:
    """Pure-ASGI middleware that binds a request id for the whole request.

    Implemented at the ASGI layer (rather than ``@app.middleware``) so the
    ``ContextVar`` it sets propagates to endpoints and exception handlers, and
    so the id is echoed back in the ``X-Request-ID`` response header.
    """

    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        incoming = headers.get(REQUEST_ID_HEADER.encode())
        request_id = set_request_id(incoming.decode("latin-1") if incoming else None)

        async def send_with_request_id(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                response_headers = message.setdefault("headers", [])
                key = REQUEST_ID_HEADER.encode()
                if not any(name == key for name, _ in response_headers):
                    response_headers.append((key, request_id.encode()))
            await send(message)

        await self.app(scope, receive, send_with_request_id)


def _error_response(status_code: int, detail: Any) -> JSONResponse:
    request_id = get_request_id()
    # Set the header here too: the catch-all 500 handler runs in Starlette's
    # outermost ServerErrorMiddleware, whose response bypasses the request-id
    # ASGI wrapper, so error responses would otherwise lose the header.
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "request_id": request_id},
        headers=headers,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _error_response(exc.status_code, exc.detail)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return _error_response(422, exc.errors())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    get_metrics().increment("http_requests_failed_total")
    logger.exception(
        "Unhandled request error",
        extra={"method": request.method, "path": request.url.path},
    )
    return _error_response(500, "Internal Server Error")


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    started = time.perf_counter()
    metrics = get_metrics()
    response = await call_next(request)
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


# Registered last so it wraps the task-spawning ``observe_requests`` middleware:
# this binds the request id in the outermost task, where the exception handlers
# also run, so error responses and every in-request log carry the same id.
app.add_middleware(RequestContextMiddleware)


for _router in ROUTERS:
    app.include_router(_router)
