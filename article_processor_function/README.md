# Article Processor Function

Unified article processing pipeline using vector embeddings for grouping and a single LLM call per group.

## Architecture

```
Raw Articles → Pre-filter → Embed → Group → LLM → Final Output
```

1. **Pre-filter**: Remove exact URL/title duplicates (code-based)
2. **Embed**: Generate vectors with `text-embedding-004`
3. **Group**: Cosine similarity ≥ 0.85 → Union-Find grouping
4. **LLM**: One call per group (merge decision + summary + tags + x_post + translation)

## Design Decisions

**Binary merge decision per group**: Groups are either fully merged or kept separate. No partial merging within a group.

This relies on the 0.85 similarity threshold producing homogeneous groups. If mixed groups occur, raise the threshold (e.g., 0.90).

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `SIMILARITY_THRESHOLD` | 0.85 | Min cosine similarity for grouping |
| `EMBEDDING_MODEL` | text-embedding-004 | Vertex AI embedding model |
| `VERTEX_AI_MODEL` | gemini-3-pro-preview | LLM for processing |
| `CROSS_RUN_DEDUP_THRESHOLD` | 0.7 | Default cross-run dedup threshold |
| `CROSS_RUN_DEDUP_THRESHOLD_TR` | 0.7 | Cross-run dedup threshold for TR region |
| `CROSS_RUN_DEDUP_THRESHOLD_EU` | 0.9 | Cross-run dedup threshold for EU region |
| `GROUPING_THRESHOLD` | 0.8 | Within-run article grouping threshold |

### Region-Specific Thresholds

Cross-run deduplication supports per-region thresholds to account for different content overlap patterns:

- **TR (Turkish)**: Uses 0.7 - Turkish sports news has higher content overlap across sources
- **EU (European)**: Uses 0.9 - European content is more unique, requires stricter dedup

Articles without a region field use the default threshold (0.7).

## Replaces

- `batch_builder_function` (stage 1)
- `result_merger_function` (stage 2)

Old functions kept for rollback.
