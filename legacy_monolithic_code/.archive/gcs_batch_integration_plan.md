# GCS Batch Integration Implementation Plan
**Using Vertex AI Native Batch Processing with Cross-Source Batching**

## Executive Summary

This plan outlines the complete implementation of a GCS-based news processing pipeline using **Vertex AI's native batch processing** with **cross-source batching optimization**. This approach provides 50% cost savings, automatic scaling, and maximizes batch efficiency by combining articles from multiple sources (bbc, fotomac, fanatik, sabah) within the 2M word limit.

## Key Changes from Previous Plan

### ❌ **REMOVED**: Manual Asyncio Multi-Threading
- No more `asyncio.create_task()` and `asyncio.gather()`
- No more manual retry logic and rate limiting
- No more sequential batch processing

### ✅ **NEW**: Vertex AI Native Batch Processing
- Use `client.batches.create()` for batch job submission
- Automatic scaling and parallelization by Google
- 50% cost reduction compared to synchronous calls
- Built-in retry and error handling

### ✅ **NEW**: Cross-Source Batching Strategy
- **Problem**: Processing each source separately leads to underutilized batches
- **Solution**: Combine articles from multiple sources (bbc, fotomac, fanatik, sabah) into single batches
- **Benefit**: Maximize the 2M word limit per batch for better cost efficiency
- **Implementation**: Collect all diff files first, then create batches across sources

## Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Multi-Source  │    │ Cross-Source     │    │  Vertex AI      │
│   Scraping      │───▶│ Diff & Batch     │───▶│  Batch Jobs     │
│   (eu/tr)       │    │ Preparation      │    │  (Optimized)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                         │
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Metadata      │◀───│   Result         │◀───│  Batch Results  │
│   Updates       │    │   Processing     │    │  from GCS       │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## GCS Folder Structure

```
news_data/
├── sources/
│   ├── bbc/
│   │   ├── 2025-07/
│   │   │   ├── articles/
│   │   │   │   ├── session_data_bbc_com_uk_001.json
│   │   │   │   ├── session_data_bbc_com_uk_002.json
│   │   │   │   └── ...
│   │   │   ├── embeddings/
│   │   │   │   ├── session_data_bbc_com_uk_001.npy
│   │   │   │   ├── session_data_bbc_com_uk_002.npy
│   │   │   │   └── ...
│   │   │   ├── summaries/
│   │   │   │   ├── ai_summarized_session_data_bbc_com_uk_001.json
│   │   │   │   ├── ai_summarized_session_data_bbc_com_uk_002.json
│   │   │   │   └── ...
│   │   │   ├── clusters/
│   │   │   │   ├── cluster_001.json
│   │   │   │   └── ...
│   │   │   └── metadata/
│   │   │       ├── manifest.csv
│   │   │       └── processing_log.txt
│   │   └── ...
│   ├── fotomac/
│   │   ├── 2025-07/
│   │   │   ├── articles/
│   │   │   │   ├── session_data_fotomac_com_tr_001.json
│   │   │   │   ├── session_data_fotomac_com_tr_002.json
│   │   │   │   └── ...
│   │   │   ├── summaries/
│   │   │   │   ├── ai_summarized_session_data_fotomac_com_tr_001.json
│   │   │   │   ├── ai_summarized_session_data_fotomac_com_tr_002.json
│   │   │   │   └── ...
│   │   │   ├── clusters/
│   │   │   │   ├── cluster_001.json
│   │   │   │   └── ...
│   │   │   └── metadata/
│   │   │       ├── manifest.csv
│   │   │       └── processing_log.txt
│   │   └── ...
│   ├── fanatik/
│   │   ├── 2025-07/
│   │   │   ├── articles/
│   │   │   │   ├── session_data_fanatik_com_tr_001.json
│   │   │   │   └── ...
│   │   │   ├── summaries/
│   │   │   │   ├── ai_summarized_session_data_fanatik_com_tr_001.json
│   │   │   │   └── ...
│   │   │   └── metadata/
│   │   │       ├── manifest.csv
│   │   │       └── processing_log.txt
│   │   └── ...
│   └── sabah/
│       ├── 2025-07/
│       │   ├── articles/
│       │   │   ├── session_data_sabah_com_tr_001.json
│       │   │   └── ...
│       │   ├── summaries/
│       │   │   ├── ai_summarized_session_data_sabah_com_tr_001.json
│       │   │   └── ...
│       │   └── metadata/
│       │       ├── manifest.csv
│       │       └── processing_log.txt
│       └── ...
├── batch_processing/
│   ├── 2025-07/
│   │   ├── batch_20250708_140530_001/
│   │   │   ├── request.jsonl
│   │   │   ├── response.jsonl
│   │   │   ├── job_metadata.json
│   │   │   └── source_files_manifest.json
│   │   ├── batch_20250708_140530_002/
│   │   │   ├── request.jsonl
│   │   │   ├── response.jsonl
│   │   │   ├── job_metadata.json
│   │   │   └── source_files_manifest.json
│   │   └── batch_jobs_log.json
│   └── ...
├── processing_runs/
│   ├── run_20250708_140530/
│   │   ├── run_metadata.json
│   │   ├── processing_summary.json
│   │   ├── error_log.txt
│   │   └── performance_metrics.json
│   └── ...
└── global_metadata/
    ├── all_sources_manifest.csv
    ├── daily_processing_log.txt
    └── pipeline_config.json
```

