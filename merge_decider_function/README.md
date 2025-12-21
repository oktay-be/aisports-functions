# Merge Decider Function

Cloud Function that uses Vertex AI batch processing to decide whether similar article groups should be merged or kept separate.

## Overview

This function is triggered when `grouped_*.json` files are uploaded to the GCS bucket. It submits groups of similar articles to Vertex AI for merge decisions.

## Trigger Files

| Trigger File Pattern | Description |
|---------------------|-------------|
| `grouped_complete_articles.json` | Complete articles with full content |
| `grouped_scraped_incomplete_articles.json` | Scraped articles needing enrichment |
| `grouped_scraped_articles.json` | General scraped articles |

## GCS Path Structure

```
aisports-scraping/
└── ingestion/{date}/{run_id}/
    ├── grouped_{source_type}_articles.json  # Input trigger
    └── batch_merge/{source_type}/
        ├── input/
        │   └── batch_{i}.json              # Group data for fileData reference
        ├── request.jsonl                   # Batch request
        ├── metadata.json                   # Job metadata
        └── {prediction-folder}/            # Batch prediction outputs
```

## Input Schema

Groups are provided as JSON with article metadata including URLs:

```json
{
  "groups": [
    {
      "group_id": 1,
      "max_similarity": 0.85,
      "articles": [
        {
          "article_id": "abc123",
          "url": "https://example.com/article",
          "title": "Article title",
          "body": "Article content...",
          "source": "example.com"
        }
      ]
    }
  ]
}
```

### Input Fields

| Field | Type | Description |
|-------|------|-------------|
| `group_id` | integer | Unique identifier for the group |
| `max_similarity` | number | Highest similarity score within group |
| `articles` | array | Articles in this group |
| `articles[].article_id` | string | Unique article identifier |
| `articles[].url` | string | Original article URL |
| `articles[].title` | string | Article title |
| `articles[].body` | string | Article content (truncated to 1000 chars) |
| `articles[].source` | string | Source website |

## Output Schema

LLM returns decisions for each group:

```json
{
  "decisions": [
    {
      "group_id": 1,
      "decision": "MERGE",
      "reason": "Both articles report the same match result",
      "primary_article_id": "abc123",
      "primary_article_url": "https://example.com/best-article",
      "merged_article_ids": ["abc123", "def456"],
      "merged_from_urls": ["https://example.com/article1", "https://example.com/article2"]
    }
  ]
}
```

### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `group_id` | integer | Group being decided |
| `decision` | enum | `MERGE` or `KEEP_BOTH` |
| `reason` | string | Brief explanation for the decision |
| `primary_article_id` | string/null | ID of best article (MERGE only) |
| `primary_article_url` | string/null | URL of best article (MERGE only) |
| `merged_article_ids` | array | **DEPRECATED** - IDs of merged articles |
| `merged_from_urls` | array | URLs of all merged articles |

> **Note**: `merged_article_ids` is deprecated. Use `merged_from_urls` for URL tracking throughout the pipeline.

## Decision Criteria

### MERGE when:
- Articles report the exact same match result
- Articles announce the same transfer deal
- Articles quote the same press conference
- Articles are essentially duplicates with minor wording differences

### KEEP_BOTH when:
- One is a match report, another is player interview
- One is breaking news, another is in-depth analysis
- Articles cover different aspects of the same broader topic
- Articles have significantly different perspectives or sources

## Batch Processing

### FileData Pattern

The function uses the `fileData` pattern for efficient batch processing:

1. **Upload group data** to `input/batch_{i}.json` files
2. **Create batch request** with `fileData` references instead of inline content
3. **Submit to Vertex AI** batch prediction API
4. **Exit immediately** - no polling, results processed by `jsonl_transformer_function`

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
      "topP": 0.9,
      "temperature": 0.1
    }
  }
}
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLOUD_PROJECT` | Google Cloud project ID |
| `GCS_BUCKET_NAME` | GCS bucket name (default: `aisports-scraping`) |
| `VERTEX_AI_LOCATION` | Vertex AI region (default: `us-central1`) |
| `VERTEX_AI_MODEL` | Model ID (default: `gemini-2.0-flash`) |

## Dependencies

- `google-cloud-storage`
- `google-genai`
- `functions-framework`

## Related Functions

- **article_processor_function**: Upstream - creates `grouped_*.json` files from similarity grouping
- **jsonl_transformer_function**: Downstream - processes batch results and applies merge decisions
- **article_enricher_function**: Downstream - enriches merged/separated articles
