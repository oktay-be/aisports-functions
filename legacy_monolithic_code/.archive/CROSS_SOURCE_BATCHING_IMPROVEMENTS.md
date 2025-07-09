# Cross-Source Batching Improvements

## Problem Identified
The initial GCS structure had batch processing at the source level (e.g., `bbc/2025-07/batch_processing/`), which would create separate batches for each source. This leads to:
- Underutilized batches (each source might not reach the 2M word limit)
- Higher costs due to inefficient batch sizing
- More batch jobs than necessary

## Solution Implemented

### 1. **Updated GCS Folder Structure**
- Moved `batch_processing/` to the month level: `news_data/2025-07/batch_processing/`
- Sources remain separate under: `news_data/2025-07/sources/{source}/`
- This allows batches to contain files from multiple sources

### 2. **Cross-Source Orchestrator Flow**
- **Before**: Process each source separately, create source-specific batches
- **After**: Collect articles from ALL sources first, then create optimized cross-source batches

### 3. **Enhanced Batch Manager**
- `create_cross_source_batches()` instead of source-specific batching
- Can mix files from bbc, fotomac, fanatik, sabah in single batches
- Maximizes the 2M word limit efficiency

### 4. **Cross-Source Manifest Files**
- Each batch now tracks source breakdown
- Shows which sources contributed to each batch
- Provides detailed word count analytics per source

## Benefits
1. **Cost Efficiency**: Better utilization of 2M word limit per batch
2. **Fewer Jobs**: Reduced number of batch jobs needed
3. **Scalability**: Easier to add new sources without changing batch logic
4. **Monitoring**: Better visibility into cross-source processing metrics

## Example
**Before**: 
- BBC batch: 800K words (underutilized)
- Fotomac batch: 600K words (underutilized)
- Total: 2 batch jobs, 1.4M words

**After**:
- Combined batch: BBC (800K) + Fotomac (600K) + Fanatik (400K) + Sabah (200K) = 2M words
- Total: 1 batch job, 2M words (fully utilized)

## Implementation Status
✅ **Updated**: GCS folder structure
✅ **Updated**: Implementation plan with cross-source logic
✅ **Updated**: Class signatures and method names
✅ **Updated**: Orchestrator flow to collect all sources first
✅ **Added**: Cross-source manifest structure example
✅ **Added**: Detailed source breakdown in batch metadata

## Next Steps
- Implement the updated code according to the revised plan
- Test cross-source batching with real data
- Validate batch size optimization
