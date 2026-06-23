from __future__ import annotations

from code_rag.interfaces.rest.routers import (
    answer,
    health,
    indexing,
    indices,
    jobs,
    metrics,
    permissions,
    search,
    webhooks,
)

ROUTERS = [
    health.router,
    metrics.router,
    indices.router,
    indexing.router,
    webhooks.router,
    jobs.router,
    permissions.router,
    search.router,
    answer.router,
]

__all__ = ["ROUTERS"]
