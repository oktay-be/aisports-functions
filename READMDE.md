# AI Sports Functions - Event-Driven Microservices Architecture

This project implements an event-driven microservices architecture using Google Cloud Functions for sports news scraping and AI-powered content processing.

## Architecture Overview

The system consists of multiple Cloud Functions that communicate through Google Cloud Pub/Sub topics:

1. **Scraper Function** (`scraper_function/`) - Scrapes news content and stores it in GCS
2. **Batch Builder Function** (`batch_builder_function/`) - Prepares batches for AI processing  
3. **AI Processor Function** (`ai_processor_function/`) - Processes content using Vertex AI
4. **Result Processor Function** (`result_processor_function/`) - Processes and stores AI results

## Storage Structure

All data is stored in Google Cloud Storage with the following structure:

```
news_data/
├── sources/
│   ├── bbc/
│   │   ├── 2025-07/
│   │   │   ├── articles/     # Raw session data from scraping
│   │   │   ├── summaries/    # AI-generated summaries
│   │   │   └── metadata/     # Processing logs and manifests
│   └── ...
├── batch_processing/         # Vertex AI batch processing data
└── processing_runs/          # Processing run metadata
```

## Local Development Setup

### Prerequisites

- Python 3.12
- Google Cloud SDK (gcloud CLI)
- Access to the `gen-lang-client-0306766464` Google Cloud project

### Environment Setup

1. Create a virtual environment using Python 3.12:

   ```cmd
   py -3.12 -m venv .venv
   .venv\Scripts\activate
   ```

2. Install dependencies:

   ```cmd
   # Install pip-tools for dependency management
   python -m pip install pip-tools==7.3.0
   
   # Compile requirements from requirements.in
   pip-compile requirements.in --output-file requirements.txt
   
   # Install all dependencies
   python -m pip install -r requirements.txt
   ```

3. Set up Google Cloud authentication:

   ```cmd
   gcloud auth login
   gcloud config set project gen-lang-client-0306766464
   gcloud auth application-default login
   ```

### Environment Variables

Each function requires specific environment variables. See individual function directories for details.

Common variables:
- `GOOGLE_CLOUD_PROJECT=gen-lang-client-0306766464`
- `GCS_BUCKET_NAME=aisports-news-data`
- `NEWS_DATA_ROOT_PREFIX=news_data/`

## Deployment

### Automated CI/CD

All functions are automatically deployed via GitHub Actions when changes are pushed to the `main` branch:

- `.github/workflows/deploy-scraper-function.yml` - Deploys scraper function

Additional workflows will be created as functions are implemented:
- `deploy-batch-builder-function.yml` (when batch_builder_function/ is created)
- `deploy-ai-processor-function.yml` (when ai_processor_function/ is created)
- `deploy-result-processor-function.yml` (when result_processor_function/ is created)

### Required GitHub Secrets

- `GOOGLE_APPLICATION_CREDENTIALS_BASE64` - Base64 encoded service account key

### Local Testing

Each function directory contains test files and local testing utilities. For example:

```cmd
cd scraper_function
python trigger_test.py
```

## Project Structure

```
aisports-functions/
├── .github/workflows/          # GitHub Actions CI/CD workflows
├── scraper_function/           # Web scraping Cloud Function
├── batch_builder_function/     # Batch preparation function (to be created)
├── ai_processor_function/      # AI processing function (to be created)  
├── result_processor_function/  # Result processing function (to be created)
├── shared_libs/               # Shared libraries (to be created)
├── legacy_monolithic_code/    # Original monolithic application (archived)
├── Cloud Function Migration/  # Documentation and reference files
├── requirements.in            # Project dependencies
└── .gitignore                # Git ignore rules
```

## Technology Stack

- **Cloud Functions**: Serverless compute platform
- **Cloud Pub/Sub**: Asynchronous messaging
- **Cloud Storage**: Data persistence
- **Vertex AI**: AI/ML processing
- **Python 3.9**: Runtime environment
- **GitHub Actions**: CI/CD pipeline

## Key Features

- **Event-driven architecture**: Functions communicate via Pub/Sub topics
- **GCS-only storage**: No dependency on Firestore or other databases
- **Automated deployment**: GitHub Actions workflows for CI/CD
- **Scalable design**: Independent scaling of each microservice
- **Comprehensive logging**: Structured logging throughout the pipeline

## Contributing

1. Make changes in feature branches
2. Test locally before pushing
3. GitHub Actions will automatically deploy to production on merge to `main`
4. Monitor Cloud Function logs for deployment status

## Documentation

See the `Cloud Function Migration/` directory for detailed architecture documentation and implementation guides.