### Cross-Source Batch Manifest Example

Each batch folder contains a `source_files_manifest.json` that tracks which sources are included:

```json
{
  "batch_id": "batch_20250708_140530_001",
  "created_at": "2025-07-08T14:05:30Z",
  "total_files": 15,
  "total_word_count": 1950000,
  "sources_breakdown": {
    "bbc": {
      "file_count": 6,
      "word_count": 820000,
      "files": [
        "gs://bucket/news_data/sources/bbc/2025-07/articles/session_001.json",
        "gs://bucket/news_data/sources/bbc/2025-07/articles/session_002.json"
      ]
    },
    "fotomac": {
      "file_count": 4,
      "word_count": 610000,
      "files": [
        "gs://bucket/news_data/sources/fotomac/2025-07/articles/session_001.json",
        "gs://bucket/news_data/sources/fotomac/2025-07/articles/session_002.json"
      ]
    },
    "fanatik": {
      "file_count": 3,
      "word_count": 340000,
      "files": [
        "gs://bucket/news_data/sources/fanatik/2025-07/articles/session_001.json"
      ]
    },
    "sabah": {
      "file_count": 2,
      "word_count": 180000,
      "files": [
        "gs://bucket/news_data/sources/sabah/2025-07/articles/session_001.json"
      ]
    }
  }
}
```

## Implementation Components

### 1. Core Utilities

#### 1.1 GCS Folder Manager
**File**: `utils/gcs_folder_manager.py`

```python
class GCSFolderManager:
    """Manages GCS folder structure and file operations"""
    
    def __init__(self, bucket_name: str, project_id: str)
    def create_source_folder_structure(self, source_domain: str, year_month: str) -> str
    def get_next_session_number(self, source_domain: str, year_month: str) -> int
    def upload_session_data(self, session_data: Dict, source_domain: str, session_number: int) -> str
    def list_existing_sessions(self, source_domain: str, year_month: str) -> List[str]
    def download_session_data(self, gcs_uri: str) -> Dict[str, Any]
    
    # Batch processing folder management
    def create_batch_folder(self, batch_id: str, year_month: str) -> str
    def upload_batch_request(self, requests: List[Dict], batch_id: str, year_month: str) -> str
    def download_batch_results(self, batch_id: str, year_month: str) -> List[Dict]
    def save_batch_metadata(self, metadata: Dict, batch_id: str, year_month: str) -> str
    
    # Processing run management
    def create_processing_run_folder(self, run_id: str) -> str
    def save_run_metadata(self, metadata: Dict, run_id: str) -> str
    def save_processing_summary(self, summary: Dict, run_id: str) -> str
    def update_global_manifest(self, processing_results: List[Dict]) -> None
```

