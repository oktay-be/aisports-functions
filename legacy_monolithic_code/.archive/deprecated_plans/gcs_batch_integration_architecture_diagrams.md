# GCS Batch Integration Architecture Diagrams

## Class Relationship Diagram

```mermaid
classDiagram
    class GCSCollectionOrchestrator {
        +project_id: str
        +bucket_name: str
        +gcs_manager: GCSFolderManager
        +diff_calculator: SessionDiffCalculator
        +batch_manager: BatchManager
        +batch_processor: VertexAIBatchProcessor
        +result_processor: BatchResultProcessor
        
        +run_full_pipeline(regions) Dict
        +_run_scraping_phase(region) List[Dict]
        +_run_diff_calculation_phase(sessions) List[str]
        +_run_batch_processing_phase(gcs_files) Dict
        +_run_metadata_update_phase(results) None
        +_cleanup_old_files(retention_days) None
    }
    
    class GCSFolderManager {
        +bucket_name: str
        +project_id: str
        +storage_client: storage.Client
        
        +create_source_folder_structure(domain, year_month) str
        +get_next_session_number(domain, year_month) int
        +upload_session_data(session, domain, number) str
        +list_existing_sessions(domain, year_month) List[str]
        +download_session_data(gcs_uri) Dict
        +save_summary_to_gcs(summary, domain, number) str
    }
    
    class SessionDiffCalculator {
        +gcs_manager: GCSFolderManager
        
        +calculate_diff(new_session, domain) Dict
        +find_latest_session(domain, date) Optional[str]
        +_compare_articles(new, existing) List[Dict]
        +_generate_diff_session(articles, metadata) Dict
    }
    
    class BatchManager {
        +max_words: int
        +word_counter: WordCounter
        
        +create_batches(gcs_uris, gcs_manager) List[List[str]]
        +_calculate_batch_word_count(batch, gcs_manager) int
        +validate_batch_size(batch, gcs_manager) bool
    }
    
    class WordCounter {
        <<static>>
        +count_words_in_session(session_data) int
        +count_words_in_gcs_file(gcs_uri, gcs_manager) int
        +estimate_token_count(word_count) int
    }
    
    class BatchRequestGenerator {
        +gcs_manager: GCSFolderManager
        +prompt_template: str
        
        +create_batch_request_file(batch, batch_id) str
        +_generate_single_request(gcs_uri) Dict
        +upload_batch_request_to_gcs(requests, batch_id) str
        +_construct_prompt_with_gcs_reference(gcs_uri) str
    }
    
    class VertexAIBatchProcessor {
        +project_id: str
        +location: str
        +model_name: str
        +client: genai.Client
        +request_generator: BatchRequestGenerator
        
        +submit_batch_job(request_uri, batch_id) str
        +monitor_batch_job(job_name, polling_interval) Dict
        +download_batch_results(result_uri) List[Dict]
        +_parse_batch_result_line(jsonl_line) Dict
        +process_single_batch(gcs_batch, batch_id) List[Dict]
    }
    
    class BatchResultProcessor {
        +gcs_manager: GCSFolderManager
        
        +process_batch_results(results, batch_id) Dict
        +_extract_summary_from_result(result) Dict
        +_save_summary_to_gcs(summary, source_info, number) str
        +_update_metadata_files(results) None
        +_log_batch_processing_stats(batch_id, results) None
    }

    %% Relationships
    GCSCollectionOrchestrator --> GCSFolderManager
    GCSCollectionOrchestrator --> SessionDiffCalculator
    GCSCollectionOrchestrator --> BatchManager
    GCSCollectionOrchestrator --> VertexAIBatchProcessor
    GCSCollectionOrchestrator --> BatchResultProcessor
    
    SessionDiffCalculator --> GCSFolderManager
    BatchManager --> WordCounter
    BatchManager --> GCSFolderManager
    
    VertexAIBatchProcessor --> BatchRequestGenerator
    BatchRequestGenerator --> GCSFolderManager
    
    BatchResultProcessor --> GCSFolderManager
```

