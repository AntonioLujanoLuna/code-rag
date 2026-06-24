from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from code_rag.apps.metrics.metrics_registry import MetricsRegistry
from code_rag.interfaces.rest.dependencies import get_metrics

router = APIRouter()


@router.get("/metrics")
def metrics(request: Request, registry: MetricsRegistry = Depends(get_metrics)):
    if "application/json" in request.headers.get("accept", ""):
        return registry.snapshot()
    return Response(
        content=registry.prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