#### 1.2 Session Diff Calculator
**File**: `utils/session_diff_calculator.py`

```python
class SessionDiffCalculator:
    """Calculates differences between session data files"""
    
    def __init__(self, gcs_manager: GCSFolderManager)
    def calculate_diff(self, new_session: Dict, source_domain: str) -> Dict[str, Any]
    def find_latest_session(self, source_domain: str, current_date: str) -> Optional[str]
    def _compare_articles(self, new_articles: List, existing_articles: List) -> List[Dict]
    def _generate_diff_session(self, diff_articles: List, metadata: Dict) -> Dict[str, Any]
```

#### 1.3 Word Counter and Batch Manager
**File**: `utils/batch_word_manager.py`

```python
class WordCounter:
    """Counts words in session data files"""
    
    @staticmethod
    def count_words_in_session(session_data: Dict[str, Any]) -> int
    @staticmethod
    def count_words_in_gcs_file(gcs_uri: str, gcs_manager: GCSFolderManager) -> int
    @staticmethod
    def estimate_token_count(word_count: int) -> int  # ~1.3 tokens per word

class BatchManager:
    """Creates cross-source batches of GCS files under 2M word limit"""
    
    def __init__(self, max_words: int = 2_000_000)
    def create_cross_source_batches(self, all_gcs_file_uris: List[str], gcs_manager: GCSFolderManager) -> List[List[str]]
    def _calculate_batch_word_count(self, batch: List[str], gcs_manager: GCSFolderManager) -> int
    def validate_batch_size(self, batch: List[str], gcs_manager: GCSFolderManager) -> bool
    def _extract_source_from_uri(self, gcs_uri: str) -> str
    def _get_batch_source_breakdown(self, batch: List[str]) -> Dict[str, List[str]]
```

### 2. Vertex AI Batch Processing System

#### 2.1 Batch Request Generator
**File**: `capabilities/batch_request_generator.py`

```python
class BatchRequestGenerator:
    """Generates JSONL batch request files for Vertex AI"""
    
    def __init__(self, gcs_manager: GCSFolderManager, prompt_template: str)
    def create_batch_request_file(self, gcs_file_batch: List[str], batch_id: str, year_month: str) -> str
    def _generate_single_request(self, gcs_uri: str) -> Dict[str, Any]
    def upload_batch_request_to_gcs(self, requests: List[Dict], batch_id: str, year_month: str) -> str
    def _construct_prompt_with_gcs_reference(self, gcs_uri: str) -> str
    def create_source_files_manifest(self, gcs_file_batch: List[str], batch_id: str, year_month: str) -> str
```

#### 2.2 Vertex AI Batch Processor
**File**: `capabilities/vertex_ai_batch_processor.py`

```python
class VertexAIBatchProcessor:
    """Manages Vertex AI batch job submission and monitoring"""
    
    def __init__(self, project_id: str, location: str, model_name: str = "gemini-2.5-pro")
    async def submit_batch_job(self, batch_request_gcs_uri: str, batch_id: str) -> str
    async def monitor_batch_job(self, job_name: str, polling_interval: int = 60) -> Dict[str, Any]
    async def download_batch_results(self, job_result_uri: str) -> List[Dict[str, Any]]
    def _parse_batch_result_line(self, jsonl_line: str) -> Dict[str, Any]
    async def process_single_batch(self, gcs_file_batch: List[str], batch_id: str) -> List[Dict]
```

#### 2.3 Batch Result Processor
**File**: `capabilities/batch_result_processor.py`

```python
class BatchResultProcessor:
    """Processes batch job results and saves summaries to GCS"""
    
    def __init__(self, gcs_manager: GCSFolderManager)
    async def process_batch_results(self, batch_results: List[Dict], batch_id: str) -> Dict[str, Any]
    def _extract_summary_from_result(self, result: Dict) -> Dict[str, Any]
    def _save_summary_to_gcs(self, summary: Dict, source_info: Dict, session_number: int) -> str
    def _update_metadata_files(self, processing_results: List[Dict]) -> None
    def _log_batch_processing_stats(self, batch_id: str, results: List[Dict]) -> None
```

