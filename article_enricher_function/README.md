# Article Enricher Function

Cloud Function that enriches articles with AI-generated summaries, X (Twitter) posts, translations, categories, and key entity extraction using Vertex AI batch processing.

## Overview

This function is triggered when `singleton_*.json` or `decision_*.json` files are uploaded to the GCS bucket. It processes articles through Vertex AI's batch prediction API to generate enriched content.

## Trigger Files

| Trigger File Pattern | Branch Type | Description |
|---------------------|-------------|-------------|
| `singleton_*.json` | `singleton` | Individual articles that weren't grouped for merging |
| `decision_*.json` | `merged` | Articles that went through merge decision process |

## GCS Path Structure

```
aisports-scraping/
└── ingestion/{date}/{run_id}/
    └── batch_enrichment/{source_type}/{branch_type}/
        ├── input/
        │   └── batch_{i}.json          # Individual article content files
        ├── request.jsonl               # Batch request with fileData references
        ├── metadata.json               # Job metadata
        └── results/                    # Batch prediction outputs
```

### Path Parameters

- **source_type**: `complete`, `scraped_incomplete`, `news_api_incomplete`
- **branch_type**: `singleton` or `merged` (prevents path collisions between parallel enrichment jobs)

## Input Schema

Articles are provided as JSON with the following structure:

```json
{
  "articles": [
    {
      "article_id": "e4b4dc72744b064b",
      "title": "Article Title",
      "content": "Full article content...",
      "source": "source-name",
      "publish_date": "2025-12-21",
      "original_url": "https://...",
      "merged_from_urls": ["https://...", "https://..."]
    }
  ]
}
```

## Output Schema

Each enriched article contains:

```json
{
  "article_id": "e4b4dc72744b064b",
  "original_url": "https://original-article-url.com",
  "merged_from_urls": ["https://url1.com", "https://url2.com"],
  "title": "Article Title",
  "summary": "AI-generated summary in the article's language",
  "summary_translation": "Turkish translation (if original is not Turkish)",
  "x_post": "Twitter/X post with hashtags (max 280 chars)",
  "source": "source-name",
  "publish_date": "2025-12-21",
  "categories": [
    {"tag": "match-report", "confidence": 0.95},
    {"tag": "super-lig", "confidence": 0.90}
  ],
  "key_entities": {
    "teams": ["Fenerbahçe", "Galatasaray"],
    "players": ["Player Name"],
    "amounts": ["€10M", "3-0"],
    "dates": ["December 21, 2025"],
    "competitions": ["Süper Lig"],
    "locations": ["Istanbul"]
  },
  "content_quality": "high",
  "confidence": 0.95,
  "language": "tr",
  "region": "eu",
  "source_type": "complete",
  "_processing_metadata": {
    "enriched_at": "2025-12-21T10:15:46.177404+00:00",
    "enrichment_processor": "batch_enrichment"
  },
  "_merge_metadata": null
}
```

### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `article_id` | string | Unique identifier preserved from input |
| `original_url` | string | URL of the primary/original article |
| `merged_from_urls` | array | URLs of articles that were merged (empty for singletons) |
| `title` | string | Article title |
| `summary` | string | AI-generated summary in original language |
| `summary_translation` | string/null | Turkish translation (if original not Turkish) |
| `x_post` | string | Twitter/X post with relevant hashtags |
| `categories` | array | Content categories with confidence scores |
| `key_entities` | object | Extracted entities (teams, players, amounts, etc.) |
| `content_quality` | enum | `high`, `medium`, or `low` |
| `confidence` | number | Overall confidence score (0-1) |
| `language` | string | ISO language code |
| `region` | string | Geographic region (`eu`, `tr`, `us`) |

## Categories

The function categorizes articles using predefined tags:

- `transfers-confirmed`, `transfers-rumors`, `transfers-interest`
- `match-report`, `match-results`, `match-preview`
- `injury-news`, `contract-news`, `squad-changes`
- `performance-analysis`, `interviews`, `press-conference`
- `club-news`, `league-news`, `international-football`
- `super-lig`, `champions-league`, `europa-league`
- `basketball`, `off-field-scandals`, `legal-issues`

## Batch Processing

### FileData Pattern

The function uses the `fileData` pattern for efficient batch processing:

1. **Upload individual articles** to `input/batch_{i}.json` files
2. **Create batch request** with `fileData` references instead of inline content
3. **Submit to Vertex AI** batch prediction API

```json
{
  "request": {
    "contents": [
      {
        "role": "user",
        "parts": [
          {"text": "System prompt..."},
          {"fileData": {"fileUri": "gs://bucket/path/input/batch_0.json", "mimeType": "text/plain"}}
        ]
      }
    ],
    "generationConfig": {
      "responseMimeType": "application/json",
      "responseSchema": {...},
      "candidateCount": 1,
      "topP": 0.95
    }
  }
}
```

### Benefits

- **Reduced request size**: ~200 bytes per reference vs ~30KB inline content
- **Better scalability**: Handle larger batches without request size limits
- **Improved debugging**: Article content preserved in separate files

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GCP_PROJECT` | Google Cloud project ID |
| `BUCKET_NAME` | GCS bucket name (default: `aisports-scraping`) |
| `MODEL_ID` | Vertex AI model (default: `gemini-2.0-flash-001`) |
| `BATCH_SIZE` | Articles per batch request (default: `5`) |

## Dependencies

- `google-cloud-storage`
- `google-cloud-aiplatform`
- `functions-framework`

## Related Functions

- **article_processor_function**: Upstream - creates `singleton_*.json` and `grouped_*.json` files
- **merge_decider_function**: Upstream - creates `decision_*.json` files from grouped articles
- **jsonl_transformer_function**: Downstream - processes batch results
