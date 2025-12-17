# News API Content Enrichment - Implementation Status

## ✅ Completed (Phases 1-5 Redesigned)

### Phase 1: Content Detection ✅
**File**: `news_aggregator.py`

- ✅ Added `is_content_complete()`: Detects truncated content using `[+N chars]` pattern
- ~~Removed `classify_region()`~~: Region-based splitting removed for simplification

### Phase 2: Article Classification & Schema Transformation ✅
**File**: `news_api_fetcher_function/main.py`

- ✅ Added `generate_article_id()`: Generates MD5-based article IDs
- ✅ Added `transform_api_article_to_session_schema()`: Transforms API articles to match scraper schema
- ✅ Splits articles into complete/incomplete (no region distinction)
- ✅ Transforms complete articles to session schema format
- ✅ Saves complete articles to `complete_articles.json` (renamed from articles.json)

### Phase 3: Scraper Triggering ✅ (Simplified)
**File**: `news_api_fetcher_function/main.py`

- ✅ Simplified `trigger_scraper_for_incomplete_articles()`: Single message for all incomplete articles
- ✅ Removed region-based splitting (TR/EU)
- ✅ Passes only `api_run_path` parameter (no output_filename)
- ✅ Function exits immediately after triggering (no waiting)

### Phase 4: Scraper Integration ✅ (Redesigned)
**File**: `scraper_function/main.py`

- ✅ Detects API integration mode (`api_run_path` parameter)
- ✅ Merges all sessions into single file
- ✅ Outputs to `scrape_results/articles_scraped.json` (new location)
- ✅ **Always publishes to SESSION_DATA_CREATED_TOPIC** with both files:
  - `scrape_results/articles_scraped.json`
  - `complete_articles.json`

---

## 📂 New Folder Structure (Simplified)

```
news_data/api/2025-12/2025-12-17/run_10-59-06/
  ├── complete_articles.json     # Complete API articles (session schema)
  ├── scrape_results/
  │   └── articles_scraped.json  # All scraped articles merged (session schema)
  ├── metadata.json              # Run metadata
  └── responses/                 # Raw API responses
      ├── newsapi.json
      ├── worldnewsapi.json
      └── gnews.json
```

---

## 📋 Consistent Schema Across All Files

All three article files now use the **same session schema**:

```json
{
  "source_domain": "api_combined",
  "source_url": "https://api-news-aggregator",
  "articles": [
    {
      "url": "https://...",
      "scraped_at": "2025-12-17T10:59:06Z",
      "keywords_used": ["fenerbahce", "galatasaray"],
      "title": "Article Title",
      "body": "Full article content...",
      "published_at": "2025-12-17T10:30:00Z",
      "source": "example.com",
      "extraction_method": "api:gnews",
      "site": "example.com",
      "article_id": "a4bcce7f4fb0a77a"
    }
  ],
  "session_metadata": {
    "session_id": "api_10-59-06",
    "fetched_at": "2025-12-17T10:59:06Z",
    "collection_id": "mixed",
    "source_count": 5,
    "extraction_method": "api_aggregation"
  }
}
```

### Schema Fields

| Field | Description | Source |
|-------|-------------|--------|
| `url` | Article URL | API or scraped |
| `scraped_at` | Timestamp when processed | Generated |
| `keywords_used` | Keywords that matched | From request |
| `title` | Article title | API or scraped |
| `body` | Full content (not truncated!) | API or scraped |
| `published_at` | Original publish date | API metadata |
| `source` | Domain name | Extracted from URL |
| `extraction_method` | How it was extracted | `api:gnews`, `journalist`, etc. |
| `site` | Domain name | Extracted from URL |
| `article_id` | MD5-based unique ID | Generated from URL |

---

## 🔄 New Event-Driven Data Flow (Simplified)

