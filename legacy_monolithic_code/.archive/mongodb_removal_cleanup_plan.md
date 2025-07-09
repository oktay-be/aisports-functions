# MongoDB Removal and Cleanup Plan

## Overview

This document outlines the complete removal of MongoDB dependencies from the AISports codebase as part of the GCS integration implementation.

## Files to Remove Completely

### 1. Database Module Files
```
database/
├── __init__.py
├── mongodb_client.py
└── README.md (if exists)
```

### 2. MongoDB Test Files
```
tests/
├── test_mongodb_client.py
├── test_mongodb_client_motor.py
└── Any other MongoDB-related test files
```

### 3. MongoDB-dependent Integration Files
```
integrations/
└── ai_post_maker.py (if it uses MongoDB - needs verification)
```

## Files to Modify - Remove MongoDB References

### 1. Environment Configuration
**File**: `.env`
```diff
- MONGODB_URI=mongodb://localhost:27017
- MONGODB_DATABASE=aisports
```

**File**: `requirements.in`
```diff
- pymongo==4.13.2  # MongoDB driver with async support
```

### 2. Capabilities Module

**File**: `capabilities/ai_aggregator.py`
- Remove: `from database.mongodb_client import MongoDBClient`
- Remove: `self.db_client = MongoDBClient()`
- Remove: All MongoDB save operations
- Modify: All methods to use GCS instead of MongoDB

**Lines to Remove/Modify**:
- Line 21: Import statement
- Line 68: Database client initialization
- Lines 76, 78, 112, 122, 160, 170, 230, 242: MongoDB references in comments and code

### 3. Integrations Module

**File**: `integrations/collection_orchestrator.py`
- Remove: `from database.mongodb_client import MongoDBClient`
- Remove: `self.db_client = MongoDBClient()`
- Remove: All MongoDB operations
- Replace: All database operations with GCS equivalents

**Lines to Remove/Modify**:
- Line 16: Import statement
- Line 73: Database client initialization
- Lines 127-132, 146, 216, 227, 236, 273, 275, 289, 332, 363, 431, 499, 552: MongoDB references

### 4. Test Files

**File**: `test_run_full_collection_only_scraping.py`
- Remove: MongoDB URI configuration
- Lines 132-135: MongoDB URI setup

**File**: `test_fixes.py`
- Remove: MongoDB test references
- Lines 42-43: MongoDB test case

## Replacement Strategy

### 1. Replace MongoDB Operations with GCS Operations

#### Current MongoDB Pattern:
```python
# Save to MongoDB
await self.db_client.save_article_summary(
    summary_data,
    collection_run_id=run_id
)
```

#### New GCS Pattern:
```python
# Save to GCS
gcs_path = self.folder_manager.get_summaries_path(source, date)
filename = f"ai_summarized_session_data_{source}_{session_number:03d}.json"
await self.gcs_client.upload_json(summary_data, f"{gcs_path}/{filename}")
```

### 2. Replace MongoDB Queries with GCS Listing

#### Current MongoDB Pattern:
```python
# Get latest summaries from MongoDB
summaries = await self.db_client.get_source_summaries(
    collection_run_id=run_id,
    region=region
)
```

#### New GCS Pattern:
```python
# Get latest summaries from GCS
summaries_path = self.folder_manager.get_summaries_path(source, date)
summary_files = await self.gcs_client.list_files(summaries_path)
summaries = []
for file_path in summary_files:
    summary_data = await self.gcs_client.download_json(file_path)
    summaries.append(summary_data)
```

### 3. Replace MongoDB IDs with GCS Paths

#### Current Pattern:
```python
collection_run_id = await self.db_client.create_collection_run(run_metadata)
```

#### New Pattern:
```python
run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
run_metadata_path = f"metadata/collection_run_{run_timestamp}.json"
await self.gcs_client.upload_json(run_metadata, run_metadata_path)
```

## Updated Class Definitions

### 1. Updated AISummarizer (GCS Version)
```python
class AISummarizer:
    def __init__(self, project_id: str = None, location: str = None, model_name: str = "gemini-2.5-pro"):
        # Remove: self.db_client = MongoDBClient()
        self.gcs_client = GCSClient(bucket_name=os.getenv("GCS_BUCKET_NAME"))
        self.folder_manager = GCSFolderManager(bucket_name=os.getenv("GCS_BUCKET_NAME"))
        # ... rest of initialization
    
    async def _save_ai_summary_to_gcs(self, session_data: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Save AI summary result to GCS instead of workspace directory."""
        # New GCS-based implementation
```

