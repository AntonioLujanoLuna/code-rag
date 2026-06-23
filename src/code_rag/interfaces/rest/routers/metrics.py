from __future__ import annotations

from fastapi import APIRouter, Depends

from code_rag.apps.metrics.metrics_registry import MetricsRegistry
from code_rag.interfaces.rest.dependencies import get_metrics

router = APIRouter()


@router.get("/metrics")
def metrics(registry: MetricsRegistry = Depends(get_metrics)) -> dict[str, dict]:
    return registry.snapshot()
