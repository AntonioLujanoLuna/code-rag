from __future__ import annotations

import httpx

from code_rag.adapters.answer import grounding
from code_rag.adapters.http.retries import request_with_retries
from code_rag.config.settings import Settings
from code_rag.domain.models import SearchResponse


class ExtractiveAnswerProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def answer(self, search_response: SearchResponse, max_context_chars: int) -> str:
        refusal = self.refusal_reason(search_response)
        if refusal:
            return refusal
        if self.settings.llm_answer_service_url:
            return self._remote_answer(search_response, max_context_chars)
        lines = ["Grounded answer draft from indexed code:"]
        for index, hit in enumerate(search_response.hits[:5], start=1):
            symbol = f" `{hit.symbol_name}`" if hit.symbol_name else ""
            lines.append(
                f"- Source [{index}] points to {hit.repo_path_with_namespace}/{hit.file_path}"
                f":{hit.line_start}-{hit.line_end}{symbol}."
            )
        lines.append("The cited source lines are required context for any generated explanation.")
        return "\n".join(lines)

    def is_grounded(self, search_response: SearchResponse) -> bool:
        return self.refusal_reason(search_response) is None

    def refusal_reason(self, search_response: SearchResponse) -> str | None:
        return grounding.refusal_reason(self.settings, search_response)

    def source_coverage(self, search_response: SearchResponse) -> float:
        return grounding.source_coverage(search_response)

    def _remote_answer(self, search_response: SearchResponse, max_context_chars: int) -> str:
        payload = {
            "query": search_response.query,
            "query_type": search_response.query_type,
            "identifiers": search_response.identifiers,
            "context": search_response.context[:max_context_chars],
            "sources": [
                {
                    "repo": hit.repo_path_with_namespace,
                    "file_path": hit.file_path,
                    "line_start": hit.line_start,
                    "line_end": hit.line_end,
                    "url": hit.gitlab_blob_url,
                }
                for hit in search_response.hits
            ],
            "requirements": {
                "must_cite_sources": True,
                "refuse_if_context_is_insufficient": True,
                "do_not_use_unretrieved_facts": True,
            },
        }
        with httpx.Client(timeout=self.settings.llm_answer_service_timeout_seconds) as client:
            response = request_with_retries(
                client,
                "POST",
                self.settings.llm_answer_service_url,
                json=payload,
                retries=self.settings.http_retries,
                backoff_seconds=self.settings.http_retry_backoff_seconds,
            )
            response.raise_for_status()
            data = response.json()
        return data.get("answer") or data.get("text") or ""