## Process Flow Diagram

```mermaid
flowchart TD
    Start([Start Full Pipeline]) --> LoadParams[Load search_parameters_eu.json<br/>search_parameters_tr.json]
    
    LoadParams --> Scraping{Run Scraping for<br/>Each Region}
    Scraping --> ScrapeEU[Journalist.read<br/>EU sources]
    Scraping --> ScrapeTR[Journalist.read<br/>TR sources]
    
    ScrapeEU --> UploadEU[GCSFolderManager<br/>upload_session_data]
    ScrapeTR --> UploadTR[GCSFolderManager<br/>upload_session_data]
    
    UploadEU --> DiffCalc[SessionDiffCalculator<br/>calculate_diff]
    UploadTR --> DiffCalc
    
    DiffCalc --> HasChanges{Has Changes?}
    HasChanges -->|Yes| CreateDiffSession[Generate diff session<br/>with only new articles]
    HasChanges -->|No| Skip[Skip processing]
    
    CreateDiffSession --> WordCount[WordCounter<br/>count_words_in_gcs_file]
    
    WordCount --> BatchCreate[BatchManager<br/>create_batches<br/>Max 2M words per batch]
    
    BatchCreate --> BatchLoop{For Each Batch}
    
    BatchLoop --> GenRequest[BatchRequestGenerator<br/>create_batch_request_file<br/>Generate JSONL requests]
    
    GenRequest --> SubmitBatch[VertexAIBatchProcessor<br/>submit_batch_job<br/>client.batches.create]
    
    SubmitBatch --> MonitorJob[Monitor batch job<br/>Poll until completion<br/>Up to 24 hours]
    
    MonitorJob --> JobComplete{Job Status}
    JobComplete -->|SUCCEEDED| DownloadResults[Download batch results<br/>from GCS output location]
    JobComplete -->|FAILED| HandleError[Log error and<br/>retry if needed]
    JobComplete -->|RUNNING| WaitPoll[Wait and poll again]
    
    WaitPoll --> MonitorJob
    HandleError --> BatchLoop
    
    DownloadResults --> ProcessResults[BatchResultProcessor<br/>process_batch_results]
    
    ProcessResults --> SaveSummaries[Save AI summaries to GCS<br/>summaries/ folder]
    
    SaveSummaries --> UpdateMetadata[Update metadata files<br/>manifest.csv<br/>processing_log.txt]
    
    UpdateMetadata --> NextBatch{More Batches?}
    NextBatch -->|Yes| BatchLoop
    NextBatch -->|No| Cleanup[Cleanup old files<br/>if retention policy applies]
    
    Cleanup --> End([End Pipeline])
    Skip --> End
```

## Function Call Hierarchy

