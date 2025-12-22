# Pipeline Tester Agent Manual

Comprehensive guide for analyzing, debugging, and validating AISports news ingestion pipeline runs.

## Table of Contents

1. [Project Overview](#project-overview)
2. [Pipeline Architecture](#pipeline-architecture)
3. [Downloading Runs](#downloading-runs)
4. [I/O Consistency Analysis](#io-consistency-analysis)
5. [Deduplication Verification](#deduplication-verification)
6. [Merge Decider Analysis](#merge-decider-analysis)
7. [Debugging Common Issues](#debugging-common-issues)
8. [Utility Scripts](#utility-scripts)
9. [GCS Commands Reference](#gcs-commands-reference)
10. [Cloud Function Logs](#cloud-function-logs)

---

## Project Overview

### Repository Structure

```
/home/neo/aisports/aisports-functions/
├── news_api_fetcher_function/    # Fetches from NewsAPI, GNews, WorldNewsAPI
├── scraper_function/             # Scrapes incomplete articles using journalist lib
├── article_processor_function/   # Embeds + deduplicates + groups articles
├── merge_decider_function/       # LLM decides MERGE vs KEEP_BOTH for groups
├── article_enricher_function/    # LLM generates summary, X post, translation
├── jsonl_transformer_function/   # Processes batch predictions
├── utils/                        # Helper scripts for testing/debugging
│   ├── download_run.py           # Download GCS run to local
│   ├── count_batch_articles.py   # Count input/output articles
│   ├── inspect_predictions.py    # Analyze LLM predictions
│   └── visualize_gcs_tree.py     # Show GCS folder structure
└── README.md                     # Full architecture documentation
```

### Local Workspace

```
/home/neo/aisports/
├── aisports-functions/           # Cloud functions source code
├── pipeline_runs/                # Downloaded GCS runs for local analysis
│   ├── 08-40-17/                 # Run ID (HH-MM-SS format)
│   ├── 15-17-02/
│   └── ...
└── journalist/                   # Scraper library (journ4list)
```

---

## Pipeline Architecture

### Data Flow (API-Triggered Run)

```
news_api_fetcher_function
         │
         ├── complete_articles.json        (full body from API)
         └── to_scrape.json                (incomplete, needs scraping)
                    │
                    ▼
         scraper_function
                    │
                    ▼
         scraped_incomplete_articles.json
                    │
         ┌─────────┴─────────┐
         ▼                   ▼
article_processor_function   article_processor_function
(complete)                   (scraped_incomplete)
         │                   │
    ┌────┴────┐         ┌────┴────┐
    ▼         ▼         ▼         ▼
singleton   grouped   singleton   grouped
    │         │         │         │
    │    merge_decider  │    merge_decider
    │         │         │         │
    ▼         ▼         ▼         ▼
article_enricher_function (combines all)
         │
         ▼
enriched_complete_articles.json
enriched_scraped_incomplete_articles.json
```

### Key Files Per Run

| File | Description |
|------|-------------|
| `metadata.json` | Run metadata: keywords, counts, trigger info |
| `responses/*.json` | Raw API responses (gnews, newsapi, worldnewsapi) |
| `complete_articles.json` | Articles with full body from API |
| `to_scrape.json` | Articles needing scraping (incomplete body) |
| `scraped_incomplete_articles.json` | Scraped versions of incomplete articles |
| `processing_metadata_*.json` | Dedup/grouping stats |
| `embeddings/*.json` | Vector embeddings per article |
| `singleton_*.json` | Articles not grouped (unique) |
| `grouped_*.json` | Similar articles grouped together |
| `decision_*.json` | Articles after merge decisions |
| `enriched_*.json` | **Final output** consumed by UI |

---

## Downloading Runs

### Using download_run.py

```bash
python /home/neo/aisports/aisports-functions/utils/download_run.py \
    aisports-scraping/ingestion/2025-12-22/08-40-17
```

**Default local directory**: `/home/neo/aisports/pipeline_runs/`

**Options**:
- `--local_dir <path>`: Custom download location
- `--skip-existing` or `-s`: Skip files already downloaded

### Manual GCS Download

```bash
gsutil -m cp -r gs://aisports-scraping/ingestion/2025-12-22/08-40-17 \
    /home/neo/aisports/pipeline_runs/
```

---

## I/O Consistency Analysis

Verify article counts are consistent across pipeline stages.

### Quick Analysis Script

```python
import json
import os

RUN_DIR = "/home/neo/aisports/pipeline_runs/08-40-17"

def count_articles(filepath):
    with open(filepath) as f:
        data = json.load(f)
        if "articles" in data:
            return len(data["articles"])
        elif "groups" in data:
            return sum(len(g.get("articles", [])) for g in data["groups"])
    return 0

files = [
    "complete_articles.json",
    "scraped_incomplete_articles.json",
    "singleton_complete_articles.json",
    "grouped_complete_articles.json",
    "singleton_scraped_incomplete_articles.json",
    "grouped_scraped_incomplete_articles.json",
    "decision_complete_articles.json",
    "decision_scraped_incomplete_articles.json",
    "enriched_complete_articles.json",
    "enriched_scraped_incomplete_articles.json",
]

for f in files:
    path = os.path.join(RUN_DIR, f)
    if os.path.exists(path):
        print(f"{f}: {count_articles(path)}")
```

### Expected Flow

```
STAGE 1: API Responses
   gnews.json + newsapi.json + worldnewsapi.json → TOTAL

STAGE 2: Initial Split
   complete_articles + to_scrape = TOTAL

STAGE 3: After Scraping
   scraped_incomplete ≤ to_scrape (some may fail)

STAGE 4: Embedding Deduplication
   Check processing_metadata_*.json for:
   - prefilter_removed (near-identical)
   - cross_run_removed (seen in previous runs)

STAGE 5: Grouping
   singleton + grouped = articles_after_dedup

STAGE 6: Merge Decisions
   decision articles ≤ grouped + singleton

STAGE 7: Final Enriched
   enriched_complete + enriched_scraped_incomplete = FINAL TOTAL
```

### Processing Metadata Keys

```python
with open("processing_metadata_complete.json") as f:
    meta = json.load(f)
    print(f"Input: {meta['total_input_articles']}")
    print(f"Prefilter removed: {meta['prefilter_removed']}")
    print(f"Cross-run removed: {meta['cross_run_removed']}")
    print(f"After dedup: {meta['articles_after_dedup']}")
    print(f"Singletons: {meta['singleton_count']}")
    print(f"Groups: {meta['group_count']} ({meta['grouped_article_count']} articles)")
```

---

## Deduplication Verification

### Thresholds

| Threshold | Value | Purpose |
|-----------|-------|---------|
| Cross-run dedup | 0.7 | Drop if similar to previous run |
| Within-run grouping | 0.8 | Group for merge decision |

### Check Embeddings

```python
with open("embeddings/complete_embeddings.json") as f:
    data = json.load(f)
    print(f"Embeddings count: {len(data.get('embeddings', []))}")
```

### Verify No False Positives

If articles are unexpectedly dropped, check similarity scores in the processing pipeline logs.

---

## Merge Decider Analysis

### Check Grouping

```python
with open("grouped_complete_articles.json") as f:
    data = json.load(f)
    for i, group in enumerate(data.get("groups", [])):
        print(f"Group {i+1}: {len(group['articles'])} articles")
        for art in group['articles']:
            print(f"  - {art.get('source')}: {art.get('title')[:50]}...")
```

### Check Merge Decisions

```python
# Read batch prediction output
with open("batch_merge/complete/prediction-model-*/predictions.jsonl") as f:
    for line in f:
        pred = json.loads(line)
        response = pred.get("response", {})
        candidates = response.get("candidates", [{}])
        if candidates:
            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            print(text[:300])  # Shows decision JSON
```

### Expected Decisions

- `MERGE`: Combine duplicate articles into one
- `KEEP_BOTH`: Similar but distinct (different angles, different info)

---

## Debugging Common Issues

### Issue: TR Region Articles Missing publish_date

**Symptom**: hurriyet, spor.haber7, sabah articles show NaN in UI, but aktifhaber works.

**Cause**: Scraper wasn't preserving `publish_date` from original `to_scrape.json`.

**Check**:
```python
# Compare to_scrape vs scraped_incomplete
with open("to_scrape.json") as f:
    to_scrape = json.load(f)
with open("scraped_incomplete_articles.json") as f:
    scraped = json.load(f)

# Find matching article
for orig in to_scrape["articles"]:
    for scr in scraped["articles"]:
        if orig["url"] == scr.get("url"):
            print(f"Original publish_date: {orig.get('publish_date')}")
            print(f"Scraped published_at: {scr.get('published_at')}")
```

### Issue: All Articles Marked as "scraped" Instead of "api"

**Symptom**: `source_type: "scraped"` even for API-originated articles.

**Cause**: `source_type` not preserved through scraping pipeline.

**Check**:
```python
# Check source_type in final output
with open("enriched_complete_articles.json") as f:
    data = json.load(f)
    for art in data["articles"]:
        print(f"{art['source']}: source_type={art.get('source_type')}")
```

### Issue: Data Loss in Enrichment

**Symptom**: Fewer articles in `enriched_*.json` than in `decision_*.json`.

**Check**:
```bash
python /home/neo/aisports/aisports-functions/utils/count_batch_articles.py \
    /home/neo/aisports/pipeline_runs/08-40-17
```

See [BATCH_ARTICLE_ANALYSIS_GUIDE.md](BATCH_ARTICLE_ANALYSIS_GUIDE.md) for detailed analysis.

---

## Utility Scripts

### download_run.py

Download a GCS run folder to local for analysis.

```bash
python utils/download_run.py aisports-scraping/ingestion/2025-12-22/08-40-17
```

### count_batch_articles.py

Count articles in batch input/output files to detect data loss.

```bash
python utils/count_batch_articles.py /home/neo/aisports/pipeline_runs/08-40-17
```

### inspect_predictions.py

Analyze LLM prediction outputs.

### visualize_gcs_tree.py

Show GCS folder structure as a tree.

---

## GCS Commands Reference

### List Run Contents

```bash
gsutil ls gs://aisports-scraping/ingestion/2025-12-22/08-40-17/
```

### Read Metadata

```bash
gsutil cat gs://aisports-scraping/ingestion/2025-12-22/08-40-17/metadata.json | python3 -m json.tool
```

### Check File Exists

```bash
gsutil stat gs://aisports-scraping/ingestion/2025-12-22/08-40-17/complete_articles.json
```

### List Recent Runs

```bash
gsutil ls gs://aisports-scraping/ingestion/2025-12-22/ | sort | tail -5
```

---

## Cloud Function Logs

### Check news_api_fetcher Logs

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="news-api-fetcher-function"' \
  --limit=50 \
  --format="table(timestamp,severity,textPayload)" \
  --project=gen-lang-client-0306766464
```

### Check Scraper Logs

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="scraper-function"' \
  --limit=50 \
  --format="table(timestamp,severity,textPayload)" \
  --project=gen-lang-client-0306766464
```

### Filter for Errors Only

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND severity>=ERROR' \
  --limit=30 \
  --format="table(timestamp,resource.labels.service_name,textPayload)" \
  --project=gen-lang-client-0306766464
```

### Filter by Run Time

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND timestamp>="2025-12-22T08:40:00Z"' \
  --limit=100 \
  --project=gen-lang-client-0306766464
```

---

## Success Criteria Checklist

- [ ] `metadata.json` exists and contains run info
- [ ] API responses present in `responses/` folder
- [ ] `complete_articles.json` has articles
- [ ] If scraping triggered: `scraped_incomplete_articles.json` exists
- [ ] Processing metadata shows no unexpected drops
- [ ] Enriched files have consistent article counts
- [ ] `source_type` correctly set (api vs scraped)
- [ ] `publish_date` populated for all articles
- [ ] No ERROR logs during run timeframe

---

## Quick Inspection Commands

### One-liner to check article counts

```bash
cd /home/neo/aisports/pipeline_runs/08-40-17 && \
for f in *.json; do \
  echo -n "$f: "; \
  python3 -c "import json; d=json.load(open('$f')); print(len(d.get('articles', d.get('groups', []))))" 2>/dev/null || echo "N/A"; \
done
```

### Check extraction methods

```bash
cd /home/neo/aisports/pipeline_runs/08-40-17 && \
python3 -c "
import json
with open('scraped_incomplete_articles.json') as f:
    data = json.load(f)
    methods = {}
    for art in data.get('articles', []):
        m = art.get('extraction_method', 'none')
        methods[m] = methods.get(m, 0) + 1
    for m, c in methods.items():
        print(f'{m}: {c}')
"
```

### Check source_type distribution

```bash
cd /home/neo/aisports/pipeline_runs/08-40-17 && \
python3 -c "
import json
for fname in ['enriched_complete_articles.json', 'enriched_scraped_incomplete_articles.json']:
    try:
        with open(fname) as f:
            data = json.load(f)
            types = {}
            for art in data.get('articles', []):
                t = art.get('source_type', 'none')
                types[t] = types.get(t, 0) + 1
            print(f'{fname}: {types}')
    except: pass
"
```