```
1. News API Fetch
   ↓
2. Classify by Completeness (no region)
   ├─ Complete (30 articles)
   │  └─ Transform to session schema
   │     └─ Save to complete_articles.json
   │
   └─ Incomplete (40 articles)
      └─ Single batch of all incomplete articles
         └─ Trigger scraper via Pub/Sub → EXIT

3. Scraper Function (triggered separately)
   ├─ Scrape all incomplete articles
   ├─ Merge all into single file
   ├─ Save to scrape_results/articles_scraped.json
   └─ Publish to SESSION_DATA_CREATED_TOPIC with:
      • scrape_results/articles_scraped.json
      • complete_articles.json

4. Batch Builder Function (triggered by SESSION_DATA_CREATED_TOPIC)
   └─ Creates Stage 1 batch job for both files

5. Result Merger Function (triggered by Stage 1 completion)
   └─ Creates Stage 2 deduplication batch job
```

### Two Possible Paths

**Path A: All Complete (no scraping needed)**
```
news_api_fetcher → complete_articles.json → SESSION_DATA_CREATED_TOPIC → batch_builder
```

**Path B: Mixed Complete + Incomplete**
```
news_api_fetcher → complete_articles.json + trigger scraper → EXIT
                     ↓
                   scraper → articles_scraped.json + SESSION_DATA_CREATED_TOPIC → batch_builder
```

---

## ✅ Phase 5: Event-Driven Architecture (Redesigned)

**Files Modified**: `news_api_fetcher_function/main.py`, `scraper_function/main.py`

### New Implementation Approach

**Event-Driven Pattern:**
- No waiting or polling
- Each function does ONE job and exits
- Pub/Sub messages trigger next stage
- Natural retries and error handling

### Key Changes

#### Removed Functions
- ~~`wait_for_scraped_files()`~~: Eliminated polling and timeouts
- ~~`classify_region()`~~: Removed region-based complexity

#### Modified Functions

**`trigger_scraper_for_incomplete_articles()`**
- Now accepts flat list of articles (no region grouping)
- Publishes single message to scraping-requests topic
- Returns immediately (no waiting)

**`publish_batch_processing_request()`**
- Updated to use `gcs_path` format (matching batch_builder expectations)
- Simplified message structure

### Execution Flows

**Scenario 1: All complete articles**
1. news_api_fetcher writes complete_articles.json
2. Publishes to SESSION_DATA_CREATED_TOPIC immediately
3. Exits with success
4. batch_builder processes the file

**Scenario 2: Some incomplete articles**
1. news_api_fetcher writes complete_articles.json
2. Triggers scraper via scraping-requests topic
3. Exits with success
4. scraper_function (separate execution):
   - Scrapes incomplete articles
   - Writes to scrape_results/articles_scraped.json
   - Publishes to SESSION_DATA_CREATED_TOPIC with both files
5. batch_builder processes both files

### Batch Processing Results Location

```
news_data/api/.../run_XX-XX-XX/
  ├── complete_articles.json
  ├── scrape_results/
  │   └── articles_scraped.json
  ├── stage1_extraction/
  │   ├── requests/request.jsonl
  │   └── results/predictions.jsonl
  └── stage2_deduplication/
      ├── input_merged_data/
      ├── requests/request.jsonl
      └── results/predictions.jsonl
```

---

## 🎯 Next Step (Phase 6)

### Phase 6: Final Output (TODO)

**Goal**: Create `enriched_articles.json` with AI processing results

**Contents**:
- Deduplicated articles from all three sources
- AI-generated summaries
- Category classifications
- Translations (EU → TR)
- X post suggestions

---

## 📊 Benefits of New Architecture

1. **Full Content**: No more truncated `[+497 chars]` - all articles have complete text
2. **Unified Schema**: All files use same format - easy to process together
3. **Simplified Flow**: No region classification - single merged file for all scraped articles
4. **Event-Driven**: No polling or waiting - natural Pub/Sub flow
5. **Reliability**: Each function exits cleanly, natural retries via Pub/Sub
6. **Debuggability**: Clear message trail through Cloud Logging
7. **Quality Improvement**: Uses existing high-quality batch processing pipeline
8. **Backwards Compatible**: Traditional scraping pipeline unchanged

---

