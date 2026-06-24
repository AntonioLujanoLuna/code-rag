from __future__ import annotations

import logging

import httpx

from code_rag.adapters.http.retries import request_with_retries
from code_rag.config.settings import Settings

logger = logging.getLogger(__name__)


class HttpCrossEncoderReranker:
    """Adapter for a remote cross-encoder rerank service.

    Posts ``{"query": ..., "documents": [...]}`` and reads back a parallel list
    of relevance scores (either a top-level list or a ``scores``/``results``
    field). When no service URL is configured, or the call fails, it returns an
    empty list so the caller keeps its existing ordering.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.rerank_service_url)

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not self.enabled or not documents:
            return []
        payload = {"query": query, "documents": documents}
        try:
            with httpx.Client(timeout=self.settings.rerank_service_timeout_seconds) as client:
                response = request_with_retries(
                    client,
                    "POST",
                    self.settings.rerank_service_url,
                    json=payload,
                    retries=self.settings.http_retries,
                    backoff_seconds=self.settings.http_retry_backoff_seconds,
                )
                response.raise_for_status()
                data = response.json()
        except Exception:  # pragma: no cover - network failure path
            logger.warning("Cross-encoder rerank request failed; falling back", exc_info=True)
            return []
        scores = self._scores(data)
        if len(scores) != len(documents):
            logger.warning(
                "Cross-encoder returned %d scores for %d documents; ignoring",
                len(scores),
                len(documents),
            )
            return []
        return scores

    def _scores(self, data: object) -> list[float]:
        if isinstance(data, dict):
            data = data.get("scores") or data.get("results") or data.get("data") or []
        if not isinstance(data, list):
            return []
        scores: list[float] = []
        for item in data:
            if isinstance(item, dict):
                value = item.get("score") or item.get("relevance") or 0.0
            else:
                value = item
            try:
                scores.append(float(value))
            except (TypeError, ValueError):
                return []
        return scores
