from __future__ import annotations

import logging

from code_rag.config.settings import Settings

logger = logging.getLogger(__name__)

_PROMPT = (
    "Write a short, realistic code snippet (10-30 lines) that would directly answer "
    "the following question. Output only the code, no explanation or markdown fences:\n\n"
    "{query}"
)


class HydeExpander:
    """Generate a hypothetical code document to improve dense-vector recall.

    When enabled, a single Claude call produces a plausible code snippet that
    matches what a retrieved answer might look like. Embedding the combined
    query + snippet shifts the query vector toward code rather than natural
    language, improving kNN recall for semantic queries.
    """

    def __init__(self, settings: Settings, client: object | None = None) -> None:
        self.settings = settings
        self._client = client

    def expand(self, query: str) -> str | None:
        if not self.settings.hyde_enabled:
            return None
        try:
            client = self._ensure_client()
            model = self.settings.hyde_model or self.settings.anthropic_model
            message = client.messages.create(  # type: ignore[attr-defined]
                model=model,
                max_tokens=512,
                messages=[{"role": "user", "content": _PROMPT.format(query=query)}],
            )
            snippet = "".join(
                block.text for block in message.content if getattr(block, "type", None) == "text"
            ).strip()
            return snippet or None
        except Exception:
            logger.debug("HyDE expansion failed", exc_info=True)
            return None

    def _ensure_client(self) -> object:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key or None)
        return self._client
