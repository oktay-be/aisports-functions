# Pipeline Tester Agent

Agent for validating that a specific ingestion run completed successfully.

## Input Parameters

- **RUN_ID**: The run timestamp in `HH-MM-SS` format (e.g., `14-15-14`)
- **DATE** (optional): Date in `YYYY-MM-DD` format. Defaults to today.

## GCS Validation Commands

### 1. Check run folder exists
```bash
GOOGLE_APPLICATION_CREDENTIALS=/home/neo/aisports/aisports-functions/news_api_fetcher_function/gen-lang-client-0306766464-99aaf54afa07.json \
gsutil ls gs://aisports-scraping/ingestion/{DATE}/{RUN_ID}/
```

### 2. Verify required files exist
```bash
# Check articles.json
GOOGLE_APPLICATION_CREDENTIALS=/home/neo/aisports/aisports-functions/news_api_fetcher_function/gen-lang-client-0306766464-99aaf54afa07.json \
gsutil stat gs://aisports-scraping/ingestion/{DATE}/{RUN_ID}/articles.json

# Check metadata.json
GOOGLE_APPLICATION_CREDENTIALS=/home/neo/aisports/aisports-functions/news_api_fetcher_function/gen-lang-client-0306766464-99aaf54afa07.json \
gsutil stat gs://aisports-scraping/ingestion/{DATE}/{RUN_ID}/metadata.json
```

### 3. Check API responses folder
```bash
GOOGLE_APPLICATION_CREDENTIALS=/home/neo/aisports/aisports-functions/news_api_fetcher_function/gen-lang-client-0306766464-99aaf54afa07.json \
gsutil ls gs://aisports-scraping/ingestion/{DATE}/{RUN_ID}/responses/
```

Expected files: `gnews.json`, `newsapi.json`, `worldnewsapi.json`

### 4. Check scrape results (if triggered)
```bash
GOOGLE_APPLICATION_CREDENTIALS=/home/neo/aisports/aisports-functions/news_api_fetcher_function/gen-lang-client-0306766464-99aaf54afa07.json \
gsutil ls gs://aisports-scraping/ingestion/{DATE}/{RUN_ID}/scrape_results/
```

### 5. Read metadata for run status
```bash
GOOGLE_APPLICATION_CREDENTIALS=/home/neo/aisports/aisports-functions/news_api_fetcher_function/gen-lang-client-0306766464-99aaf54afa07.json \
gsutil cat gs://aisports-scraping/ingestion/{DATE}/{RUN_ID}/metadata.json | python3 -m json.tool
```

## Cloud Function Log Commands

### 1. Check news_api_fetcher logs
```bash
GOOGLE_APPLICATION_CREDENTIALS=/home/neo/aisports/aisports-functions/news_api_fetcher_function/gen-lang-client-0306766464-99aaf54afa07.json \
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="news-api-fetcher-function" AND timestamp>="{DATE}T{RUN_ID_COLON}:00Z"' \
--limit=100 \
--format="table(timestamp,severity,textPayload)" \
--project=aisports-dev
```

Note: Replace `{RUN_ID_COLON}` with time in `HH:MM:SS` format (e.g., `14:15:14`)

### 2. Check scraper logs
```bash
GOOGLE_APPLICATION_CREDENTIALS=/home/neo/aisports/aisports-functions/news_api_fetcher_function/gen-lang-client-0306766464-99aaf54afa07.json \
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="scraper-function" AND timestamp>="{DATE}T{RUN_ID_COLON}:00Z"' \
--limit=100 \
--format="table(timestamp,severity,textPayload)" \
--project=aisports-dev
```

### 3. Filter for errors only
```bash
GOOGLE_APPLICATION_CREDENTIALS=/home/neo/aisports/aisports-functions/news_api_fetcher_function/gen-lang-client-0306766464-99aaf54afa07.json \
gcloud logging read 'resource.type="cloud_run_revision" AND severity>=ERROR AND timestamp>="{DATE}T{RUN_ID_COLON}:00Z"' \
--limit=50 \
--format="table(timestamp,resource.labels.service_name,textPayload)" \
--project=aisports-dev
```

## Success Criteria Checklist

- [ ] `articles.json` exists and is valid JSON
- [ ] `metadata.json` exists and contains `"status": "success"`
- [ ] `responses/` folder contains at least one API response file
- [ ] No ERROR severity logs during run timeframe
- [ ] If scraping was triggered: `scrape_results/articles_scraped.json` exists

## Sample Invocation

```
Test run 14-15-14 for today (2025-12-19):

1. Check GCS structure:
   gsutil ls gs://aisports-scraping/ingestion/2025-12-19/14-15-14/

2. Read metadata:
   gsutil cat gs://aisports-scraping/ingestion/2025-12-19/14-15-14/metadata.json

3. Check logs for errors:
   gcloud logging read 'resource.type="cloud_run_revision" AND severity>=ERROR AND timestamp>="2025-12-19T14:15:00Z"' --limit=20
```

## Quick Validation Script

```python
# Run this to validate a specific run
import subprocess
import json
from datetime import date

RUN_ID = "14-15-14"  # Change this
DATE = date.today().isoformat()

creds = "/home/neo/aisports/aisports-functions/news_api_fetcher_function/gen-lang-client-0306766464-99aaf54afa07.json"
base_path = f"gs://aisports-scraping/ingestion/{DATE}/{RUN_ID}"

# Check files exist
files_to_check = ["articles.json", "metadata.json"]
for f in files_to_check:
    result = subprocess.run(
        f"GOOGLE_APPLICATION_CREDENTIALS={creds} gsutil stat {base_path}/{f}",
        shell=True, capture_output=True, text=True
    )
    status = "OK" if result.returncode == 0 else "MISSING"
    print(f"{f}: {status}")
```