### 3. Main Collection Orchestrator

#### 3.1 GCS Collection Orchestrator
**File**: `integrations/gcs_collection_orchestrator.py`

```python
class GCSCollectionOrchestrator:
    """Main orchestrator for end-to-end GCS-based processing pipeline with cross-source batching"""
    
    def __init__(self, project_id: str, bucket_name: str)    async def run_full_pipeline(self, regions: List[str] = ["eu", "tr"]) -> Dict[str, Any]
    async def _run_cross_source_scraping_phase(self, regions: List[str]) -> Dict[str, List[Dict[str, Any]]]
    async def _run_cross_source_diff_calculation_phase(self, all_sessions: Dict[str, List[Dict]]) -> List[str]
    async def _run_cross_source_batch_processing_phase(self, all_diff_files: List[str]) -> Dict[str, Any]
    async def _run_metadata_update_phase(self, processing_results: Dict) -> None
    def _cleanup_old_files(self, retention_days: int = 30) -> None
```

## Detailed Implementation Flow

### Phase 1: Cross-Source Scraping and GCS Upload

1. **Execute Scraping for All Regions**
   ```python
   # Load search parameters for all regions
   search_params_eu = load_json("search_parameters_eu.json")
   search_params_tr = load_json("search_parameters_tr.json")
   
   # Run journalist scraping for all regions
   all_sessions = {}
   all_sessions["eu"] = await journalist.read(search_params_eu)
   all_sessions["tr"] = await journalist.read(search_params_tr)
   ```

2. **Upload All Sessions to GCS with Proper Structure**
   ```python
   # For each region and session, create proper GCS structure
   all_uploaded_uris = []
   for region, sessions in all_sessions.items():
       for session in sessions:
           source_domain = extract_domain(session["source_domain"])
           session_number = gcs_manager.get_next_session_number(source_domain, "2025-07")
           gcs_uri = gcs_manager.upload_session_data(session, source_domain, session_number)
           all_uploaded_uris.append(gcs_uri)
           # Uploads to: gs://bucket/news_data/sources/{source_domain}/2025-07/articles/
   ```

### Phase 2: Cross-Source Diff Calculation

1. **Calculate Diffs for All Sources**
   ```python
   diff_calculator = SessionDiffCalculator(gcs_manager)
   
   all_diff_uris = []
   for region, sessions in all_sessions.items():
       for session in sessions:
           source_domain = extract_domain(session["source_domain"])
           diff_session = diff_calculator.calculate_diff(session, source_domain)
           
           if diff_session and len(diff_session.get("articles", [])) > 0:
               session_number = gcs_manager.get_next_session_number(source_domain, "2025-07")
               diff_uri = gcs_manager.upload_session_data(diff_session, source_domain, session_number)
               all_diff_uris.append(diff_uri)
   ```

### Phase 3: Cross-Source Vertex AI Batch Processing

