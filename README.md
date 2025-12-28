# AISports Functions - Article Processing Pipeline

## Architecture Overview

This repository contains Cloud Functions for the AISports news article processing pipeline. Articles are ingested, deduplicated using vector embeddings, grouped for merge decisions, and enriched with AI-generated summaries.

---

## Pipeline Flows

### Flow 1: API Fetch Event (news_api_fetcher_function)

Triggered when fetching articles from news APIs. Produces both complete and incomplete articles.

```
                            news_api_fetcher_function
                                      │
                    ┌─────────────────┴─────────────────┐
                    ▼                                   ▼
         complete_articles.json                   to_scrape.json
                    │                                   │
                    │                          PubSub trigger
                    │                                   ▼
                    │                         scraper_function
                    │                                   │
                    │                                   ▼
                    │                   scraped_incomplete_articles.json
                    │                                   │
                    ▼                                   ▼
            ┌───────────────────────────────────────────┐
            │         article_processor_function        │
            │    (embed + cross-run dedup + group)      │
            └───────────────────────────────────────────┘
                    │                                   │
        ┌───────────┴───────────┐           ┌──────────┴──────────┐
        ▼                       ▼           ▼                      ▼
singleton_complete_     grouped_complete_   singleton_scraped_    grouped_scraped_
articles.json           articles.json       incomplete_articles   incomplete_articles
        │                       │                   │                      │
        │                       ▼                   │                      ▼
        │              merge_decider_function       │             merge_decider_function
        │                       │                   │                      │
        │                       ▼                   │                      ▼
        │              decision_complete_           │             decision_scraped_
        │              articles.json                │             incomplete_articles.json
        │                       │                   │                      │
        ▼                       ▼                   ▼                      ▼
        └───────────────────────┴───────────────────┴──────────────────────┘
                                        │
                                        ▼
                           article_enricher_function
                                        │
                                        ▼
                            enriched_*.json (consumed by UI)
```

### Flow 2: Scrape Event Only (scraper_function)

Triggered when directly scraping URLs without API fetch. Simpler single-source flow.

```
                              scraper_function
                                     │
                                     ▼
                          scraped_articles.json
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │    article_processor_function  │
                    │  (embed + cross-run dedup +    │
                    │           group)               │
                    └────────────────────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
        singleton_scraped_                grouped_scraped_
        articles.json                     articles.json
                    │                                 │
                    │                                 ▼
                    │                    merge_decider_function
                    │                                 │
                    │                                 ▼
                    │                    decision_scraped_
                    │                    articles.json
                    │                                 │
                    ▼                                 ▼
                    └─────────────────┬───────────────┘
                                      │
                                      ▼
                         article_enricher_function
                                      │
                                      ▼
                          enriched_*.json (consumed by UI)
```

---

## Functions

| Function | Purpose | Trigger |
|----------|---------|---------|
| `news_api_fetcher_function` | Fetch articles from news APIs | Cloud Scheduler |
| `scraper_function` | Scrape full article content from URLs | PubSub / Manual |
| `article_processor_function` | Embed + cross-run dedup + group | GCS (Eventarc) |
| `merge_decider_function` | LLM decides MERGE vs KEEP_ALL | GCS (Eventarc) |
| `article_enricher_function` | LLM generates summary, X post, translation | GCS (Eventarc) |
| `region_diff_function` | Find EU articles not covered in TR | GCS (Eventarc) |

---

## GCS Structure

### API-Triggered Run (news_api_fetcher → scraper)

```
gs://aisports-scraping/
└── ingestion/{YYYY-MM-DD}/
    └── {HH-MM-SS}/
        ├── complete_articles.json                    # API articles with full body
        ├── to_scrape.json                            # API articles missing body (won't trigger processor)
        ├── scraped_incomplete_articles.json          # Scraped versions of incomplete
        ├── embeddings/
        │   ├── complete_embeddings.json              # For cross-run dedup comparison
        │   └── scraped_incomplete_embeddings.json
        ├── singleton_complete_articles.json
        ├── grouped_complete_articles.json
        ├── singleton_scraped_incomplete_articles.json
        ├── grouped_scraped_incomplete_articles.json
        ├── decision_complete_articles.json
        ├── decision_scraped_incomplete_articles.json
        ├── dedup_log_complete.json                   # Dropped duplicates with match info
        ├── dedup_log_scraped_incomplete.json
        ├── processing_metadata_complete.json         # Processing stats
        ├── processing_metadata_scraped_incomplete.json
        ├── enriched_*.json                           ← UI consumes these
        └── analysis/
            └── region_diff_eu_vs_tr.json             # EU articles not covered in TR
```

