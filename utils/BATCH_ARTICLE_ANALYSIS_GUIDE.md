# Batch Article Analysis Guide

This guide documents how to analyze and compare batch input/output files in the AI Sports pipeline to detect data loss during LLM enrichment.

## Overview

The pipeline sends articles to Gemini LLM in batches for enrichment. Articles flow through:
```
batch_enrichment/{source_type}/{branch_type}/input/batch_*.json
    → Gemini Batch API
        → batch_enrichment/{source_type}/{branch_type}/prediction-*/predictions.jsonl
```

**Source types**: `complete`, `scraped_incomplete`
**Branch types**: `merged`, `singleton`

## File Structures

### Input Files: `batch_*.json`

Location: `batch_enrichment/{source_type}/{branch_type}/input/batch_*.json`

```json
{
    "articles": [
        {
            "article_id": "2d2a2657bb70df6f",
            "title": "Article title",
            "body": "Full article body...",
            "url": "https://...",
            "merged_from_urls": ["https://..."],
            "source": "example.com",
            "publish_date": "2025-01-15T10:00:00Z",
            "language": "tr",
            "region": "tr"
        }
    ]
}
```

### Output Files: `predictions.jsonl`

Location: `batch_enrichment/{source_type}/{branch_type}/prediction-model-*/predictions.jsonl`

Each line is a JSON object containing:
- `request`: The original request sent to Gemini (contains input articles as escaped JSON)
- `response`: Gemini's response with enriched articles (contains output as escaped JSON)

The content is heavily escaped, so `article_id` appears as `\"article_id\"`.

## Counting Methods

### Method 1: Count Articles in Input Files

Count `"body"` field occurrences to find number of articles:

```python
import re

def count_body_in_json(file_path: str) -> int:
    """Count articles in input JSON file by counting 'body' field occurrences."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Count "body": occurrences (the field name followed by value)
    count = len(re.findall(r'"body"\s*:\s*"', content))
    return count
```

**Why `"body"`?**
- Every article in input has a `body` field
- It's unique per article (unlike `title` which could appear in other contexts)
- Simple regex pattern that doesn't get confused by nested structures

### Method 2: Count Articles in Output Files (Predictions)

Count `\"article_id\": \"<16-char-hex>\"` pattern in escaped JSONL:

```python
import re

def count_article_ids_in_jsonl(file_path: str) -> int:
    """
    Count articles in output JSONL prediction file.
    Matches pattern: \"article_id\": \"<16 hex chars>\"
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Match escaped article_id with hex value: \"article_id\": \"2d2a2657bb70df6f\"
    # Pattern: \"article_id\": \"<16 hex chars>\"
    escaped_count = len(re.findall(r'\\"article_id\\"\s*:\s*\\"[a-f0-9]{16}\\"', content))
    
    return escaped_count
```

**Why this specific regex?**
- `\\"article_id\\"` - Matches escaped quotes in JSONL format
- `\s*:\s*` - Handles optional whitespace around colon
- `\\"[a-f0-9]{16}\\"` - Matches exactly 16-character hex article IDs
- This pattern ONLY matches actual article IDs, not field names in schema definitions

**Example match:**
```
\"article_id\": \"2d2a2657bb70df6f\"
```

## Findings from Run 15-17-02

```
================================================================================
BATCH ARTICLE COUNT ANALYSIS
Run folder: pipeline_runs/15-17-02
================================================================================

📁 complete/merged
   INPUT FILES (counting 'body' occurrences):
      batch_0.json: 10 articles
      batch_1.json: 10 articles
      batch_2.json: 10 articles
      batch_3.json: 10 articles
      batch_4.json: 10 articles
      batch_5.json: 10 articles
      batch_6.json: 3 articles
      SUBTOTAL: 63 articles

   OUTPUT FILES (counting 'article_id'):
      prediction-model-2025-12-21T14:22:11.415644Z: 45 articles
      SUBTOTAL: 45 articles

   ⚠️  DIFF: 18 articles LOST

📁 complete/singleton
   INPUT: 26 articles → OUTPUT: 26 articles ✅ MATCH

📁 scraped_incomplete/merged
   INPUT: 3 articles → OUTPUT: 3 articles ✅ MATCH

📁 scraped_incomplete/singleton
   INPUT: 4 articles → OUTPUT: 4 articles ✅ MATCH

================================================================================
GRAND TOTAL
================================================================================
   Total Input Articles:  96
   Total Output Articles: 78
   ⚠️  TOTAL DIFF: 18 articles LOST (all in complete/merged)
================================================================================
```

## Key Insights

1. **Data Loss Location**: The `complete/merged` branch lost 18 articles (63 → 45)
2. **Other Branches OK**: `singleton` branches and `scraped_incomplete` had no data loss
3. **Root Cause**: Likely LLM truncation or batch processing issues with merged articles (which tend to be longer due to combined content)

## Usage

Run the analysis script:

```bash
python3 aisports-functions/utils/count_batch_articles.py <run_folder>

# Example:
python3 aisports-functions/utils/count_batch_articles.py pipeline_runs/15-17-02
```

## Shell Commands for Quick Verification

### Count article_ids in a prediction file:
```bash
grep -o '\\"article_id\\"\s*:\s*\\"[a-f0-9]\{16\}\\"' predictions.jsonl | wc -l
```

### Count body fields in input files:
```bash
grep -o '"body"\s*:\s*"' batch_*.json | wc -l
```

### Count lines (batches) in predictions.jsonl:
```bash
wc -l predictions.jsonl
```

## Folder Structure Reference

```
pipeline_runs/{run_id}/
├── batch_enrichment/
│   ├── complete/
│   │   ├── merged/
│   │   │   ├── input/
│   │   │   │   ├── batch_0.json
│   │   │   │   ├── batch_1.json
│   │   │   │   └── ...
│   │   │   ├── metadata.json
│   │   │   ├── request.jsonl
│   │   │   └── prediction-model-{timestamp}/
│   │   │       └── predictions.jsonl
│   │   └── singleton/
│   │       ├── input/
│   │       │   └── batch_*.json
│   │       └── prediction-model-{timestamp}/
│   │           └── predictions.jsonl
│   └── scraped_incomplete/
│       ├── merged/
│       │   └── ...
│       └── singleton/
│           └── ...
├── enriched_complete_articles.json
├── enriched_scraped_incomplete_articles.json
└── ...
```

## Related Files

- **Analysis Script**: `aisports-functions/utils/count_batch_articles.py`
- **JSONL Transformer**: `aisports-functions/jsonl_transformer_function/main.py` - Processes predictions.jsonl
- **Article Enricher**: `aisports-functions/article_enricher_function/main.py` - Creates batch input files