1. **Create Cross-Source Word-Counted Batches**
   ```python   batch_manager = BatchManager(max_words=2_000_000)
   # This now creates batches that can include files from multiple sources (bbc, fotomac, fanatik, etc.)
   cross_source_batches = batch_manager.create_cross_source_batches(all_diff_uris, gcs_manager)
   
   # Each batch: ["gs://bucket/sources/bbc/2025-07/articles/session1.json", 
   #             "gs://bucket/sources/fotomac/2025-07/articles/session2.json",
   #             "gs://bucket/sources/fanatik/2025-07/articles/session3.json", ...]
   # Total words per batch < 2M across ALL sources
   ```
   diff_calculator = SessionDiffCalculator(gcs_manager)
   
   diff_sessions = []
   for session_gcs_uri in new_session_uris:
       session_data = gcs_manager.download_session_data(session_gcs_uri)
       diff_result = diff_calculator.calculate_diff(session_data, source_domain)
       
       if diff_result["has_changes"]:
           diff_sessions.append(diff_result["diff_session"])
   ```

2. **Upload Diff Sessions**
   ```python
   diff_gcs_uris = []
   for diff_session in diff_sessions:
       diff_uri = gcs_manager.upload_session_data(diff_session, source_domain, session_number)
       diff_gcs_uris.append(diff_uri)
   ```

### Phase 3: Vertex AI Batch Processing

1. **Create Word-Counted Batches**
   ```python
   batch_manager = BatchManager(max_words=2_000_000)
   batches = batch_manager.create_batches(diff_gcs_uris, gcs_manager)
   
   # Each batch: ["gs://bucket/session1.json", "gs://bucket/session2.json", ...]
   # Total words per batch < 2M
   ```

2. **Generate Cross-Source Batch Request Files**
   ```python
   request_generator = BatchRequestGenerator(gcs_manager, prompt_template)
   
   batch_jobs = []
   for i, cross_source_batch in enumerate(cross_source_batches):
       batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i:03d}"
       request_gcs_uri = request_generator.create_batch_request_file(cross_source_batch, batch_id, "2025-07")
       
       # Create manifest showing which sources are included in this batch
       manifest_uri = request_generator.create_source_files_manifest(cross_source_batch, batch_id, "2025-07")
       
       batch_jobs.append({
           "batch_id": batch_id, 
           "request_uri": request_gcs_uri,
           "manifest_uri": manifest_uri,
           "source_files": cross_source_batch  # Mix of files from different sources
       })
       # Uploads to: gs://bucket/news_data/batch_processing/2025-07/batch_{id}/
   ```

3. **Submit to Vertex AI Batch Processing**
   ```python
   batch_processor = VertexAIBatchProcessor(project_id, location)
   
   submitted_jobs = []
   for job_info in batch_jobs:
       job_name = await batch_processor.submit_batch_job(
           job_info["request_uri"], 
           job_info["batch_id"]
       )
       submitted_jobs.append({"job_name": job_name, **job_info})
   ```

4. **Monitor and Collect Results**
   ```python
   all_results = []
   for job in submitted_jobs:
       # Wait for job completion (up to 24 hours)
       job_result = await batch_processor.monitor_batch_job(job["job_name"])
       
       if job_result["status"] == "SUCCEEDED":
           batch_results = await batch_processor.download_batch_results(
               job_result["output_uri"]
           )
           all_results.extend(batch_results)
   ```

### Phase 4: Result Processing and GCS Storage

1. **Process Batch Results**
   ```python
   result_processor = BatchResultProcessor(gcs_manager)
   
   processing_summary = await result_processor.process_batch_results(
       all_results, 
       batch_id="combined_results"
   )
   ```

2. **Save Summaries to GCS**
   ```python
   # Results automatically saved to:
   # gs://bucket/news_data/{source}/2025-07/summaries/
   #   ai_summarized_session_data_{source}_{number}.json
   ```

3. **Update Metadata**
   ```python
   # Update manifest.csv and processing_log.txt
   result_processor._update_metadata_files(processing_summary)
   ```

## MongoDB Removal Strategy

### Files to Clean Up

1. **Database Client Removal**
   ```python
   # Remove from integrations/collection_orchestrator.py:
   - from database.mongodb_client import MongoDBClient
   - self.db_client initialization
   - All MongoDB save operations
   ```

2. **Configuration Cleanup**
   ```python
   # Remove from .env:
   - MONGODB_URI
   - MONGODB_DATABASE
   - All MongoDB-related env vars
   ```

3. **Dependency Cleanup**
   ```python
   # Remove from requirements.in:
   - motor
   - pymongo
   ```

### Replacement Strategy

```python
# OLD: MongoDB saving
await self.db_client.save_ai_summary_per_source(summary_doc)

