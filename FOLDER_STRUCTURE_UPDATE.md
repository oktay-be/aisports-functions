# Folder Structure Updates - batch_results → batch_results_raw

## Summary

Updated all references from `batch_results/` to `batch_results_raw/` to clearly distinguish between:
- **Raw batch results** (multiple AI candidates) → `batch_results_raw/`
- **Merged results** (candidates combined) → `batch_results_merged/`
- **Deduplicated results** (final output) → `dedup_results/`

## Files Updated

### 1. batch_builder_function/main.py
**Line 246**: Updated output URI path

**Before:**
```python
output_uri = f"gs://{GCS_BUCKET_NAME}/{NEWS_DATA_ROOT_PREFIX}{BATCH_PROCESSING_FOLDER}{current_date_path}/batch_results/{batch_id}/"
```

**After:**
```python
output_uri = f"gs://{GCS_BUCKET_NAME}/{NEWS_DATA_ROOT_PREFIX}{BATCH_PROCESSING_FOLDER}{current_date_path}/batch_results_raw/{batch_id}/"
```

**Impact**: 
- Batch builder now outputs raw Vertex AI predictions to `batch_results_raw/`
- This matches the folder structure expected by result_merger_function

---

### 2. result_merger_function/main.py
**Already updated in previous changes:**
- Line 50-58: Added environment variables for folder structure
- Line 297: Outputs merged data to `batch_results_merged/`
- Line 484: Outputs dedup results to `dedup_results/`
- Line 534-540: Filters to only process files from `batch_results_raw/`

---

### 3. result_merger_function/README.md
**Already updated in previous changes:**
- Environment variables section: Added new folder configuration variables
- GCS Trigger section: Updated pattern to `batch_results_raw/*_predictions.jsonl`
- Output Locations section: Updated all example paths
- Deployment command: Updated trigger pattern and env vars

---

### 4. .github/workflows/deploy-result-merger-function.yml
**Already updated in previous changes:**
- Line 53: Updated trigger pattern to `batch_results_raw/*_predictions.jsonl`
- Line 59: Added new environment variables
- Line 74: Updated output message pattern

---

### 5. result_merger_function/IMPLEMENTATION_SUMMARY.md
**Lines 95, 215, 238, 258**: Updated all path references

**Changes:**
- Architecture diagram: `batch_results/*` → `batch_results_raw/*`
- Trigger configuration: `batch_results/*` → `batch_results_raw/*`
- Deployment command: `batch_results/*` → `batch_results_raw/*`
- Test data path: `batch_results/` → `batch_results_raw/`

---

### 6. result_merger_function/GCS_FOLDER_STRUCTURE.md
**Already created with correct structure:**
- Complete documentation of all three folders
- Clear separation between raw, merged, and deduplicated results
- Data flow diagrams showing processing stages

---

## Updated GCS Path Structure

```
gs://aisports-scraping/news_data/batch_processing/{YYYY-MM}/

├── batch_results_raw/              ← Vertex AI raw predictions (2 candidates)
│   └── {batch_id}/                 ← From batch_builder_function
│       └── prediction-model-{timestamp}/
│           └── predictions.jsonl
│
├── batch_results_merged/           ← Merged candidate results
│   └── batch_{dedup_id}/           ← From result_merger_function
│       └── merged_*.json
│
├── dedup_batch_{dedup_id}/         ← Deduplication requests
│   └── request.jsonl               ← From result_merger_function
│
└── dedup_results/                  ← Final deduplicated articles
    └── {dedup_id}/                 ← From Vertex AI dedup job
        └── prediction-model-{timestamp}/
            └── predictions.jsonl
```

## Pipeline Flow with New Structure

```
1. Scraper Function
   ↓ publishes to session-data-created
   
2. Batch Builder Function
   ↓ creates batch request
   ↓ submits to Vertex AI
   ↓ OUTPUTS TO: batch_results_raw/{batch_id}/
   
3. GCS Event Trigger
   ↓ object.v1.finalized on batch_results_raw/*_predictions.jsonl
   
4. Result Merger Function
   ↓ downloads from: batch_results_raw/
   ↓ merges candidates
   ↓ OUTPUTS TO: batch_results_merged/batch_{dedup_id}/
   ↓ creates dedup request
   ↓ submits to Vertex AI
   ↓ VERTEX AI OUTPUTS TO: dedup_results/{dedup_id}/
   ↓ publishes to dedup-job-created
   
5. (Future) Final Processor
   ↓ processes from: dedup_results/
   ↓ stores to database/BigQuery
```

## Environment Variables Added

### batch_builder_function
No new env vars needed - just path change in code.

