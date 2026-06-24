"""Elasticsearch adapter facade.

The implementation is split across focused mixins so each responsibility lives in
its own module instead of one 900-line class:

- :class:`~code_rag.adapters.elasticsearch._base.EsClientBase` — connection,
  index lifecycle (create/reindex/alias swap), filters, and document mapping.
- :class:`~code_rag.adapters.elasticsearch._search.SearchMixin` — query-time
  BM25/vector/symbol/edge/neighbour/community search.
- :class:`~code_rag.adapters.elasticsearch._indexing.IndexingMixin` — write-path
  file replacement/deletion and graph/community maintenance.
- :class:`~code_rag.adapters.elasticsearch._jobs.JobStoreMixin` — the durable
  index-job queue.

``ElasticsearchCodeIndex`` composes them into the combined object the job queue,
indexing service, and retrieval service depend on. Each mixin is itself a
working adapter for its slice (e.g. ``JobStoreMixin`` satisfies ``JobStorePort``)
should a consumer want to depend on a narrower type.
"""

from __future__ import annotations

from code_rag.adapters.elasticsearch._indexing import IndexingMixin
from code_rag.adapters.elasticsearch._jobs import JobStoreMixin
from code_rag.adapters.elasticsearch._search import SearchMixin

__all__ = ["ElasticsearchCodeIndex", "SearchMixin", "IndexingMixin", "JobStoreMixin"]


class ElasticsearchCodeIndex(SearchMixin, IndexingMixin, JobStoreMixin):
    """Elasticsearch adapter implementing the search, job-store and repo-store ports."""
