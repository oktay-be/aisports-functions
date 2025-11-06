# GCS Folder Structure for Batch Processing

## Overview

This document explains the organized folder structure for batch processing results in Google Cloud Storage.

## Complete Folder Hierarchy

```
gs://aisports-scraping/
└── news_data/
    └── batch_processing/
        └── {YYYY-MM}/                              # Date-based partitioning
            ├── batch_results_raw/                   # Raw Vertex AI predictions (multiple candidates)
            │   └── {batch_id}/                      # e.g., 20251106_083721_002
            │       └── prediction-model-{timestamp}/
            │           └── predictions.jsonl        # Multiple candidates per source
            │
            ├── batch_results_merged/                # Merged results (candidates combined)
            │   └── batch_{dedup_batch_id}/          # e.g., batch_dedup_20251106_103000
            │       ├── merged_session_data_fanatik.com.tr.json
            │       ├── merged_session_data_sporx.com.json
            │       └── merged_session_data_*.json   # One merged file per source
            │
            ├── dedup_batch_{dedup_batch_id}/        # Deduplication batch requests
            │   └── request.jsonl                    # Batch request for deduplication
            │
            └── dedup_results/                       # Final deduplicated results
                └── {dedup_batch_id}/                # e.g., dedup_20251106_103000
                    └── prediction-model-{timestamp}/
                        └── predictions.jsonl        # Single candidate (deduplicated)
```

## Folder Purpose & Content

### 1. `batch_results_raw/`
**Purpose**: Store raw Vertex AI batch prediction results with multiple candidates

**Created by**: Vertex AI Batch API (via batch_builder_function)

**Content Structure**:
```json
// predictions.jsonl - each line:
{
  "request": {...},
  "response": {
    "candidates": [
      {"content": {...}, "avgLogprobs": -0.11464},  // Candidate 0: 23 articles
      {"content": {...}, "avgLogprobs": -0.10573}   // Candidate 1: 54 articles
    ]
  }
}
```

**Example Path**:
```
gs://aisports-scraping/news_data/batch_processing/2025-10/batch_results_raw/20251025_083721_002/prediction-model-2025-10-25T08:37:21.590419Z/predictions.jsonl
```

**Triggers**: Result Merger Function (GCS object finalized event)

---

### 2. `batch_results_merged/`
**Purpose**: Store merged results from multiple AI candidates (before deduplication)

**Created by**: result_merger_function

**Content Structure**:
```json
// merged_session_data_SOURCE.json
{
  "source_file": "gs://.../session_data_fanatik.com.tr.json",
  "source_domain": "fanatik.com.tr",
  "merge_timestamp": "2025-11-06T10:30:00Z",
  "merge_statistics": {
    "total_articles_before_dedup": 77,
    "num_candidates_merged": 2,
    "candidates_avg_logprobs": [-0.11464, -0.10573],
    "pandas_analysis": {
      "unique_urls": 45,
      "content_quality_distribution": {"high": 50, "medium": 20, "low": 7}
    }
  },
  "articles": [
    {
      "original_url": "...",
      "title": "...",
      "_merge_metadata": {
        "candidate_index": 1,
        "candidate_avg_logprobs": -0.10573
      }
    }
  ]
}
```

**Example Path**:
```
gs://aisports-scraping/news_data/batch_processing/2025-11/batch_results_merged/batch_dedup_20251106_103000/merged_session_data_fanatik.com.tr.json
```

**Used by**: Vertex AI (as input for deduplication batch job)

---

### 3. `dedup_batch_{id}/`
**Purpose**: Store deduplication batch request JSONL files

**Created by**: result_merger_function

**Content Structure**:
```json
// request.jsonl - each line:
{
  "request": {
    "contents": [
      {
        "role": "user",
        "parts": [
          {"text": "<DEDUP_PROMPT.md contents>"},
          {"fileData": {"fileUri": "gs://.../merged_fanatik.com.tr.json"}}
        ]
      }
    ],
    "generationConfig": {
      "candidateCount": 1,
      "temperature": 0.05,
      "responseSchema": {...}
    }
  }
}
```

**Example Path**:
```
gs://aisports-scraping/news_data/batch_processing/2025-11/dedup_batch_20251106_103000/request.jsonl
```

**Used by**: Vertex AI Batch API (as input)

---

### 4. `dedup_results/`
**Purpose**: Store final deduplicated results from Vertex AI

**Created by**: Vertex AI Batch API (after processing dedup requests)

**Content Structure**:
```json
// predictions.jsonl - each line:
{
  "request": {...},
  "response": {
    "candidates": [
      {
        "content": {
          "parts": [{
            "text": "{\"processing_summary\":{\"articles_deduplicated\":32,...}, \"processed_articles\":[...]}"
          }]
        }
      }
    ]
  }
}
```

**Example Path**:
```
gs://aisports-scraping/news_data/batch_processing/2025-11/dedup_results/dedup_20251106_103000/prediction-model-2025-11-06T10:30:01.234567Z/predictions.jsonl
```

**Triggers**: (Future) Final Processor Function OR stores to database/BigQuery

---

## Data Flow Through Folders

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Batch Processing Pipeline                        │
└─────────────────────────────────────────────────────────────────────────┘

1. Batch Builder Function
   Creates batch request → Submits to Vertex AI
   ↓
   batch_results_raw/
   ├── 20251106_083721_002/
   │   └── prediction-model-2025-11-06T08:37:21.590419Z/
   │       └── predictions.jsonl (Multiple candidates: 23 + 54 = 77 articles)
   ↓
   [GCS Event Trigger: object.v1.finalized]
   ↓
