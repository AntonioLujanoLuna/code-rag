# Index schema migrations

All Elasticsearch indices are addressed through **aliases** (`code_chunks`,
`code_symbols`, …) that point at **versioned backing indices**
(`code_chunks_v1`, `code_chunks_v2`, …). The version comes from
`CODE_RAG_INDEX_VERSION` (default `1`). Reads and writes always go through the
alias, so a backing index can be rebuilt and swapped underneath live traffic.

## When you need a migration

Elasticsearch mappings are mostly immutable: you can add new fields, but you
cannot change the type, analyzer, or `dims` of an existing field in place. A
migration is therefore required when you:

- change a field's type, analyzer, or normalizer,
- change the embedding vector `dims` (`CODE_RAG_EMBEDDING_DIMENSION`), or
- otherwise alter an existing field in `adapters/elasticsearch/mappings.py`.

Purely additive changes (a brand-new field) do not need a version bump; the new
mapping is applied to the existing backing index on the next `init-indices`.

## Rolling a migration

1. **Edit the mapping** in `src/code_rag/adapters/elasticsearch/mappings.py`.
2. **Bump the version**: set `CODE_RAG_INDEX_VERSION` to the next integer
   (e.g. `2`). This changes the backing-index names without touching the
   aliases that the application reads/writes.
3. **Reindex and swap** with the CLI:

   ```bash
   code-rag reindex                 # migrate every managed index
   code-rag reindex --only code_chunks   # or just one alias
   ```

   For each alias this creates the new `*_vN` backing index from the current
   mapping, copies documents from the alias's existing backing into it (via the
   Elasticsearch reindex API), and atomically moves the alias to the new
   backing. The command is idempotent: an alias already pointing at the current
   version is skipped, and it prints the per-alias document count it copied.

4. **Verify** retrieval quality against the golden dataset before and after:

   ```bash
   code-rag evaluate eval/dataset.example.json --k 10
   ```

5. **Drop the old backing indices** once you are satisfied the swap is healthy
   and you no longer need to roll back:

   ```bash
   curl -XDELETE "$CODE_RAG_ELASTICSEARCH_URL/code_chunks_v1"
   ```

## Rollback

Because the swap is atomic and the previous backing index is left in place, a
rollback is just another alias swap back to the old backing (lower the version
and `reindex`, or move the alias manually). Keep the old `*_vN` indices until
the new version is proven in production.

## Notes

- Embeddings are reused across reindexes by content hash, but a `dims` change
  invalidates them — plan to re-embed (full re-index) rather than a pure copy
  when the vector dimensionality changes.
- Run migrations from a single operator process. The reindex itself is safe
  under concurrent reads, but you should not run two competing `reindex`
  invocations against the same alias.