### result_merger_function
```bash
BATCH_RESULTS_RAW_FOLDER=batch_results_raw/
BATCH_RESULTS_MERGED_FOLDER=batch_results_merged/
DEDUP_RESULTS_FOLDER=dedup_results/
```

## Migration Notes

### For Existing Data
If you have existing data in `batch_results/`, you can either:

**Option 1: Rename (Recommended)**
```bash
# Rename existing batch_results to batch_results_raw
gsutil -m mv "gs://aisports-scraping/news_data/batch_processing/2025-10/batch_results/*" \
             "gs://aisports-scraping/news_data/batch_processing/2025-10/batch_results_raw/"
```

**Option 2: Keep Both**
```bash
# Leave old data in batch_results/ (won't be processed)
# New data will go to batch_results_raw/ (will be processed)
```

**Option 3: Copy**
```bash
# Copy existing data to new structure
gsutil -m cp -r "gs://aisports-scraping/news_data/batch_processing/2025-10/batch_results/*" \
               "gs://aisports-scraping/news_data/batch_processing/2025-10/batch_results_raw/"
```

### Your Specific Case
Based on your path:
```
https://storage.googleapis.com/aisports-scraping/news_data/batch_processing/2025-10/batch_results/20251025_083721_002/prediction-model-2025-10-25T08:37:21.590419Z/predictions.jsonl
```

You should rename/move:
```bash
gsutil -m mv "gs://aisports-scraping/news_data/batch_processing/2025-10/batch_results/" \
             "gs://aisports-scraping/news_data/batch_processing/2025-10/batch_results_raw/"
```

## Testing Changes

### 1. Test Batch Builder Output
```bash
# Deploy updated batch_builder_function
# Trigger a new batch
# Check output location:
gsutil ls "gs://aisports-scraping/news_data/batch_processing/$(date +%Y-%m)/batch_results_raw/"
```

### 2. Test Result Merger Trigger
```bash
# Wait for Vertex AI to complete a batch job
# Check result_merger_function logs:
gcloud functions logs read result-merger-function --region=us-central1 --limit=50

# Verify merged output:
gsutil ls "gs://aisports-scraping/news_data/batch_processing/$(date +%Y-%m)/batch_results_merged/"
```

### 3. Test End-to-End
```bash
# 1. Trigger scraper
# 2. Wait for batch_builder to create job
# 3. Wait for Vertex AI to complete → writes to batch_results_raw/
# 4. Result merger auto-triggers → reads from batch_results_raw/
# 5. Result merger outputs to batch_results_merged/
# 6. Result merger submits dedup job → Vertex AI writes to dedup_results/
```

## Verification Checklist

- [x] ✅ batch_builder_function/main.py updated (line 246)
- [x] ✅ result_merger_function/main.py updated (env vars, paths, filters)
- [x] ✅ result_merger_function/README.md updated
- [x] ✅ .github/workflows/deploy-result-merger-function.yml updated
- [x] ✅ result_merger_function/IMPLEMENTATION_SUMMARY.md updated
- [x] ✅ result_merger_function/GCS_FOLDER_STRUCTURE.md created
- [x] ✅ All path references consistent

## Deployment Order

1. **Deploy batch_builder_function** (updated output path)
   ```bash
   git add batch_builder_function/main.py
   git commit -m "Update batch_builder to output to batch_results_raw/"
   git push
   ```

2. **Deploy result_merger_function** (updated trigger and paths)
   ```bash
   git add result_merger_function/
   git commit -m "Update result_merger folder structure and triggers"
   git push
   ```

3. **Update GCS event trigger** (if manually configured)
   ```bash
   # Re-deploy result-merger-function to update trigger pattern
   # GitHub Actions will handle this automatically
   ```

4. **(Optional) Migrate existing data**
   ```bash
   # Rename old batch_results to batch_results_raw
   gsutil -m mv "gs://aisports-scraping/news_data/batch_processing/2025-10/batch_results/" \
                "gs://aisports-scraping/news_data/batch_processing/2025-10/batch_results_raw/"
   ```

## Benefits of New Structure

✅ **Clear Separation**: Each processing stage has its own folder  
✅ **Easy Monitoring**: Can track progress through folder structure  
✅ **Prevents Confusion**: No ambiguity about data state  
✅ **Event-Driven**: GCS triggers only fire on correct files  
✅ **Scalable**: Each stage independent, can process in parallel  
✅ **Traceable**: Full lineage from raw → merged → deduplicated  

## Notes

- The old `batch_results/` folder won't interfere with new processing
- Result merger will ONLY trigger on `batch_results_raw/` files
- All new batches will use the new structure automatically
- Old data can coexist without issues (just won't be processed)