### 2. Updated CollectionOrchestrator (GCS Version)
```python
class CollectionOrchestrator:
    def __init__(self, bucket_name: str):
        # Remove: self.db_client = MongoDBClient()
        self.gcs_client = GCSClient(bucket_name)
        self.folder_manager = GCSFolderManager(bucket_name)
        # ... rest of initialization
    
    async def run_full_collection(self) -> Dict[str, Any]:
        """Run full collection pipeline using GCS storage."""
        # Replace all MongoDB operations with GCS operations
```

### 3. Updated AIAggregator (GCS Version)
```python
class AIAggregator:
    def __init__(self, project_id: str = None, location: str = None):
        # Remove: self.db_client = MongoDBClient()
        self.gcs_client = GCSClient(bucket_name=os.getenv("GCS_BUCKET_NAME"))
        self.folder_manager = GCSFolderManager(bucket_name=os.getenv("GCS_BUCKET_NAME"))
        # ... rest of initialization
```

## Migration Steps

### Step 1: Create GCS Infrastructure Classes
1. Create `utils/gcs_folder_manager.py`
2. Create `integrations/gcs_client.py`
3. Update `requirements.in` to include GCS dependencies

### Step 2: Update Core Classes
1. Modify `capabilities/ai_summarizer.py`
2. Modify `capabilities/ai_aggregator.py` 
3. Create new `integrations/gcs_collection_orchestrator.py`

### Step 3: Remove MongoDB Files
1. Delete `database/` directory entirely
2. Delete MongoDB test files
3. Remove MongoDB-dependent integration files

### Step 4: Update Configuration
1. Remove MongoDB environment variables from `.env`
2. Update `requirements.in`
3. Update any configuration documentation

### Step 5: Update Tests
1. Remove MongoDB test references
2. Create new GCS-based tests
3. Update integration tests

## Data Migration (if needed)

If there's existing data in MongoDB that needs to be preserved:

### 1. Export MongoDB Data
```python
async def export_mongodb_to_gcs():
    """One-time migration script to move data from MongoDB to GCS"""
    db_client = MongoDBClient()
    gcs_client = GCSClient("multi-modal-ai-bucket")
    
    # Export articles
    articles = await db_client.get_all_articles()
    for article in articles:
        gcs_path = f"migrated_data/articles/{article['id']}.json"
        await gcs_client.upload_json(article, gcs_path)
    
    # Export summaries
    summaries = await db_client.get_all_summaries()
    for summary in summaries:
        gcs_path = f"migrated_data/summaries/{summary['id']}.json"
        await gcs_client.upload_json(summary, gcs_path)
```

### 2. Verify Migration
```python
async def verify_migration():
    """Verify that all data was successfully migrated to GCS"""
    # Compare counts and sample data
```

## Updated Dependencies

### Remove from requirements.in:
```
pymongo==4.13.2
motor>=3.0.0 (if present)
```

### Add to requirements.in:
```
google-cloud-storage>=2.10.0
```

## Environment Variables Changes

### Remove:
```env
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=aisports
```

### Add:
```env
GCS_BUCKET_NAME=multi-modal-ai-bucket
GCS_PROJECT_ID=gen-lang-client-0306766464
```

## Validation Checklist

After MongoDB removal:

- [ ] No MongoDB imports in any Python file
- [ ] No MongoDB references in configuration files
- [ ] All tests pass without MongoDB dependencies
- [ ] GCS operations work correctly
- [ ] Data persistence maintains same functionality
- [ ] Error handling works with GCS operations
- [ ] Performance is acceptable with GCS operations
- [ ] All MongoDB test files removed
- [ ] Requirements.txt updated
- [ ] Environment configuration updated
- [ ] Documentation updated

## Risk Mitigation

1. **Backup Current Codebase**: Create a branch with MongoDB version before removal
2. **Gradual Migration**: Implement GCS classes first, then remove MongoDB
3. **Parallel Testing**: Test GCS operations while MongoDB is still available
4. **Data Validation**: Ensure no data loss during migration
5. **Rollback Plan**: Keep ability to revert to MongoDB if needed

## Timeline

- **Day 1**: Create GCS infrastructure classes
- **Day 2**: Update core classes to use GCS
- **Day 3**: Remove MongoDB files and references
- **Day 4**: Update tests and configuration
- **Day 5**: Final testing and validation
