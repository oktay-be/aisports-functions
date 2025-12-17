# News API Content Enrichment - Implementation Status

## ✅ Completed (Phases 1-5)

### Phase 1: Content Detection ✅
**File**: `news_aggregator.py`

- ✅ Added `is_content_complete()`: Detects truncated content using `[+N chars]` pattern
- ✅ Added `classify_region()`: Classifies articles as TR/EU based on language field

### Phase 2: Article Classification & Schema Transformation ✅
**File**: `news_api_fetcher_function/main.py`

- ✅ Added `generate_article_id()`: Generates MD5-based article IDs
- ✅ Added `transform_api_article_to_session_schema()`: Transforms API articles to match scraper schema
- ✅ Splits articles into complete/incomplete by region
- ✅ Transforms complete articles to session schema format
- ✅ Saves only complete articles to `articles.json`

### Phase 3: Scraper Triggering ✅
**File**: `news_api_fetcher_function/main.py`

- ✅ Added `trigger_scraper_for_incomplete_articles()`: Triggers scraper via Pub/Sub
- ✅ Publishes two separate messages (TR and EU) with region-specific filenames
- ✅ Passes `api_run_path` and `output_filename` parameters

### Phase 4: Scraper Integration ✅
**File**: `scraper_function/main.py`

- ✅ Detects API integration mode (`api_run_path` parameter)
- ✅ Merges all sessions into single file per region
- ✅ Outputs session schema format matching traditional scraping
- ✅ Saves to `articles_scraped_{region}.json`
- ✅ Skips normal batch processing in API mode

---

## 📂 Current Folder Structure

```
news_data/api/2025-12/2025-12-17/run_10-59-06/
  ├── articles.json              # Complete API articles (session schema)
  ├── articles_scraped_tr.json   # Scraped Turkish articles (session schema)
  ├── articles_scraped_eu.json   # Scraped EU articles (session schema)
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

## 🔄 Data Flow

```
1. News API Fetch
   ↓
2. Classify by Completeness & Region
   ├─ Complete (30 articles)
   │  └─ Transform to session schema
   │     └─ Save to articles.json
   │
   └─ Incomplete (40 articles)
      ├─ TR (25 articles)
      │  └─ Trigger scraper via Pub/Sub
      │     └─ Save to articles_scraped_tr.json
      │
      └─ EU (15 articles)
         └─ Trigger scraper via Pub/Sub
            └─ Save to articles_scraped_eu.json
```

### After Scraper Completes

```
news_data/api/.../run_XX-XX-XX/
  ├── articles.json (30 complete)
  ├── articles_scraped_tr.json (25 scraped TR)
  └── articles_scraped_eu.json (15 scraped EU)
      ↓
  Total: 70 articles with full content
```

---

## ✅ Phase 5: Batch Processing Integration (Completed)

**File**: `news_api_fetcher_function/main.py`

### Implementation Approach

**Followed scraper_function pattern exactly:**
- News API fetcher waits synchronously for scraper completion (Option C)
- Polls GCS for articles_scraped_tr.json and articles_scraped_eu.json
- Collects all 3 file paths (articles.json + scraped files)
- Publishes ONE batch message to session-data-created (like scraper_function does)

### Added Functions

#### `wait_for_scraped_files()`
- Polls GCS for scraped article files
- Timeout: 5 minutes (300 seconds)
- Checks every 5 seconds
- Returns list of file info with paths and article counts

#### `publish_batch_processing_request()`
- Publishes to session-data-created topic
- Creates batch message with success_messages array (all 3 files)
- Follows exact same pattern as scraper_function

### Single vs Multiple Invocations

**Single Invocation (All complete articles):**
- No incomplete articles → no scrapers triggered
- Publishes batch message with only articles.json

**Multiple Invocations (Some incomplete articles):**
- Triggers TR and EU scrapers via Pub/Sub
- Waits for both to complete
- Publishes batch message with all 3 files

### Batch Processing Results Location

```
news_data/api/.../run_XX-XX-XX/
  ├── articles.json
  ├── articles_scraped_tr.json
  ├── articles_scraped_eu.json
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

## 📊 Benefits

1. **Full Content**: No more truncated `[+497 chars]` - all articles have complete text
2. **Unified Schema**: All files use same format - easy to process together
3. **Region Classification**: Articles pre-classified by language (TR/EU)
4. **Quality Improvement**: Uses existing high-quality batch processing pipeline
5. **Backwards Compatible**: Traditional scraping pipeline unchanged

---

## 🔧 Modified Files

### news_api_fetcher_function
1. `news_aggregator.py` - Added detection functions:
   - `is_content_complete()`: Detects truncated content
   - `classify_region()`: Classifies articles by language (TR/EU)

2. `main.py` - Added complete integration:
   - `generate_article_id()`: Generate MD5-based article IDs
   - `transform_api_article_to_session_schema()`: Transform API → session schema
   - `trigger_scraper_for_incomplete_articles()`: Trigger scrapers via Pub/Sub
   - `wait_for_scraped_files()`: Poll GCS for scraper completion
   - `publish_batch_processing_request()`: Publish to session-data-created
   - Modified `fetch_and_store_news()`: Added orchestration logic

### scraper_function
1. `main.py` - Added API integration mode:
   - Detects `api_run_path` parameter
   - Merges all sessions into single file per region
   - Outputs to custom path (articles_scraped_{region}.json)
   - Skips normal batch processing (news_api_fetcher handles it)

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

## 🐛 Known Limitations

1. **No Retry Mechanism**: If TR or EU scraper fails, no automatic retry
2. **Timeout Fixed at 5 Minutes**: May need adjustment based on scraping load
3. **Phase 6 Not Implemented**: Final enriched_articles.json not yet created

---

## 🚀 Testing Checklist

- [ ] Test content completeness detection with real API responses
- [ ] Test region classification (TR vs EU)
- [ ] Test scraper triggering via Pub/Sub
- [ ] Test schema consistency across all files
- [ ] Test batch processing integration (Phase 5)
- [ ] Test end-to-end flow with real data

---

## 📝 Notes

- **Scrape Depth**: Using `scrape_depth=0` for incomplete articles (no link discovery)
- **Deduplication**: Cross-run deduplication already implemented
- **Pub/Sub Topic**: Uses existing `scraping-requests` topic
- **Region-Specific Files**: Prevents race conditions when TR and EU scrapers run in parallel
