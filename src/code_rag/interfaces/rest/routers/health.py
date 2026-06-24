from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response, status

from code_rag.adapters.elasticsearch.index import ElasticsearchCodeIndex
from code_rag.interfaces.rest.dependencies import get_index

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe: the process is up and serving. Always cheap, no I/O."""
    return {"status": "ok"}


@router.get("/ready")
def ready(
    response: Response,
    index: ElasticsearchCodeIndex = Depends(get_index),
) -> dict[str, str]:
    """Readiness probe: verify the service can reach Elasticsearch.

    Returns 503 when the dependency is unavailable so that load balancers and
    orchestrators stop routing traffic to the instance.
    """
    try:
        reachable = index.ping()
    except Exception:  # pragma: no cover - defensive, network errors vary
        logger.warning("Readiness check failed to reach Elasticsearch", exc_info=True)
        reachable = False
    if not reachable:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "elasticsearch": "unreachable"}
    return {"status": "ready", "elasticsearch": "ok"}
