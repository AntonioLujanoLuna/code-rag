from __future__ import annotations

from typing import Any

try:
    from elasticsearch import Elasticsearch
except ImportError:  # pragma: no cover - exercised only without the optional dep
    Elasticsearch = None  # type: ignore[assignment,misc]

from code_rag.config.settings import Settings
from code_rag.domain.models import PermissionRecord


class ElasticsearchPermissionStore:
    """Durable, multi-process permission store backed by Elasticsearch.

    Replaces the process-local in-memory store so permission grants survive
    restarts and stay consistent across API workers/replicas.
    """

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.settings = settings
        if client is not None:
            self.client = client
        else:
            if Elasticsearch is None:
                raise RuntimeError("The elasticsearch package is required for the permission store")
            kwargs: dict[str, Any] = {}
            if settings.elasticsearch_api_key:
                kwargs["api_key"] = settings.elasticsearch_api_key
            self.client = Elasticsearch(settings.elasticsearch_url, **kwargs)

    @property
    def index(self) -> str:
        return f"{self.settings.index_prefix}code_permissions_v1"

    def ensure_index(self) -> None:
        if not self.client.indices.exists(index=self.index):
            self.client.indices.create(
                index=self.index,
                mappings={
                    "dynamic": True,
                    "properties": {
                        "user_id": {"type": "keyword"},
                        "tenant_id": {"type": "keyword"},
                        "accessible_project_ids": {"type": "keyword"},
                        "last_synced_at": {"type": "date"},
                    },
                },
                settings={"number_of_shards": 1, "number_of_replicas": 0},
            )

    def upsert(self, record: PermissionRecord) -> None:
        self.ensure_index()
        self.client.index(
            index=self.index,
            id=self._doc_id(record.tenant_id, record.user_id),
            document=record.model_dump(mode="json"),
            refresh=True,
        )

    def get(self, tenant_id: str, user_id: str) -> PermissionRecord | None:
        doc_id = self._doc_id(tenant_id, user_id)
        if not self.client.exists(index=self.index, id=doc_id):
            return None
        response = self.client.get(index=self.index, id=doc_id)
        return PermissionRecord.model_validate(response["_source"])

    def _doc_id(self, tenant_id: str, user_id: str) -> str:
        return f"{tenant_id}|{user_id}"
