# Plan: Homologate API and Scrape Branch File Structure

## Goals
1. Make run folder more readable
2. Homologate api and scrape branches (no case-specific handles)
3. Simplify triggers - 1 file instead of 3

---

## Current State (Problem)

```
ingestion/YYYY-MM-DD/HH-MM-SS/
├── complete_articles.json              # API with full body
├── to_scrape.json                      # API incomplete → triggers scraper
├── scraped_articles.json               # Standalone scraped
├── scraped_incomplete_articles.json    # Scraped from API incomplete
├── singleton_{complete,scraped,scraped_incomplete}_articles.json (x3)
├── grouped_{complete,scraped,scraped_incomplete}_articles.json (x3)
├── decision_{complete,scraped,scraped_incomplete}_articles.json (x3)
├── enriched_{complete,scraped,scraped_incomplete}_articles.json (x3)
└── batch_enrichment/{complete,scraped,scraped_incomplete}/...
```

**Problems:**
- 15+ files with verbose names
- 3 enriched outputs = 3 triggers needed
- Case-specific handling throughout pipeline

---

## Final Structure (2 Folders + Combined Output)

```
ingestion/YYYY-MM-DD/HH-MM-SS/
├── responses/                    # Raw API responses (existing)
│   ├── gnews.json
│   └── worldnewsapi.json
│
├── api/                          # Source: News API (complete body)
│   ├── articles.json             # was: complete_articles.json
│   ├── singletons.json
│   ├── groups.json
│   └── decisions.json
│
├── scraped/                      # ALL scraped (merged: standalone + api_incomplete)
│   ├── to_fetch.json             # was: to_scrape.json (triggers scraper)
│   ├── articles.json             # was: scraped_articles.json + scraped_incomplete_articles.json
│   ├── singletons.json
│   ├── groups.json
│   └── decisions.json
│
├── batch_enrichment/             # Intermediate batch files
│   ├── api/...
│   └── scraped/...
│
└── enriched_articles.json        # SINGLE OUTPUT - combines api + scraped
```

**Key changes:**
- `api_scraped` merged INTO `scraped/` (differentiate by `source_type` field)
- ONE enriched output file → ONE trigger needed
- Consistent folder structure: `{folder}/articles.json`, `{folder}/singletons.json`, etc.

---

## source_type Values

| source_type | Description |
|-------------|-------------|
| `api` | News API with complete body |
| `scraped` | Standalone scraper OR API incomplete → scraped |

The distinction between "API incomplete" and "standalone scrape" is preserved in `_processing_metadata.origin`:
- `origin: "api_incomplete"` - came from to_fetch.json
- `origin: "standalone"` - triggered directly via Pub/Sub

---

## Trigger Simplification

**Before:** 3 Eventarc triggers
```
enriched_complete_articles.json
enriched_scraped_articles.json
enriched_scraped_incomplete_articles.json
```

**After:** 1 Eventarc trigger
```
enriched_articles.json
```

---

## Implementation Steps

### Step 1: Update news_api_fetcher_function/main.py
- Output: `api/articles.json` (was `complete_articles.json`)
- Output: `scraped/to_fetch.json` (was `to_scrape.json`)

### Step 2: Update scraper_function/main.py
- Output: `scraped/articles.json` (APPEND mode - both API incomplete AND standalone)
- Remove case-specific file naming logic

### Step 3: Update article_processor_function/main.py
- Input: `api/articles.json` OR `scraped/articles.json`
- Output: `{source}/singletons.json`, `{source}/groups.json`
- Generic handling - no source-type specific logic

### Step 4: Update merge_decider_function/main.py
- Input: `{source}/groups.json`
- Output: `{source}/decisions.json`

### Step 5: Update article_enricher_function/main.py
- Input: `{source}/singletons.json` + `{source}/decisions.json`
- Aggregate BOTH api + scraped into batch
- Output: `enriched_articles.json` (SINGLE combined file)

### Step 6: Update jsonl_transformer_function/main.py
- Output: `enriched_articles.json` (append/merge mode)

### Step 7: Update gcs_api_function/main.py
- Input: `enriched_articles.json` (single file)

### Step 8: Update Eventarc triggers
- Pattern: `ingestion/**/enriched_articles.json`

---

## Files to Modify

| File | Changes |
|------|---------|
| `news_api_fetcher_function/main.py` | Output paths: `api/`, `scraped/to_fetch.json` |
| `scraper_function/main.py` | Output: `scraped/articles.json`, remove case handling |
| `article_processor_function/main.py` | Generic `{source}/` paths |
| `merge_decider_function/main.py` | Generic `{source}/` paths |
| `article_enricher_function/main.py` | Aggregate both sources → single output |
| `jsonl_transformer_function/main.py` | Single output path |
| `gcs_api_function/main.py` | Read single enriched file |
| `.github/workflows/*.yml` | Simplified trigger patterns |

---

## Migration Strategy

1. Deploy with backwards-compatible reading (check both old and new paths)
2. Run one full pipeline cycle
3. Verify enriched_articles.json contains all articles
4. Remove backwards-compat code
5. Clean up old file patterns from GCS
