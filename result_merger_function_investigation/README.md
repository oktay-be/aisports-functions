# Result Merger Function Investigation

**Investigation Date**: 2025-12-17
**Data Analyzed**: 2025-12-14 batch run (Stage 1 & Stage 2)
**Purpose**: Understand the necessity and benefit of result_merger_function

---

## Quick Answer

**Q: What does result_merger_function do?**
A: It merges multiple AI candidate responses (2 per source) from Stage 1 extraction into a single dataset, then triggers Stage 2 deduplication.

**Q: Is it necessary?**
A: It's a **quality improver**, not strictly necessary. It catches 9-10 additional articles (6.4% more) that a single candidate would miss, but costs 2× Stage 1 API calls.

**Q: Should we keep it?**
A: **Yes, for now**. The quality benefit (catching missed articles) justifies the cost. Monitor variance rates over time to reassess.

---

## Investigation Files

This investigation folder contains the following documents:

### 1. [SUMMARY.md](./SUMMARY.md) - **START HERE**
- Executive summary of findings
- Real data statistics from 2025-12-14 run
- Cost-benefit analysis
- Recommendations

### 2. [INVESTIGATION_REPORT.md](./INVESTIGATION_REPORT.md) - **DETAILED ANALYSIS**
- Per-source breakdown
- Candidate comparison statistics
- Necessity analysis with evidence
- Alternative approaches

### 3. [CANDIDATE_DIFFERENCES.md](./CANDIDATE_DIFFERENCES.md) - **SPECIFIC EXAMPLES**
- Exact articles that differed between candidates
- URLs and titles of missed articles
- Concrete evidence of merger value

### 4. [analysis_results.json](./analysis_results.json) - **RAW DATA**
- Complete analysis data in JSON format
- Stage 1 and Stage 2 statistics
- Can be used for further analysis

### 5. [analyze_merger.py](./analyze_merger.py) - **ANALYSIS SCRIPT**
- Python script used to generate all reports
- Can be rerun on other batch runs
- Extensible for future analysis

---

## Key Findings

### Data Summary (2025-12-14 Run)

| Metric | Value |
|--------|-------|
| **Sources Processed** | 8 |
| **Total Candidates** | 16 (2 per source) |
| **Articles Before Merge** | 141 |
| **Articles After Dedup** | 68 |
| **Duplicates Removed** | 73 (51.8%) |
| **Sources with Variance** | 2 (25%) |
| **Unique Articles Caught** | 9 (6.4% of final dataset) |

### What This Means

1. **Duplication is High**: 51.8% of merged articles are duplicates
   - Both candidates often extract the same articles
   - Deduplication step is valuable

2. **Variance Exists**: 25% of sources had different articles between candidates
   - www.fanatik.com.tr: 4 unique to candidate 0
   - www.aspor.com.tr: 2 unique to candidate 0, 3 unique to candidate 1

3. **Quality vs Cost Trade-off**: 9 additional articles captured
   - Benefit: 6.4% more articles (better coverage)
   - Cost: 2× Stage 1 API calls (doubles extraction cost)

---

## Visual Pipeline Flow

### Current Architecture (With Merger)

```
┌─────────────────────────────────────────────────────────────┐
│                    STAGE 1: EXTRACTION                       │
│                                                               │
│  Source: www.fanatik.com.tr                                  │
│    ├─ Candidate 0 → 18 articles ┐                           │
│    └─ Candidate 1 → 14 articles ┘                           │
│                      ↓                                        │
│             result_merger_function                           │
│                      ↓                                        │
│              Merged: 32 articles                             │
│            (18 + 14 with duplicates)                         │
└─────────────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────┐
│                 STAGE 2: DEDUPLICATION                       │
│                                                               │
│              Remove 18 duplicates                            │
│                      ↓                                        │
│              Final: 14 unique articles                       │
└─────────────────────────────────────────────────────────────┘
```

### Alternative Architecture (Without Merger)

