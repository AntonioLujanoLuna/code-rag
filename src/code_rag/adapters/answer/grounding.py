from __future__ import annotations

from code_rag.config.settings import Settings
from code_rag.domain.models import SearchResponse


def source_coverage(search_response: SearchResponse) -> float:
    if not search_response.hits:
        return 0.0
    with_source = sum(1 for hit in search_response.hits if hit.gitlab_blob_url)
    return with_source / len(search_response.hits)


def refusal_reason(settings: Settings, search_response: SearchResponse) -> str | None:
    if not search_response.hits:
        return "I could not find relevant indexed code for this question."
    if len(search_response.hits) < settings.min_answer_sources:
        return (
            "I found too few independent source citations to answer this safely "
            f"({len(search_response.hits)} found, {settings.min_answer_sources} required)."
        )
    if max(hit.score for hit in search_response.hits) < settings.min_answer_score:
        return "The retrieved evidence is below the configured relevance threshold."
    if source_coverage(search_response) <= 0.0:
        return "The retrieved evidence did not include source links."
    return None