### Pure Scrape Run (scraper only)

```
gs://aisports-scraping/
└── ingestion/{YYYY-MM-DD}/
    └── {HH-MM-SS}/
        ├── scraped_articles.json                     # Direct scraper output
        ├── embeddings/
        │   └── scraped_embeddings.json               # For cross-run dedup comparison
        ├── singleton_scraped_articles.json
        ├── grouped_scraped_articles.json
        ├── decision_scraped_articles.json
        ├── dedup_log_scraped.json                    # Dropped duplicates with match info
        ├── processing_metadata_scraped.json          # Processing stats
        ├── enriched_*.json                           ← UI consumes these
        └── analysis/
            └── region_diff_eu_vs_tr.json             # EU articles not covered in TR
```

---

## Key Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| Cross-run dedup threshold (TR) | 0.85 | Drop Turkish articles similar to previous run |
| Cross-run dedup threshold (EU) | 0.9 | Drop European articles similar to previous run |
| Cross-run dedup depth | 3 days | Number of days to look back for deduplication |
| Within-run grouping threshold | 0.8 | Group similar articles for merge decision |
| Region diff threshold | 0.75 | Similarity threshold for EU vs TR coverage |
| Embedding model | text-embedding-004 | 768-dim vectors |
| Embedding input | title + 500 chars body | Per article |

---

## Deduplication Logic

### Phase 1: Pre-filter (Code-based)
- Exact URL match → drop
- Exact title match → drop
- No embedding comparison needed

### Phase 2: Cross-run Deduplication (Embedding-based)
- **Scope**: **Last N days** - configurable via `CROSS_RUN_DEDUP_DEPTH` env var (default: 3 days)
- **Method**: Cosine similarity against previous run embeddings
- **Thresholds**:
  - TR region: 0.85 (lower to catch more transfer news)
  - EU region: 0.9 (higher, European content more unique)
- **Output**: `dedup_log_{source_type}.json` with matched URLs

### Phase 3: Region Diff Analysis (Post-enrichment)
- **Scope**: **Last 3 days** - compares EU articles against TR from `HISTORICAL_DIFF_DEPTH` days
- **Method**: Find EU articles with no similar coverage in TR
- **Threshold**: 0.75
- **Output**: `analysis/region_diff_eu_vs_tr.json`

---

## Output Files Reference

| File | Created By | Contains |
|------|-----------|----------|
| `dedup_log_*.json` | article_processor | Dropped duplicates with matched article URLs |
| `processing_metadata_*.json` | article_processor | Processing stats and thresholds used |
| `singleton_*.json` | article_processor | Non-grouped articles (direct to enricher) |
| `grouped_*.json` | article_processor | Similarity groups for merge decision |
| `decision_*.json` | merge_decider | Merge decisions per group |
| `enriched_*.json` | article_enricher | Final enriched articles for UI |
| `analysis/region_diff_*.json` | region_diff | EU articles not covered in TR |

### Dedup Log Schema

```json
{
  "dropped_articles": [
    {
      "article_id": "abc123",
      "title": "Transfer News...",
      "url": "https://example.com/article",
      "matched_article_url": "https://other.com/similar-article",
      "region": "tr",
      "max_similarity": 0.91,
      "threshold": 0.85,
      "reason": "cross_run_duplicate"
    }
  ],
  "count": 5,
  "region_thresholds": {"tr": 0.85, "eu": 0.9}
}
```

---

## Documentation

- **Full Plan**: See [pipeline_refactoring_plan.md](../pipeline_refactoring_plan.md)
- **Vector Strategy ADR**: See [future_considerations/vector_management.md](future_considerations/vector_management.md)

## Known Limitations

- **Concurrency:** The `PUT /user/preferences` endpoint uses a read-modify-write pattern without locking. Concurrent updates from multiple clients may result in lost data.
- **Cross-run dedup**: Configurable lookback depth (default 3 days). Controlled by `CROSS_RUN_DEDUP_DEPTH` env var.
- **Region diff**: Only compares last 3 days of TR history. Older EU coverage gaps won't be detected.