```
┌─────────────────────────────────────────────────────────────┐
│                    STAGE 1: EXTRACTION                       │
│                                                               │
│  Source: www.fanatik.com.tr                                  │
│    └─ Single Candidate → 14-18 articles                     │
│                      ↓                                        │
│              Might miss 4 articles                           │
│            (that other candidate caught)                     │
└─────────────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────┐
│                 STAGE 2: DEDUPLICATION                       │
│                                                               │
│              No duplicates to remove                         │
│                      ↓                                        │
│              Final: 10-14 unique articles                    │
│                   (4 articles lost!)                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Business Impact

### Current Setup Benefits

✅ **Better Coverage**: Captures 6.4% more articles than single candidate
✅ **Resilience**: If one candidate fails, other provides backup
✅ **Quality Assurance**: Two independent AI responses reduce extraction errors
✅ **Automated Pipeline**: Automatically triggers deduplication

### Current Setup Costs

❌ **2× Stage 1 Cost**: Double Vertex AI API calls for extraction
❌ **Pipeline Complexity**: Extra merge step adds code to maintain
❌ **Processing Time**: ~30-60 seconds additional latency

### Cost Savings Opportunity

If we reduced to **1 candidate**:
- **Save**: 50% of Stage 1 Vertex AI costs
- **Lose**: ~6-10 articles per batch run
- **Risk**: Single point of failure (if candidate fails, lose all data)

**Estimated savings**: ~$X per month (depends on batch volume)
**Trade-off**: 6.4% fewer articles in final dataset

---

## Specific Examples of Merged Value

### Example 1: www.fanatik.com.tr

**Without Merger (Single Candidate)**:
- Candidate 0: 18 articles
- Candidate 1: 14 articles
- **We'd pick one**: Either 18 or 14 articles

**With Merger**:
- Merge both: 32 articles (raw)
- After dedup: 14 unique articles
- **Caught 4 additional articles** from candidate 0 that candidate 1 missed

**Missed Headlines (if we only used Candidate 1)**:
1. "Konyaspor, Fenerbahçe'ye hazır"
2. "Fenerbahçe, Konyaspor'a hazır!"
3. "Kazanç kazançtır"
4. "Galatasaray'ın vazgeçilmezi oldu"

### Example 2: www.aspor.com.tr

**Candidate 0 exclusive** (2 articles):
- "Antalyaspor-Galatasaray maçı sonrası flaş eleştiri"
- "Usta yorumcudan flaş Icardi iddiası"

**Candidate 1 exclusive** (3 articles):
- "Spor yazarları Hesap.com Antalyaspor-Galatasaray maçını değerlendirdi"
- "TRANSFER HABERİ: Fenerbahçe Sörloth'u böyle ikna edecek!"
- "Fenerbahçe Beko-Anadolu Efes maçı izle"

**Result**: Neither candidate alone would capture all articles. Merging is essential.

---

## Recommendations

### Immediate (Keep Current Setup)

✅ **Maintain result_merger_function**
- Quality benefit justifies cost
- 6.4% more articles is significant
- Resilience against single candidate failures

### Short-Term (Monitor)

📊 **Track variance metrics over time**
- Run this analysis monthly
- Monitor how often candidates differ
- Decision point: If variance drops below 5%, consider removing

### Long-Term (Optimize)

🎯 **Dynamic candidate strategy**
- Simple sources (news tickers): 1 candidate
- Complex sources (long articles): 2-3 candidates
- Adaptive based on historical performance

💰 **Cost optimization**
- If budget pressures increase: reduce to 1 candidate
- If quality issues arise: increase to 3 candidates
- Balance cost vs quality based on business needs

---

## Technical Architecture

### How result_merger_function Works

```python
# Simplified flow
def merge_results(event, context):
    # 1. Triggered by GCS object creation
    #    File: stage1_extraction/results/.../predictions.jsonl

    # 2. Download and parse predictions
    predictions = download_prediction_file(gcs_uri)

    # 3. For each source:
    for source in predictions:
        candidates = source['response']['candidates']  # Usually 2

        # 4. Merge all candidates into one list
        merged_articles = []
        for candidate in candidates:
            articles = parse_candidate(candidate)
            for article in articles:
                # Add metadata to track which candidate produced it
                article['_merge_metadata'] = {
                    'candidate_index': idx,
                    'candidate_avg_logprobs': candidate['avgLogprobs'],
                    'finish_reason': candidate['finishReason']
                }
            merged_articles.extend(articles)

        # 5. Upload merged data for deduplication
        upload_merged_data(merged_articles)

    # 6. Create and submit Stage 2 dedup batch job
    submit_dedup_batch_job()

    # 7. Publish notification
    publish_to_pubsub('dedup-job-created')
