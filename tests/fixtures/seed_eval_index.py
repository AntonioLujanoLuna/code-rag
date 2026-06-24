from __future__ import annotations

from datetime import UTC, datetime

from code_rag.adapters.elasticsearch.index import ElasticsearchCodeIndex
from code_rag.adapters.embeddings.hash_embedding_provider import HashEmbeddingProvider
from code_rag.config.settings import Settings
from code_rag.domain import (
    ChunkKind,
    CodeChunk,
    CodeSymbol,
    FileClass,
    FileMetadata,
    SymbolRole,
)


def main() -> None:
    settings = Settings()
    index = ElasticsearchCodeIndex(settings)
    index.ensure_indices()
    metadata, chunk, symbol = eval_documents(settings)
    index.replace_file(metadata, [chunk], [symbol], [])
    index.client.indices.refresh(index=index.chunks_index)
    index.client.indices.refresh(index=index.symbols_index)


def eval_documents(settings: Settings) -> tuple[FileMetadata, CodeChunk, CodeSymbol]:
    now = datetime.now(UTC)
    embedding = HashEmbeddingProvider(
        settings.embedding_dimension, settings.late_interaction_dimension
    )
    result = embedding.embed_query("PaymentService authorizes and captures payments")
    metadata = FileMetadata(
        tenant_id=settings.tenant_id,
        gitlab_instance_url=settings.gitlab_base_url,
        gitlab_project_id="123",
        repo_path_with_namespace="group/payments",
        repo_name="payments",
        repo_url="https://gitlab.example.com/group/payments.git",
        branch=settings.branch,
        commit_sha="abc123",
        file_path="src/payments/service.py",
        file_name="service.py",
        file_extension=".py",
        language="python",
        file_hash="hash",
        size_bytes=120,
        line_count=8,
        file_class=FileClass.SOURCE,
    )
    chunk = CodeChunk(
        chunk_id="eval-payment-service",
        tenant_id=settings.tenant_id,
        gitlab_instance_url=settings.gitlab_base_url,
        gitlab_project_id="123",
        repo_path_with_namespace="group/payments",
        repo_name="payments",
        repo_url="https://gitlab.example.com/group/payments.git",
        branch=settings.branch,
        commit_sha="abc123",
        file_path="src/payments/service.py",
        file_name="service.py",
        file_extension=".py",
        language="python",
        file_hash="hash",
        chunk_kind=ChunkKind.CLASS_DEFINITION,
        symbol_role=SymbolRole.DEFINITION,
        symbol_name="PaymentService",
        symbol_fqn="group.payments.PaymentService",
        symbol_kind="class",
        line_start=1,
        line_end=8,
        gitlab_blob_url="https://gitlab.example.com/group/payments/-/blob/abc123/src/payments/service.py#L1-L8",
        gitlab_raw_url="https://gitlab.example.com/group/payments/-/raw/abc123/src/payments/service.py",
        text=(
            "class PaymentService:\n"
            "    def authorize(self, payment):\n"
            "        return payment.is_valid()"
        ),
        text_for_embedding="PaymentService authorizes and captures payments",
        defines_symbols=["group.payments.PaymentService"],
        embedding_dense=result.dense,
        embedding_late_interaction=result.late_interaction,
        embedding_model=embedding.model_name,
        embedding_dimension=embedding.dimension,
        embedding_created_at=now,
        embedding_input_hash="hash",
    )
    symbol = CodeSymbol(
        symbol_id="eval-payment-service-symbol",
        tenant_id=settings.tenant_id,
        gitlab_project_id="123",
        repo_path_with_namespace="group/payments",
        branch=settings.branch,
        commit_sha="abc123",
        language="python",
        symbol_name="PaymentService",
        symbol_fqn="group.payments.PaymentService",
        symbol_kind="class",
        definition_file_path="src/payments/service.py",
        definition_line_start=1,
        definition_line_end=8,
        definition_chunk_id=chunk.chunk_id,
        definition_gitlab_url=chunk.gitlab_blob_url,
    )
    return metadata, chunk, symbol


if __name__ == "__main__":
    main()