```mermaid
flowchart TD
    Main[main.py] --> Orchestrator[GCSCollectionOrchestrator.run_full_pipeline]
    
    Orchestrator --> Scrape[_run_scraping_phase]
    Orchestrator --> Diff[_run_diff_calculation_phase]
    Orchestrator --> Batch[_run_batch_processing_phase]
    Orchestrator --> Metadata[_run_metadata_update_phase]
    Orchestrator --> Cleanup[_cleanup_old_files]
    
    %% Scraping Phase
    Scrape --> Journalist[journalist.read]
    Scrape --> GCSUpload[GCSFolderManager.upload_session_data]
    GCSUpload --> CreateStructure[create_source_folder_structure]
    GCSUpload --> GetSessionNum[get_next_session_number]
    
    %% Diff Calculation Phase
    Diff --> CalcDiff[SessionDiffCalculator.calculate_diff]
    CalcDiff --> FindLatest[find_latest_session]
    CalcDiff --> CompareArticles[_compare_articles]
    CalcDiff --> GenDiffSession[_generate_diff_session]
    FindLatest --> GCSList[GCSFolderManager.list_existing_sessions]
    
    %% Batch Processing Phase
    Batch --> CountWords[WordCounter.count_words_in_gcs_file]
    Batch --> CreateBatches[BatchManager.create_batches]
    CreateBatches --> CalcBatchWords[_calculate_batch_word_count]
    CreateBatches --> ValidateBatch[validate_batch_size]
    
    Batch --> GenRequests[BatchRequestGenerator.create_batch_request_file]
    GenRequests --> GenSingleReq[_generate_single_request]
    GenRequests --> UploadRequest[upload_batch_request_to_gcs]
    GenSingleReq --> ConstructPrompt[_construct_prompt_with_gcs_reference]
    
    Batch --> SubmitJob[VertexAIBatchProcessor.submit_batch_job]
    SubmitJob --> ClientBatchCreate[client.batches.create]
    
    Batch --> MonitorJob[monitor_batch_job]
    MonitorJob --> ClientBatchGet[client.batches.get]
    
    Batch --> DownloadResults[download_batch_results]
    DownloadResults --> ParseResultLine[_parse_batch_result_line]
    
    Batch --> ProcessBatch[process_single_batch]
    ProcessBatch --> ProcessResults[BatchResultProcessor.process_batch_results]
    
    %% Result Processing
    ProcessResults --> ExtractSummary[_extract_summary_from_result]
    ProcessResults --> SaveSummaryGCS[_save_summary_to_gcs]
    SaveSummaryGCS --> GCSSaveSummary[GCSFolderManager.save_summary_to_gcs]
    
    %% Metadata Update
    Metadata --> UpdateMeta[BatchResultProcessor._update_metadata_files]
    Metadata --> LogStats[_log_batch_processing_stats]
```

## Data Flow Architecture

```mermaid
flowchart LR
    subgraph "Input Sources"
        EU[search_parameters_eu.json]
        TR[search_parameters_tr.json]
    end
    
    subgraph "Scraping Layer"
        Journalist[Journalist.read]
        RawSessions[Raw Session Data]
    end
    
    subgraph "GCS Storage Layer"
        GCSArticles[GCS: articles/]
        GCSBatchReq[GCS: batch_processing/requests/]
        GCSBatchRes[GCS: batch_processing/results/]
        GCSSummaries[GCS: summaries/]
        GCSMetadata[GCS: metadata/]
    end
    
    subgraph "Processing Layer"
        DiffCalc[Diff Calculator]
        WordCount[Word Counter]
        BatchMgr[Batch Manager]
        BatchGen[Batch Request Generator]
    end
    
    subgraph "Vertex AI Layer"
        BatchSubmit[Batch Job Submission]
        BatchMonitor[Job Monitoring]
        BatchResults[Result Collection]
    end
    
    subgraph "Output Layer"
        Summaries[AI Summaries]
        Metadata[Updated Metadata]
        Logs[Processing Logs]
    end
    
    %% Flow connections
    EU --> Journalist
    TR --> Journalist
    Journalist --> RawSessions
    RawSessions --> GCSArticles
    
    GCSArticles --> DiffCalc
    DiffCalc --> WordCount
    WordCount --> BatchMgr
    BatchMgr --> BatchGen
    BatchGen --> GCSBatchReq
    
    GCSBatchReq --> BatchSubmit
    BatchSubmit --> BatchMonitor
    BatchMonitor --> BatchResults
    BatchResults --> GCSBatchRes
    
    GCSBatchRes --> Summaries
    Summaries --> GCSSummaries
    Summaries --> Metadata
    Metadata --> GCSMetadata
    Metadata --> Logs
```

## Batch Processing State Machine