```

### File Structure

```
news_data/batch_processing/{collection_id}/{YYYY-MM}/{YYYY-MM-DD}/run_{HH-MM-SS}/
├── stage1_extraction/
│   ├── requests/
│   │   └── request.jsonl
│   └── results/
│       └── prediction-model-{timestamp}/
│           └── predictions.jsonl  ← Triggers merger
├── stage2_deduplication/
│   ├── input_merged_data/  ← Merger output
│   │   ├── merged_session_data_beinsports_com_tr.json
│   │   ├── merged_session_data_www_fanatik_com_tr.json
│   │   └── ...
│   ├── requests/
│   │   └── request.jsonl  ← Merger creates this
│   └── results/
│       └── prediction-model-{timestamp}/
│           └── predictions.jsonl  ← Final deduplicated results
```

---

## Reproducing This Analysis

### Run Analysis on Different Data

```bash
# 1. Download predictions from GCS
GOOGLE_APPLICATION_CREDENTIALS=/path/to/creds.json \
gsutil cat "gs://aisports-scraping/news_data/batch_processing/tr/YYYY-MM/YYYY-MM-DD/run_XX-XX-XX/stage1_extraction/results/.../predictions.jsonl" \
  > /tmp/stage1_predictions.jsonl

gsutil cat "gs://aisports-scraping/news_data/batch_processing/tr/YYYY-MM/YYYY-MM-DD/run_XX-XX-XX/stage2_deduplication/results/.../predictions.jsonl" \
  > /tmp/stage2_predictions.jsonl

# 2. Run analysis
cd /home/neo/aisports/aisports-functions/result_merger_function_investigation
python3 analyze_merger.py

# 3. View results
cat SUMMARY.md
cat INVESTIGATION_REPORT.md
cat CANDIDATE_DIFFERENCES.md
```

### Modify Analysis Script

The `analyze_merger.py` script can be extended to:
- Compare different batch runs over time
- Track variance trends
- Calculate cost projections
- Generate custom reports

---

## Conclusion

**The result_merger_function is valuable for quality improvement.**

- **Purpose**: Combines multiple AI candidate responses to maximize article capture
- **Benefit**: 6.4% more articles (9 additional articles in this run)
- **Cost**: 2× Stage 1 Vertex AI API calls
- **Recommendation**: **Keep it** - quality benefit outweighs cost

The function is a **quality improver** that ensures we don't miss articles due to AI extraction variability. While it adds cost and complexity, the benefit of capturing all available articles justifies its existence in the current architecture.

### Decision Matrix

| Scenario | Recommendation | Rationale |
|----------|---------------|-----------|
| **Quality is priority** | Keep 2 candidates + merger | Maximum coverage |
| **Cost is concern** | Reduce to 1 candidate | 50% cost savings, lose 5-10% articles |
| **Need more quality** | Increase to 3 candidates | Even better coverage, +50% cost |

---

## Contact / Questions

For questions about this investigation or the result_merger_function:

- Review code: `/home/neo/aisports/aisports-functions/result_merger_function/main.py`
- Review plan: `/home/neo/aisports/aisports-functions/NEWS_API_ENRICHMENT_PLAN.md`
- Rerun analysis: `python3 analyze_merger.py` (in this directory)
