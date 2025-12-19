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
         complete_articles.json              incomplete_articles.json
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
| `merge_decider_function` | LLM decides MERGE vs KEEP_BOTH | GCS (Eventarc) |
| `article_enricher_function` | LLM generates summary, X post, translation | GCS (Eventarc) |

---

## GCS Structure

### API-Triggered Run (news_api_fetcher → scraper)

```
gs://aisports-scraping/
└── {YYYY-MM-DD}/
    └── {HH-MM-SS}/
        ├── complete_articles.json                    # API articles with full body
        ├── incomplete_articles.json                  # API articles missing body
        ├── scraped_incomplete_articles.json          # Scraped versions of incomplete
        ├── embeddings/
        │   ├── complete_embeddings.json
        │   └── scraped_incomplete_embeddings.json
        ├── singleton_complete_articles.json
        ├── grouped_complete_articles.json
        ├── singleton_scraped_incomplete_articles.json
        ├── grouped_scraped_incomplete_articles.json
        ├── decision_complete_articles.json
        ├── decision_scraped_incomplete_articles.json
        └── enriched_*.json                           ← UI consumes these
```

### Pure Scrape Run (scraper only)

```
gs://aisports-scraping/
└── {YYYY-MM-DD}/
    └── {HH-MM-SS}/
        ├── scraped_articles.json                     # Direct scraper output
        ├── embeddings/
        │   └── scraped_embeddings.json
        ├── singleton_scraped_articles.json
        ├── grouped_scraped_articles.json
        ├── decision_scraped_articles.json
        └── enriched_*.json                           ← UI consumes these
```

---

## Key Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| Cross-run dedup threshold | 0.7 | Drop if similar to previous run |
| Within-run grouping threshold | 0.8 | Group for merge decision |
| Embedding model | text-embedding-004 | 768-dim vectors |
| Embedding input | title + 500 chars body | Per article |

---

## Documentation

- **Full Plan**: See [pipeline_refactoring_plan.md](../pipeline_refactoring_plan.md)
- **Vector Strategy ADR**: See [future_considerations/vector_management.md](future_considerations/vector_management.md)
