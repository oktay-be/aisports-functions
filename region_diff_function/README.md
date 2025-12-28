# Region Diff Function

Cloud Function that analyzes regional news coverage differences. Finds articles that appear in one region (EU) but are not covered in another region (TR).

## Overview

This function is triggered when `enriched_*.json` files are uploaded to the GCS bucket. It compares EU articles from the current run against TR articles from the last N days to find stories unique to EU coverage.

## Use Case

EU sports news outlets often cover stories that Turkish outlets don't pick up. This function identifies:
- Transfer rumors only reported in EU sources
- International football news not covered in TR
- EU-specific team news

## Trigger Files

| Trigger File Pattern | Description |
|---------------------|-------------|
| `enriched_complete_articles.json` | Enriched complete articles |
| `enriched_scraped_incomplete_articles.json` | Enriched scraped articles |
| `enriched_scraped_articles.json` | Enriched direct scrape articles |

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `REGION_DIFF_THRESHOLD` | 0.75 | Similarity threshold for "same story" |
| `REGION1` | eu | Source region to find unique articles from |
| `REGION2` | tr | Comparison region |
| `HISTORICAL_DIFF_DEPTH` | 3 | Days of TR history to compare against |

### Historical Depth

Unlike cross-run deduplication (same day only), region diff analysis looks back **3 days** by default:

```
Current EU articles (run: 2025-12-22/08-30-00)
    compared against TR articles from:
    - 2025-12-22/* (today)
    - 2025-12-21/* (yesterday)
    - 2025-12-20/* (2 days ago)
```

This accounts for stories that may take time to be picked up across regions.

## GCS Path Structure

```
aisports-scraping/
└── ingestion/{date}/{run_id}/
    ├── enriched_*.json              # Input trigger
    └── analysis/
        └── region_diff_eu_vs_tr.json  # Output
```

## Output Schema

```json
{
  "metadata": {
    "region1": "eu",
    "region2": "tr",
    "run_folder": "ingestion/2025-12-22/08-30-00",
    "diff_threshold": 0.75,
    "generated_at": "2025-12-22T08:35:00.000000+00:00"
  },
  "summary": {
    "total_region1_articles": 25,
    "total_region2_articles": 150,
    "unique_to_region1": 8
  },
  "unique_articles": [
    {
      "article_id": "abc123",
      "title": "Manchester United in talks for...",
      "original_url": "https://eu-source.com/article",
      "source": "eu-source.com",
      "publish_date": "2025-12-22",
      "max_similarity": 0.42,
      "original_region": "eu",
      "summary": "AI-generated summary...",
      "categories": [{"tag": "transfers-rumors", "confidence": 0.9}],
      "key_entities": {
        "teams": ["Manchester United"],
        "players": ["Player Name"],
        "amounts": ["€50M"]
      },
      "closest_match": {
        "article_id": "xyz789",
        "title": "Closest TR article title",
        "url": "https://tr-source.com/article"
      },
      "closest_match_url": "https://tr-source.com/article"
    }
  ]
}
```

### Output Fields

| Field | Description |
|-------|-------------|
| `max_similarity` | Highest similarity to any TR article (< threshold = unique) |
| `closest_match` | The most similar TR article found (for context) |
| `original_region` | Always "eu" for articles in unique_articles |

## Algorithm

1. **Load EU articles** from current run's enriched files
2. **Load TR articles** from last N days (all runs)
3. **Build embedding matrices** from both sets
4. **Compute similarity matrix** (EU x TR cosine similarities)
5. **Find unique EU articles** where max_similarity < threshold

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLOUD_PROJECT` | Google Cloud project ID |
| `GCS_BUCKET_NAME` | GCS bucket name (default: `aisports-scraping`) |
| `REGION_DIFF_THRESHOLD` | Similarity threshold (default: `0.75`) |
| `HISTORICAL_DIFF_DEPTH` | Days of history (default: `3`) |

## Dependencies

- `google-cloud-storage`
- `numpy`
- `functions-framework`

## Related Functions

- **article_enricher_function**: Upstream - creates `enriched_*.json` files that trigger this function
- **article_processor_function**: Creates embeddings used for similarity comparison

## Workflow Position

```
article_processor → merge_decider → article_enricher → region_diff
                                                           │
                                                           ▼
                                            analysis/region_diff_eu_vs_tr.json
                                                           │
                                                           ▼
                                                      UI displays
                                                   "EU-only" stories
```
