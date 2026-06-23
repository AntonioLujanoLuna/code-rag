from __future__ import annotations

from code_rag.apps.indexing.indexing_service import IndexingService
from code_rag.config.settings import Settings
from code_rag.domain import ChunkKind, CodeChunk, EmbeddingResult
from code_rag.domain.ids import stable_id


class CountingEmbeddings:
    model_name = "counting"
    dimension = 4
    late_interaction_dimension = 2

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> list[EmbeddingResult]:
        self.calls.append(list(texts))
        return [
            EmbeddingResult(dense=[1.0, 0.0, 0.0, 0.0], late_interaction=[[1.0, 0.0]])
            for _ in texts
        ]

    def embed_query(self, text: str) -> EmbeddingResult:  # pragma: no cover - unused here
        return EmbeddingResult(dense=[0.0], late_interaction=[])


class CachingIndex:
    def __init__(self, stored: dict[str, dict]) -> None:
        self.stored = stored

    def existing_embeddings(self, chunk_ids: list[str]) -> dict[str, dict]:
        return {cid: self.stored[cid] for cid in chunk_ids if cid in self.stored}


def _chunk(chunk_id: str, text: str) -> CodeChunk:
    return CodeChunk(
        chunk_id=chunk_id,
        tenant_id="default",
        gitlab_instance_url="https://gitlab.example.com",
        gitlab_project_id="123",
        repo_path_with_namespace="group/payments",
        repo_name="payments",
        repo_url="https://gitlab.example.com/group/payments.git",
        branch="develop",
        commit_sha="abc",
        file_path="service.py",
        file_name="service.py",
        file_extension=".py",
        language="python",
        file_hash="hash",
        chunk_kind=ChunkKind.FUNCTION_DEFINITION,
        line_start=1,
        line_end=2,
        gitlab_blob_url="https://gitlab.example.com/x",
        gitlab_raw_url="https://gitlab.example.com/raw",
        text=text,
        text_for_embedding=text,
    )


def test_attach_embeddings_reuses_unchanged_chunks() -> None:
    reused = _chunk("reused", "unchanged text")
    fresh = _chunk("fresh", "new text")
    stored = {
        "reused": {
            "embedding_input_hash": stable_id("unchanged text"),
            "embedding_dense": [9.0, 9.0, 9.0, 9.0],
            "embedding_late_interaction": [[9.0, 9.0]],
        }
    }
    embeddings = CountingEmbeddings()
    service = object.__new__(IndexingService)
    service.settings = Settings(reuse_existing_embeddings=True)
    service.index = CachingIndex(stored)
    service.embeddings = embeddings

    service._attach_embeddings([reused, fresh])

    # Only the changed chunk was sent to the embedding backend.
    assert embeddings.calls == [["new text"]]
    assert reused.embedding_dense == [9.0, 9.0, 9.0, 9.0]
    assert fresh.embedding_dense == [1.0, 0.0, 0.0, 0.0]
    assert reused.embedding_input_hash == stable_id("unchanged text")