# NEW: GCS saving
summary_gcs_uri = await self.gcs_manager.save_summary_to_gcs(
    summary_data=summary_doc,
    source_domain=source_domain,
    session_number=session_number
)
```

## Implementation Schedule

### Week 1: Core Infrastructure
- [ ] Implement `GCSFolderManager`
- [ ] Implement `SessionDiffCalculator`
- [ ] Implement `WordCounter` and `BatchManager`
- [ ] Create unit tests for core utilities

### Week 2: Vertex AI Batch Integration
- [ ] Implement `BatchRequestGenerator`
- [ ] Implement `VertexAIBatchProcessor`
- [ ] Implement `BatchResultProcessor`
- [ ] Test batch job submission and monitoring

### Week 3: End-to-End Pipeline
- [ ] Implement `GCSCollectionOrchestrator`
- [ ] Remove all MongoDB dependencies
- [ ] Create integration tests
- [ ] Performance testing with 2M word batches

### Week 4: Testing and Optimization
- [ ] Load testing with multiple sources
- [ ] Error handling and recovery testing
- [ ] Documentation and deployment guides
- [ ] Cost optimization analysis

## Example Batch Request Format

```jsonl
{"contents": [{"parts": [{"text": "Please process the session data from gs://multi-modal-ai-bucket/news_data/fanatik/2025-07/articles/session_data_fanatik_com_tr_001.json according to the PROMPT.md specifications and return structured JSON."}]}], "config": {"max_output_tokens": 65535, "response_mime_type": "application/json"}}
{"contents": [{"parts": [{"text": "Please process the session data from gs://multi-modal-ai-bucket/news_data/fotomac/2025-07/articles/session_data_fotomac_com_tr_001.json according to the PROMPT.md specifications and return structured JSON."}]}], "config": {"max_output_tokens": 65535, "response_mime_type": "application/json"}}
```

## Testing Strategy

### Unit Tests
- `test_gcs_folder_manager.py`
- `test_session_diff_calculator.py` 
- `test_word_counter.py`
- `test_batch_manager.py`
- `test_batch_request_generator.py`

### Integration Tests
- `test_vertex_ai_batch_processing.py`
- `test_end_to_end_pipeline.py`
- `test_mongodb_removal.py`

### Performance Tests
- Batch processing with 2M word limits
- Cost comparison vs. synchronous API calls
- GCS upload/download performance

## Success Criteria

1. ✅ **Complete MongoDB Removal**: No MongoDB dependencies in codebase
2. ✅ **Functional GCS Structure**: Proper folder hierarchy and file organization
3. ✅ **Accurate Diff Calculation**: Only new/changed articles processed
4. ✅ **Word-Based Batching**: Batches stay under 2M words total
5. ✅ **Vertex AI Batch Integration**: Successful batch job submission and monitoring
6. ✅ **Cost Optimization**: 50% cost reduction using batch processing
7. ✅ **Error Handling**: Robust retry and recovery mechanisms
8. ✅ **End-to-End Pipeline**: Full automation from scraping to summaries
9. ✅ **Performance**: Handle hundreds of sources and thousands of articles
10. ✅ **Maintainability**: Clean, testable, and documented code

## Cost Analysis

### Before (Manual Asyncio)
- Synchronous API calls: $X per 1K tokens
- Manual retry and rate limiting overhead
- Risk of hitting quotas and failed requests

### After (Vertex AI Batch)
- Batch API calls: $X * 0.5 per 1K tokens (**50% savings**)
- Automatic scaling and parallelization
- Built-in retry and error handling
- No quota management needed

## Migration Path

1. **Phase 1**: Implement new GCS infrastructure alongside existing code
2. **Phase 2**: Test batch processing with subset of sources
3. **Phase 3**: Gradually migrate sources from MongoDB to GCS
4. **Phase 4**: Remove MongoDB dependencies completely
5. **Phase 5**: Optimize and scale to full production load

This plan provides a complete roadmap for implementing a cost-effective, scalable, and maintainable GCS-based news processing pipeline using Vertex AI's native batch processing capabilities.