```mermaid
stateDiagram-v2
    [*] --> ScrapingComplete : Pipeline Start
    
    ScrapingComplete --> CalculatingDiff : Raw sessions uploaded to GCS
    CalculatingDiff --> DiffComplete : Diff calculations done
    
    DiffComplete --> WordCounting : Only changed articles remain
    WordCounting --> BatchCreation : Word counts calculated
    BatchCreation --> BatchGeneration : Batches created (max 2M words)
    
    BatchGeneration --> RequestUpload : JSONL request files generated
    RequestUpload --> BatchSubmission : Request files uploaded to GCS
    
    BatchSubmission --> JobMonitoring : Batch jobs submitted to Vertex AI
    
    state JobMonitoring {
        [*] --> Pending
        Pending --> Running : Job started
        Running --> Running : Still processing
        Running --> Succeeded : Job completed successfully
        Running --> Failed : Job failed
        Failed --> Retry : Retry if possible
        Retry --> Pending
        Succeeded --> [*]
    }
    
    JobMonitoring --> ResultDownload : All jobs succeeded
    ResultDownload --> ResultProcessing : Batch results downloaded
    
    ResultProcessing --> SummaryGeneration : Results parsed and validated
    SummaryGeneration --> MetadataUpdate : Summaries saved to GCS
    
    MetadataUpdate --> Cleanup : Metadata files updated
    Cleanup --> [*] : Pipeline complete
    
    %% Error paths
    CalculatingDiff --> ErrorHandling : Diff calculation failed
    WordCounting --> ErrorHandling : Word counting failed
    BatchCreation --> ErrorHandling : Batch creation failed
    BatchSubmission --> ErrorHandling : Job submission failed
    ResultDownload --> ErrorHandling : Result download failed
    
    ErrorHandling --> [*] : Error logged and handled
```

## Integration Points

### 1. Collection Orchestrator Integration
```python
# Main entry point
async def main():
    orchestrator = GCSCollectionOrchestrator(
        project_id=os.getenv("GOOGLE_CLOUD_PROJECT"),
        bucket_name=os.getenv("GCS_BUCKET_NAME")
    )
    
    results = await orchestrator.run_full_pipeline(regions=["eu", "tr"])
    logger.info(f"Pipeline completed: {results}")
```

### 2. Journalist Integration
```python
# In _run_scraping_phase
from journalist.core import Journalist

journalist = Journalist()
eu_sessions = await journalist.read("search_parameters_eu.json")
tr_sessions = await journalist.read("search_parameters_tr.json")
```

### 3. Vertex AI Integration
```python
# In VertexAIBatchProcessor
from google import genai

self.client = genai.Client(
    vertexai=True,
    project=self.project_id,
    location=self.location
)

job = self.client.batches.create(
    model="gemini-2.5-pro",
    src=batch_request_gcs_uri,
    config=genai.types.CreateBatchJobConfig(
        dest=batch_output_gcs_uri
    )
)
```

### 4. GCS Integration
```python
# In GCSFolderManager
from google.cloud import storage

self.storage_client = storage.Client(project=self.project_id)
bucket = self.storage_client.bucket(self.bucket_name)
blob = bucket.blob(file_path)
blob.upload_from_string(json.dumps(data))
```

## Error Handling Strategy

```mermaid
flowchart TD
    Error[Error Occurs] --> ErrorType{Error Type?}
    
    ErrorType -->|Scraping Error| ScrapingRetry[Retry with backoff<br/>Log source failure<br/>Continue with other sources]
    ErrorType -->|GCS Upload Error| GCSRetry[Retry upload<br/>Check permissions<br/>Validate file size]
    ErrorType -->|Diff Calculation Error| DiffRetry[Skip diff for source<br/>Process as full session<br/>Log warning]
    ErrorType -->|Batch Job Error| BatchRetry[Retry batch job<br/>Split batch if too large<br/>Check quotas]
    ErrorType -->|Result Processing Error| ResultRetry[Retry result download<br/>Validate JSONL format<br/>Skip corrupted entries]
    
    ScrapingRetry --> Continue[Continue Pipeline]
    GCSRetry --> Continue
    DiffRetry --> Continue
    BatchRetry --> Continue
    ResultRetry --> Continue
    
    Continue --> LogError[Log to processing_log.txt<br/>Update metadata with error info<br/>Send monitoring alerts]
    LogError --> End[Continue or Abort Pipeline]
```

This architecture provides a comprehensive view of how all components interact in the new Vertex AI batch processing-based GCS integration system.
