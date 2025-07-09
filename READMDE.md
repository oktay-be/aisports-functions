# AISports Cloud Functions

This repository contains the event-driven microservices architecture for AISports using Google Cloud Functions.

## Overview

This project implements a distributed system for processing sports news data using Google Cloud Functions, Pub/Sub, and Cloud Storage. The system is designed to scrape news content, process it with AI, and store results in a scalable manner.

## Architecture

The system consists of four main Cloud Functions:

1. **Scraper Function** - Scrapes news content from various sources
2. **Batch Builder Function** - Aggregates session data for batch processing
3. **AI Processor Function** - Processes data using Vertex AI
4. **Result Processor Function** - Handles processed results and storage

## Project Structure

```
├── scraper_function/          # Session Data Scraper Function
├── batch_builder_function/    # Batch Builder Function
├── ai_processor_function/     # AI Processor Function
├── result_processor_function/ # Result Processor Function
├── Cloud Function Migration/  # Architecture documentation
├── legacy_monolithic_code/    # Reference implementation
└── README.md                  # This file
```

## Setup

### Prerequisites

- Python 3.12 installed
- Google Cloud CLI installed and authenticated
- Access to Google Cloud project: `gen-lang-client-0306766464`

### Environment Setup

1. Create a virtual environment using Python 3.12:

```cmd
py -3.12 -m venv .venv
.venv\Scripts\activate
```

2. Install dependencies:

```cmd
# Step 1: Install pip-tools (recommended)
python -m pip install pip-tools==7.3.0
pip-compile requirements.in --output-file requirements.txt

# Step 2: Install dependencies
python -m pip install -r requirements.txt
```

## Development

Each function is contained in its own directory with:
- `main.py` - Function implementation
- `requirements.txt` - Dependencies
- `deploy.sh` / `deploy.bat` - Deployment scripts
- `README.md` - Function-specific documentation

## Deployment

Refer to individual function README files for specific deployment instructions.

## Architecture Documentation

Detailed architecture and implementation guides are available in the `Cloud Function Migration/` directory.

## License

MIT

### Setup

1. Ceate a virtual environment using Python 3.12:

   py -3.12 -m venv .venv
   .venv\Scripts\activate

2. Install dependencies:


# Step 1 Using pip-compile (recommended)
python -m pip install pip-tools==7.3.0
pip-compile requirements.in --output-file requirements.txt

# Step 2
python -m pip install -r requirements.txt