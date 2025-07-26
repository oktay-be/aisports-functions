# Pub/Sub Topic Parametrization Summary

This document summarizes the changes made to parametrize all Pub/Sub topic names using environment variables across the aisports-functions project.

## Changes Made

### 1. Environment Variable Configuration

All Pub/Sub topic names are now parametrized using environment variables with sensible defaults:

- `SCRAPING_REQUEST_TOPIC` (default: `scraping-requests`)
- `SESSION_DATA_CREATED_TOPIC` (default: `session-data-created`) 
- `BATCH_JOB_CREATED_TOPIC` (default: `batch-job-created`)

### 2. GitHub Actions Workflow Updates

#### Scraper Function Workflow (`.github/workflows/deploy-scraper-function.yml`)
- **Fixed**: YAML formatting issues (missing newlines)
- **Updated**: `event_trigger_pubsub_topic` uses `${{ vars.SCRAPING_REQUEST_TOPIC || 'scraping-requests' }}`
- **Updated**: Environment variables use GitHub repository variables with fallbacks
- **Removed**: Trailing commas in environment variable definitions

#### Batch Builder Function Workflow (`.github/workflows/deploy-batch-builder-function.yml`)
- **Fixed**: YAML formatting issues (missing newlines between steps)
- **Updated**: `event_trigger_pubsub_topic` uses `${{ vars.SESSION_DATA_CREATED_TOPIC || 'session-data-created' }}`
- **Updated**: All environment variables use GitHub repository variables with fallbacks
- **Removed**: Trailing commas in environment variable definitions

### 3. Test File Updates

#### Scraper Function Test Files
- `scraper_function/trigger_test_eu.py`: Updated to use `os.getenv('SCRAPING_REQUEST_TOPIC', 'scraping-requests')`
- `scraper_function/trigger_test_tr.py`: Updated to use `os.getenv('SCRAPING_REQUEST_TOPIC', 'scraping-requests')`

#### Batch Builder Function Test File
- `batch_builder_function/trigger_test.py`: Updated to use `os.getenv('SESSION_DATA_CREATED_TOPIC', 'session-data-created')`

### 4. Environment Configuration Updates

#### New/Updated .env.example Files
- `scraper_function/.env.example`: Added `SCRAPING_REQUEST_TOPIC=scraping-requests`
- `batch_builder_function/.env.example`: Created with all parametrized variables

#### Main Project README
- `READMDE.md`: Updated environment variables section to document all parametrized topics

## GitHub Repository Variables Setup

To customize topic names in your GitHub repository, set the following repository variables:

1. Go to your GitHub repository → Settings → Secrets and variables → Actions → Variables
2. Create the following repository variables (optional - defaults will be used if not set):

```
SCRAPING_REQUEST_TOPIC=your-custom-scraping-topic
SESSION_DATA_CREATED_TOPIC=your-custom-session-topic  
BATCH_JOB_CREATED_TOPIC=your-custom-batch-topic
```

## Benefits

1. **Flexibility**: Topic names can be easily changed without code modifications
2. **Environment Separation**: Different environments can use different topic names
3. **Testing**: Local development can use separate topics from production
4. **Maintenance**: Centralized configuration reduces hardcoded values
5. **CI/CD Integration**: GitHub Actions can deploy with custom topic names per environment

## Code Examples

### Function Code (Environment Variable Usage)
```python
import os

# All functions now use this pattern
SESSION_DATA_CREATED_TOPIC = os.getenv('SESSION_DATA_CREATED_TOPIC', 'session-data-created')
BATCH_JOB_CREATED_TOPIC = os.getenv('BATCH_JOB_CREATED_TOPIC', 'batch-job-created')
```

### GitHub Actions (Workflow Configuration)
```yaml
environment_variables: |
  SESSION_DATA_CREATED_TOPIC=${{ vars.SESSION_DATA_CREATED_TOPIC || 'session-data-created' }}
  BATCH_JOB_CREATED_TOPIC=${{ vars.BATCH_JOB_CREATED_TOPIC || 'batch-job-created' }}

event_trigger_pubsub_topic: projects/gen-lang-client-0306766464/topics/${{ vars.SESSION_DATA_CREATED_TOPIC || 'session-data-created' }}
```

## Files Modified

### Core Function Files
- `scraper_function/main.py` (already parametrized)
- `batch_builder_function/main.py` (already parametrized)

### Workflow Files  
- `.github/workflows/deploy-scraper-function.yml` (✅ Fixed YAML + parametrized)
- `.github/workflows/deploy-batch-builder-function.yml` (✅ Fixed YAML + parametrized)

### Test Files
- `scraper_function/trigger_test_eu.py` (✅ Parametrized)
- `scraper_function/trigger_test_tr.py` (✅ Parametrized)  
- `batch_builder_function/trigger_test.py` (✅ Parametrized)

### Configuration Files
- `scraper_function/.env.example` (✅ Updated)
- `batch_builder_function/.env.example` (✅ Created)
- `READMDE.md` (✅ Updated)

All topic names are now fully parametrized and ready for flexible deployment across different environments.
