# GCS Folder Structure Design for Batch Processing

## Objective
Organize batch processing files (requests, inputs, results) to support:
1.  Daily grouping (`YYYY-MM-DD`).
2.  Multiple pipeline executions per day.
3.  Clear separation of pipeline stages (Extraction vs. Deduplication).
4.  Clear data flow (Inputs -> Requests -> Results).

## Proposed Structure

The root path is: `gs://aisports-scraping/news_data/batch_processing/`

### Hierarchy Level 1: Date
`{YYYY-MM}/{YYYY-MM-DD}/`

### Hierarchy Level 2: Pipeline Instance (The "Descriptor")
To support multiple triggers per day, each pipeline execution gets its own root folder, named with the start timestamp (and optionally a unique ID or tag).

`{YYYY-MM}/{YYYY-MM-DD}/run_{HH-MM-SS}/`

### Hierarchy Level 3: Stages
Inside a pipeline run folder, we separate the processing stages.

#### Stage 1: Extraction (Batch Builder)
Folder: `stage1_extraction/`

*   **`requests/`**: Contains the files generated to trigger the Vertex AI batch job.
    *   `request.jsonl` (The actual batch request)
    *   `job_metadata.json` (Metadata about the job)
    *   `source_files_manifest.json` (List of source files processed)
*   **`results/`**: Contains the raw output from Vertex AI.
    *   `predictions.jsonl` (Raw extracted articles)

#### Stage 2: Deduplication (Result Merger)
Folder: `stage2_deduplication/`

*   **`input_merged_data/`**: Contains the *inputs* for this stage (the merged JSONs from Stage 1).
    *   `merged_session_data_{source}.json`
*   **`requests/`**: Contains the batch request generated from the inputs.
    *   `request.jsonl`
*   **`results/`**: Contains the final output.
    *   `predictions.jsonl` (Final deduped content)

## Example Tree View

```text
news_data/batch_processing/2025-11/2025-11-19/
│
├── run_19-20-56/                             <-- PIPELINE INSTANCE 1
│   │
│   ├── stage1_extraction/
│   │   ├── requests/
│   │   │   ├── request.jsonl
│   │   │   ├── job_metadata.json
│   │   │   └── source_files_manifest.json
│   │   │
│   │   └── results/
│   │       └── predictions.jsonl
│   │
│   └── stage2_deduplication/
│       ├── input_merged_data/
│       │   ├── merged_session_data_fanatik.json
│       │   └── merged_session_data_ntvspor.json
│       │
│       ├── requests/
│       │   └── request.jsonl
│       │
│       └── results/
│           └── predictions.jsonl
│
└── run_21-15-00/                             <-- PIPELINE INSTANCE 2 (New Trigger)
    │
    ├── stage1_extraction/
    │   └── ...
    │
    └── stage2_deduplication/
        └── ...
```
