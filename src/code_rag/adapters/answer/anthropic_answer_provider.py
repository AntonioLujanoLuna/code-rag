from __future__ import annotations

from code_rag.adapters.answer import grounding
from code_rag.config.settings import Settings
from code_rag.domain.models import SearchResponse

_SYSTEM_PROMPT = (
    "You answer questions about a codebase using only the retrieved source context provided. "
    "Ground every claim in the numbered sources and cite them inline as [n]. "
    "If the context is insufficient to answer, say so explicitly instead of guessing. "
    "Never use facts that are not present in the provided context."
)


class AnthropicAnswerProvider:
    """Grounded answer generation via the Claude Messages API.

    Applies the same refusal/citation gates as the extractive provider, then —
    when evidence is sufficient — asks Claude to synthesize an answer strictly
    from the retrieved context. The ``anthropic`` package is imported lazily so
    it stays an optional dependency.
    """

    def __init__(self, settings: Settings, client: object | None = None) -> None:
        self.settings = settings
        self._client = client

    def _ensure_client(self) -> object:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key or None)
        return self._client

    def answer(self, search_response: SearchResponse, max_context_chars: int) -> str:
        refusal = self.refusal_reason(search_response)
        if refusal:
            return refusal
        client = self._ensure_client()
        context = search_response.context[:max_context_chars]
        user_content = (
            f"Question:\n{search_response.query}\n\n"
            f"Retrieved source context:\n{context}\n\n"
            "Answer the question using only this context and cite sources as [n]."
        )
        message = client.messages.create(  # type: ignore[attr-defined]
            model=self.settings.anthropic_model,
            max_tokens=self.settings.anthropic_max_tokens,
            system=_SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": user_content}],
        )
        return "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )

    def is_grounded(self, search_response: SearchResponse) -> bool:
        return self.refusal_reason(search_response) is None

    def refusal_reason(self, search_response: SearchResponse) -> str | None:
        return grounding.refusal_reason(self.settings, search_response)

    def source_coverage(self, search_response: SearchResponse) -> float:
        return grounding.source_coverage(search_response)
