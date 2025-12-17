# Result Merger Function Investigation Report

## Executive Summary

### What is result_merger_function?

The `result_merger_function` is a critical component in the batch processing pipeline that:

1. **Merges Multiple Candidates**: Takes predictions from Stage 1 (extraction) where each source has 2 candidates (different AI responses)
2. **Combines Articles**: Merges all articles from both candidates into a single dataset per source
3. **Triggers Deduplication**: Creates and submits a Stage 2 batch job to deduplicate the merged articles
4. **Tracks Metadata**: Adds merge metadata to each article to track which candidate it came from

### Benefits

**Quality Improvement through Diversity**:
- Stage 1 uses 2 candidates per source (different AI responses for quality)
- Each candidate might extract different articles or miss some
- Merging ensures we capture the maximum number of articles from both attempts

**Data Consolidation**:
- Before merge: 141 articles across 8 sources
- After merge+dedup: 68 articles
- Reduction: 73 articles (51.8%) removed as duplicates

## Per-Source Analysis

| Source | Candidates | Before Merge | After Merge+Dedup | Reduction | Reduction % |
|--------|-----------|--------------|-------------------|-----------|-------------|
| ajansspor_com | 2 | 16 | 8 | 8 | 50.0% |
| beinsports_com_tr | 2 | 6 | 3 | 3 | 50.0% |
| www_aspor_com_tr | 2 | 33 | 16 | 17 | 51.5% |
| www_fanatik_com_tr | 2 | 32 | 14 | 18 | 56.2% |
| www_fotospor_com | 2 | 28 | 14 | 14 | 50.0% |
| www_ntvspor_net | 2 | 18 | 9 | 9 | 50.0% |
| www_skorgazetesi_com | 2 | 8 | 4 | 4 | 50.0% |
| www_trtspor_com_tr | 2 | 0 | 0 | 0 | 0.0% |

## Candidate Comparison (Stage 1)

Comparison of articles extracted by different candidates for the same source:

### beinsports_com_tr

- **Number of candidates**: 2
- **Article counts**: [3, 3]
- **Common articles**: 3
- **Variance**: 0 articles (0.0%)

**Unique articles per candidate**:

- **candidate_0**: 0 unique articles
- **candidate_1**: 0 unique articles

### www_fanatik_com_tr

- **Number of candidates**: 2
- **Article counts**: [18, 14]
- **Common articles**: 14
- **Variance**: 4 articles (22.2%)

**Unique articles per candidate**:

- **candidate_0**: 4 unique articles
  - Examples:
    - Konyaspor, Fenerbahçe'ye hazır...
    - Fenerbahçe, Konyaspor'a hazır!...
    - Kazanç kazançtır...
- **candidate_1**: 0 unique articles

### www_fotospor_com

- **Number of candidates**: 2
- **Article counts**: [14, 14]
- **Common articles**: 14
- **Variance**: 0 articles (0.0%)

**Unique articles per candidate**:

- **candidate_0**: 0 unique articles
- **candidate_1**: 0 unique articles

### www_trtspor_com_tr

- **Number of candidates**: 2
- **Article counts**: [0, 0]
- **Common articles**: 0
- **Variance**: 0 articles (0.0%)

**Unique articles per candidate**:

- **candidate_0**: 0 unique articles
- **candidate_1**: 0 unique articles

### ajansspor_com

- **Number of candidates**: 2
- **Article counts**: [8, 8]
- **Common articles**: 8
- **Variance**: 0 articles (0.0%)

**Unique articles per candidate**:

- **candidate_0**: 0 unique articles
- **candidate_1**: 0 unique articles

### www_ntvspor_net

- **Number of candidates**: 2
- **Article counts**: [9, 9]
- **Common articles**: 9
- **Variance**: 0 articles (0.0%)

**Unique articles per candidate**:

- **candidate_0**: 0 unique articles
- **candidate_1**: 0 unique articles

### www_aspor_com_tr

- **Number of candidates**: 2
- **Article counts**: [16, 17]
- **Common articles**: 14
- **Variance**: 1 articles (5.9%)

**Unique articles per candidate**:

- **candidate_0**: 2 unique articles
  - Examples:
    - Antalyaspor-Galatasaray maçı sonrası flaş eleştiri: Ocak ayı...
    - Usta yorumcudan flaş Icardi iddiası: O teklifi kabul etti! -...
- **candidate_1**: 3 unique articles
  - Examples:
    - Spor yazarları Hesap.com Antalyaspor-Galatasaray maçını değe...
    - TRANSFER HABERİ: Fenerbahçe Sörloth'u böyle ikna edecek!...
    - Fenerbahçe Beko-Anadolu Efes maçı izle: Ne zaman ve hangi ka...

### www_skorgazetesi_com

- **Number of candidates**: 2
- **Article counts**: [4, 4]
- **Common articles**: 4
- **Variance**: 0 articles (0.0%)

**Unique articles per candidate**:

- **candidate_0**: 0 unique articles
- **candidate_1**: 0 unique articles

## Necessity Analysis

### Is result_merger_function necessary?

**YES** - The merger function is necessary for:

1. **Maximizing Article Coverage**: 2/8 sources had different article counts between candidates
2. **Quality Improvement**: Using 2 candidates catches articles that one might miss
3. **Deduplication**: The 51.8% reduction shows significant duplicate removal
4. **Pipeline Automation**: Automatically triggers Stage 2 deduplication

### Alternative Approach

**Could we use only 1 candidate in Stage 1?**

Pros:
- Simpler pipeline (no merge needed)
- Lower cost (half the API calls)
- Faster processing

Cons:
- Might miss articles that only one candidate extracts
- Lower quality due to lack of redundancy
- Single point of failure (if one candidate fails, lose all data)

**Recommendation**: Keep result_merger_function for quality, but could consider:
- Reducing to 1 candidate if cost is a concern
- Using 3 candidates for even higher quality (but more expensive)