2. Result Merger Function
   Downloads raw → Merges candidates → Uploads merged data
   ↓
   batch_results_merged/
   ├── batch_dedup_20251106_103000/
   │   ├── merged_session_data_fanatik.com.tr.json (77 articles with stats)
   │   └── merged_session_data_sporx.com.json
   ↓
   Creates dedup request → Uploads to GCS
   ↓
   dedup_batch_20251106_103000/
   └── request.jsonl (References merged files)
   ↓
   Submits to Vertex AI Batch API
   ↓
3. Vertex AI Deduplication
   Processes merged data → Applies DEDUP_PROMPT.md rules
   ↓
   dedup_results/
   └── dedup_20251106_103000/
       └── prediction-model-2025-11-06T10:30:01.234567Z/
           └── predictions.jsonl (45 unique articles - deduplicated!)
   ↓
   [Future: Final Processor or Database Storage]
```

## Naming Conventions

### Batch IDs
- **Raw batch**: `{YYYYMMDD}_{HHMMSS}_{sequence}` 
  - Example: `20251106_083721_002`
- **Dedup batch**: `dedup_{YYYYMMDD}_{HHMMSS}`
  - Example: `dedup_20251106_103000`

### File Names
- **Raw predictions**: `prediction-model-{ISO_timestamp}/predictions.jsonl`
- **Merged data**: `merged_session_data_{domain}.json`
- **Dedup request**: `request.jsonl`
- **Dedup results**: `prediction-model-{ISO_timestamp}/predictions.jsonl`

### Date Partitioning
- Format: `{YYYY}-{MM}` (e.g., `2025-11`)
- Based on UTC timezone
- All batch processing for a given month stored in same date folder

## Storage Benefits

### ✅ Clear Separation
- **Raw** vs **Merged** vs **Deduplicated** results are in separate folders
- Easy to identify processing stage
- No confusion about data state

### ✅ Chronological Organization
- Date-based partitioning (`2025-11/`)
- Easy to manage retention policies
- Efficient querying by time period

### ✅ Traceability
- Each merged file links back to source file
- Batch IDs provide lineage tracking
- Metadata preserved at each stage

### ✅ Event-Driven Triggers
- GCS events trigger on specific patterns
- Only `batch_results_raw/*_predictions.jsonl` triggers merger
- Prevents duplicate processing

### ✅ Scalability
- Handles multiple concurrent batches
- Independent processing per source
- Parallel deduplication jobs

## File Size Estimates

| Folder | Typical Size per Batch | Retention |
|--------|------------------------|-----------|
| `batch_results_raw/` | 5-50 MB | 90 days |
| `batch_results_merged/` | 2-20 MB | 30 days |
| `dedup_batch_{id}/` | 10-100 KB | 7 days |
| `dedup_results/` | 2-15 MB | Permanent |

## Monitoring Queries

### List all raw batch results for current month
```bash
gsutil ls "gs://aisports-scraping/news_data/batch_processing/$(date +%Y-%m)/batch_results_raw/**"
```

### List merged results waiting for deduplication
```bash
gsutil ls "gs://aisports-scraping/news_data/batch_processing/$(date +%Y-%m)/batch_results_merged/**"
```

### Check dedup results
```bash
gsutil ls "gs://aisports-scraping/news_data/batch_processing/$(date +%Y-%m)/dedup_results/**"
```

### Count articles in merged file (with stats)
```bash
gsutil cat "gs://aisports-scraping/news_data/batch_processing/2025-11/batch_results_merged/batch_dedup_20251106_103000/merged_session_data_fanatik.com.tr.json" | jq '.merge_statistics'
```

## Cleanup Strategy

### Automated Lifecycle Rules (Recommended)

```bash
# Raw results: Delete after 90 days
gsutil lifecycle set lifecycle-raw.json gs://aisports-scraping/

# lifecycle-raw.json:
{
  "rule": [{
    "action": {"type": "Delete"},
    "condition": {
      "age": 90,
      "matchesPrefix": ["news_data/batch_processing/*/batch_results_raw/"]
    }
  }]
}

# Merged results: Delete after 30 days
# Dedup requests: Delete after 7 days
# Dedup results: Keep permanently
```

### Manual Cleanup
```bash
# Delete old raw batches (older than 90 days)
gsutil -m rm -r "gs://aisports-scraping/news_data/batch_processing/2025-08/batch_results_raw/**"

# Delete processed merged results (after dedup completes)
gsutil -m rm -r "gs://aisports-scraping/news_data/batch_processing/2025-10/batch_results_merged/**"
```

## Troubleshooting

### Merged files not created
- Check result_merger_function logs
- Verify GCS trigger pattern matches `batch_results_raw/`
- Check service account permissions

### Dedup job not starting
- Verify merged files exist in `batch_results_merged/`
- Check Vertex AI quota
- Verify DEDUP_PROMPT.md is loaded correctly

### Missing predictions.jsonl
- Vertex AI may nest under additional folder (timestamp-based)
- Check full path: `prediction-model-{timestamp}/predictions.jsonl`
- Verify batch job completed successfully

## Future Enhancements

- [ ] Add `final_results/` folder for database-ready data
- [ ] Implement automatic archival to BigQuery
- [ ] Add quality metrics per folder
- [ ] Create dashboard for monitoring folder statistics
- [ ] Implement automatic cleanup based on dedup completion status
