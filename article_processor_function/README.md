# Article Processor Function

Unified article processing pipeline using vector embeddings for cross-run deduplication and within-run grouping.

## Architecture

```
Raw Articles → Pre-filter → Embed → Cross-run Dedup → Group → Output Files
```

1. **Pre-filter**: Remove exact URL/title duplicates (code-based)
2. **Embed**: Generate vectors with `text-embedding-004`
3. **Cross-run Dedup**: Compare against **last N days** of embeddings, drop duplicates
4. **Group**: Cosine similarity ≥ 0.8 → Union-Find grouping
5. **Output**: Separate singletons and groups for downstream processing

## Trigger Files

| Trigger File Pattern | Source | Description |
|---------------------|--------|-------------|
| `complete_articles.json` | news_api_fetcher | API articles with full body |
| `scraped_incomplete_articles.json` | scraper | Scraped versions of incomplete API articles |
| `scraped_articles.json` | scraper | Direct scraper output |

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `CROSS_RUN_DEDUP_THRESHOLD_TR` | 0.85 | Cross-run dedup threshold for TR region |
| `CROSS_RUN_DEDUP_THRESHOLD_EU` | 0.9 | Cross-run dedup threshold for EU region |
| `CROSS_RUN_DEDUP_DEPTH` | 3 | Number of days to look back for cross-run dedup |
| `GROUPING_THRESHOLD` | 0.8 | Within-run article grouping threshold |
| `EMBEDDING_MODEL` | text-embedding-004 | Vertex AI embedding model |

### Region-Specific Thresholds

Cross-run deduplication uses per-region thresholds to account for different content overlap patterns:

- **TR (Turkish)**: Uses 0.85 - Lower threshold catches more transfer news duplicates
- **EU (European)**: Uses 0.9 - European content is more unique, requires stricter dedup

Articles without a region field use the EU threshold (0.9) as fallback.

### Cross-run Dedup Scope

**LAST N DAYS**: Cross-run deduplication compares against embeddings from the last N days (configurable via `CROSS_RUN_DEDUP_DEPTH`):

```
# With CROSS_RUN_DEDUP_DEPTH=3 (default)
# Current run: 2025-12-24/08-00-00

ingestion/2025-12-22/*/embeddings/*.json  ← compared against (2 days ago)
ingestion/2025-12-23/*/embeddings/*.json  ← compared against (yesterday)
ingestion/2025-12-24/*/embeddings/*.json  ← compared against (today, except current run)
```

This ensures articles aren't republished across consecutive days.

## Output Files

| File | Contents |
|------|----------|
| `singleton_{source_type}_articles.json` | Articles not grouped with others |
| `grouped_{source_type}_articles.json` | Similar articles grouped for merge decision |
| `embeddings/{source_type}_embeddings.json` | Stored for cross-run dedup |
| `dedup_log_{source_type}.json` | Dropped duplicates with match info |
| `processing_metadata_{source_type}.json` | Processing statistics |

### Dedup Log Schema

```json
{
  "dropped_articles": [
    {
      "article_id": "abc123",
      "title": "Transfer news about...",
      "url": "https://example.com/article",
      "matched_article_url": "https://other.com/similar",
      "region": "tr",
      "max_similarity": 0.91,
      "threshold": 0.85,
      "reason": "cross_run_duplicate"
    }
  ],
  "count": 5,
  "region_thresholds": {"tr": 0.85, "eu": 0.9},
  "created_at": "2025-12-22T08:30:00.000000+00:00"
}
```

### Processing Metadata Schema

```json
{
  "status": "success",
  "source_type": "complete",
  "date": "2025-12-22",
  "run_id": "08-30-00",
  "total_input_articles": 50,
  "prefilter_removed": 3,
  "cross_run_removed": 12,
  "articles_after_dedup": 35,
  "singleton_count": 20,
  "group_count": 5,
  "grouped_article_count": 15,
  "thresholds": {
    "cross_run_dedup_tr": 0.85,
    "cross_run_dedup_eu": 0.9,
    "grouping": 0.8
  }
}
```

## GCS Path Structure

```
aisports-scraping/
└── ingestion/{date}/{run_id}/
    ├── complete_articles.json           # Input trigger
    ├── embeddings/
    │   └── complete_embeddings.json     # For future cross-run dedup
    ├── singleton_complete_articles.json # Output: ungrouped articles
    ├── grouped_complete_articles.json   # Output: similarity groups
    ├── dedup_log_complete.json          # Dropped duplicates
    └── processing_metadata_complete.json # Stats
```

## What Gets Dropped

### Pre-filter (instant, no embeddings)
- Exact URL match with article in same batch
- Exact title match with article in same batch

### Cross-run Dedup (embedding comparison)
- TR article with similarity ≥ 0.85 to previous run article
- EU article with similarity ≥ 0.9 to previous run article
- Compares against last N days (default: 3 days, configurable via `CROSS_RUN_DEDUP_DEPTH`)

## Related Functions

- **news_api_fetcher_function**: Upstream - creates `complete_articles.json`
- **scraper_function**: Upstream - creates `scraped_*.json` files
- **merge_decider_function**: Downstream - processes `grouped_*.json` files
- **article_enricher_function**: Downstream - processes `singleton_*.json` and `decision_*.json`

## Historical Note

This function replaces the original two-stage pipeline:
- `batch_builder_function` (stage 1)
- `result_merger_function` (stage 2)

The LLM merge decision logic was moved to `merge_decider_function`.