## 🔧 Modified Files (Redesign)

### news_api_fetcher_function
1. `news_aggregator.py` - Content detection:
   - `is_content_complete()`: Detects truncated content
   - ~~Removed `classify_region()`~~: Region classification eliminated

2. `main.py` - Simplified event-driven flow:
   - `generate_article_id()`: Generate MD5-based article IDs
   - `transform_api_article_to_session_schema()`: Transform API → session schema
   - **Simplified `trigger_scraper_for_incomplete_articles()`**: Single message, no regions
   - ~~Removed `wait_for_scraped_files()`~~: Polling eliminated
   - **Updated `publish_batch_processing_request()`**: Uses `gcs_path` format
   - **Redesigned `fetch_and_store_news()`**: No waiting, immediate exit

### scraper_function
1. `main.py` - Simplified API integration:
   - Detects `api_run_path` parameter
   - Merges all sessions into single file (no region distinction)
   - Outputs to `scrape_results/articles_scraped.json`
   - **Always publishes to SESSION_DATA_CREATED_TOPIC** with both files

### batch_builder_function
1. `main.py` - Updated to detect and handle API paths:
   - `extract_path_info_from_source_files()`: Detects API vs traditional paths
   - `upload_batch_request_to_gcs()`: Uses API base path for stage1_extraction/requests
   - `submit_batch_job()`: Uses API base path for stage1_extraction/results
   - `save_batch_metadata()`: Saves metadata under API run folder

### result_merger_function
1. `main.py` - Updated to detect and handle API paths:
   - Path parsing in `merge_results()`: Detects API paths
   - `upload_merged_data()`: Uses API base path for stage2_deduplication/input_merged_data
   - `upload_dedup_request()`: Uses API base path for stage2_deduplication/requests
   - `submit_dedup_batch_job()`: Uses API base path for stage2_deduplication/results

### No Changes Required
- `aisports-ui` (will display enriched articles)

---

## 🐛 Known Limitations (Updated)

1. ~~**No Retry Mechanism**~~: Pub/Sub provides automatic retries for failed functions
2. ~~**Timeout Fixed at 5 Minutes**~~: No timeout - functions exit immediately
3. **Phase 6 Not Implemented**: Final enriched_articles.json not yet created
4. **Single Scraper Invocation**: All incomplete articles scraped in one batch (not parallelized by region)

---

## 🚀 Testing Checklist (Updated)

- [x] Test content completeness detection with real API responses
- ~~[ ] Test region classification (TR vs EU)~~ - Removed
- [x] Test scraper triggering via Pub/Sub (simplified)
- [x] Test schema consistency across all files
- [x] Test event-driven batch processing integration
- [ ] Test end-to-end flow with real data (complete-only scenario)
- [ ] Test end-to-end flow with real data (mixed scenario)

---

## 📝 Notes (Updated)

- **Event-Driven Architecture**: No polling or waiting - clean Pub/Sub flow
- **Scrape Depth**: Using `scrape_depth=0` for incomplete articles (no link discovery)
- **Deduplication**: Cross-run deduplication already implemented
- **Pub/Sub Topics**:
  - `scraping-requests`: Triggers scraper_function
  - `SESSION_DATA_CREATED_TOPIC`: Triggers batch_builder_function
- **Single File Output**: All scraped articles merged into `articles_scraped.json`
- **Backwards Compatible**: Traditional scraping (without `api_run_path`) still works
- **Resilience**: Natural retries via Pub/Sub, no complex error handling needed

---

## 🔄 Redesign Summary (December 2025)

**Problem**: Original architecture had fragile waiting logic that caused premature exits and missed batch processing triggers (issue observed in run_12-55-11).

**Solution**: Complete redesign to event-driven architecture:
- ✅ Eliminated polling/waiting logic
- ✅ Removed region-based complexity
- ✅ Each function exits immediately after its job
- ✅ Pub/Sub handles orchestration and retries
- ✅ Simplified file structure (2 files instead of 3)

**Result**: Cleaner, more reliable pipeline with better debuggability.
