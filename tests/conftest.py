"""
Shared test fixtures for aisports-functions.

Provides mock implementations of:
- Google Cloud Storage (GCS)
- Vertex AI (GenAI client for embeddings)
- Pub/Sub Publisher
- Secret Manager
- Sample article data
"""

import pytest
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import numpy as np

# Add function directories to path for imports
FUNCTIONS_ROOT = Path(__file__).parent.parent
for func_dir in FUNCTIONS_ROOT.iterdir():
    if func_dir.is_dir() and func_dir.name.endswith('_function'):
        sys.path.insert(0, str(func_dir))


# ============================================================================
# GCS MOCKING
# ============================================================================

class MockBlob:
    """Mock GCS Blob object."""

    def __init__(self, name: str, content: str = ""):
        self.name = name
        self._content = content
        self.exists_value = True
        self.size = len(content.encode()) if content else 0
        self.updated = datetime.now(timezone.utc)

    def download_as_text(self) -> str:
        return self._content

    def download_as_string(self) -> bytes:
        return self._content.encode()

    def download_as_bytes(self) -> bytes:
        return self._content.encode()

    def upload_from_string(self, content: str, content_type: str = None):
        self._content = content if isinstance(content, str) else content.decode()
        self.size = len(self._content.encode())

    def exists(self) -> bool:
        return self.exists_value


class MockBucket:
    """Mock GCS Bucket object."""

    def __init__(self, name: str):
        self.name = name
        self._blobs: Dict[str, MockBlob] = {}

    def blob(self, blob_path: str) -> MockBlob:
        if blob_path not in self._blobs:
            self._blobs[blob_path] = MockBlob(blob_path)
        return self._blobs[blob_path]

    def list_blobs(self, prefix: str = "", max_results: int = None, delimiter: str = None):
        matching = [b for b in self._blobs.values() if b.name.startswith(prefix)]
        if max_results:
            matching = matching[:max_results]
        return iter(matching)

    def add_blob(self, path: str, content: str) -> MockBlob:
        """Helper to add a blob with content."""
        blob = MockBlob(path, content)
        self._blobs[path] = blob
        return blob

    def add_json_blob(self, path: str, data: dict) -> MockBlob:
        """Helper to add a blob with JSON content."""
        return self.add_blob(path, json.dumps(data, ensure_ascii=False))


class MockStorageClient:
    """Mock GCS Storage Client."""

    def __init__(self):
        self._buckets: Dict[str, MockBucket] = {}

    def bucket(self, bucket_name: str) -> MockBucket:
        if bucket_name not in self._buckets:
            self._buckets[bucket_name] = MockBucket(bucket_name)
        return self._buckets[bucket_name]

    def get_bucket(self, bucket_name: str) -> MockBucket:
        return self.bucket(bucket_name)


@pytest.fixture
def mock_storage_client():
    """Provides a mock GCS storage client."""
    return MockStorageClient()


@pytest.fixture
def mock_gcs_bucket(mock_storage_client):
    """Provides a pre-configured mock GCS bucket."""
    return mock_storage_client.bucket("aisports-scraping")


# ============================================================================
# VERTEX AI / GENAI MOCKING
# ============================================================================

class MockEmbedding:
    """Mock Vertex AI Embedding response."""

    def __init__(self, values: List[float]):
        self.values = values


class MockEmbedResponse:
    """Mock Vertex AI embed_content response."""

    def __init__(self, embeddings: List[List[float]]):
        self.embeddings = [MockEmbedding(e) for e in embeddings]


class MockGenAIModels:
    """Mock genai.Client.models interface."""

    def __init__(self, embedding_dim: int = 768):
        self.embedding_dim = embedding_dim
        self._call_count = 0

    def embed_content(self, model: str, contents: list, config=None) -> MockEmbedResponse:
        """Return deterministic embeddings based on content hash."""
        embeddings = []
        for content in contents:
            # Create deterministic but unique embedding
            content_str = str(content) if not isinstance(content, str) else content
            seed = hash(content_str) % 10000
            np.random.seed(seed)
            embedding = np.random.randn(self.embedding_dim).tolist()
            embeddings.append(embedding)
        self._call_count += 1
        return MockEmbedResponse(embeddings)


class MockBatchJob:
    """Mock Vertex AI Batch Job."""

    def __init__(self, name: str):
        self.name = name
        self.state = "JOB_STATE_PENDING"
        self.create_time = datetime.now(timezone.utc).isoformat()


class MockGenAIBatches:
    """Mock genai.Client.batches interface."""

    def __init__(self):
        self.job_counter = 0
        self.created_jobs: List[MockBatchJob] = []

    def create(self, model: str, src: str, config=None) -> MockBatchJob:
        self.job_counter += 1
        job = MockBatchJob(
            f"projects/test-project/locations/us-central1/batchPredictionJobs/{self.job_counter}"
        )
        self.created_jobs.append(job)
        return job


class MockGenAIClient:
    """Mock Google GenAI Client."""

    def __init__(self, embedding_dim: int = 768):
        self.models = MockGenAIModels(embedding_dim)
        self.batches = MockGenAIBatches()


@pytest.fixture
def mock_genai_client():
    """Provides a mock Vertex AI GenAI client."""
    return MockGenAIClient()


@pytest.fixture
def mock_embeddings():
    """Provides sample embeddings for testing."""
    np.random.seed(42)
    return np.random.randn(10, 768)


# ============================================================================
# PUB/SUB MOCKING
# ============================================================================

class MockPublisher:
    """Mock Pub/Sub Publisher."""

    def __init__(self):
        self.published_messages: List[Dict] = []

    def topic_path(self, project: str, topic: str) -> str:
        return f"projects/{project}/topics/{topic}"

    def publish(self, topic_path: str, data: bytes, **attributes):
        future = MagicMock()
        message_id = f"message-{len(self.published_messages)}"
        future.result.return_value = message_id
        self.published_messages.append({
            "topic": topic_path,
            "data": data,
            "attributes": attributes,
            "message_id": message_id
        })
        return future


@pytest.fixture
def mock_publisher():
    """Provides a mock Pub/Sub publisher."""
    return MockPublisher()


# ============================================================================
# SECRET MANAGER MOCKING
# ============================================================================

class MockSecretManager:
    """Mock Secret Manager client."""

    def __init__(self):
        self.secrets = {
            "NEWSAPI_KEY": "test-newsapi-key",
            "WORLDNEWSAPI_KEY": "test-worldnewsapi-key",
            "GNEWS_API_KEY": "test-gnews-api-key",
            "BROWSER_SERVICE_API_KEY": "test-browser-key",
            "THENEWSAPI_KEY": "test-thenewsapi-key",
        }

    def access_secret_version(self, request=None, name: str = None):
        """Mock accessing a secret."""
        secret_name = name or (request.name if request else "")
        # Extract secret ID from full path
        secret_id = secret_name.split("/")[-3] if "/versions/" in secret_name else secret_name

        payload = MagicMock()
        payload.data = self.secrets.get(secret_id, "").encode()

        response = MagicMock()
        response.payload = payload
        return response


@pytest.fixture
def mock_secret_manager():
    """Provides a mock Secret Manager client."""
    return MockSecretManager()


# ============================================================================
# SAMPLE DATA FIXTURES
# ============================================================================

@pytest.fixture
def sample_articles():
    """Provides sample article data for testing."""
    return [
        {
            "article_id": "abc123",
            "url": "https://example.com/article1",
            "original_url": "https://example.com/article1",
            "title": "Fenerbahce wins derby against Galatasaray",
            "body": "Fenerbahce defeated Galatasaray 2-1 in an exciting Istanbul derby match. " * 10,
            "source": "example.com",
            "publish_date": "2025-01-15T10:00:00Z",
            "language": "en",
            "region": "eu",
            "extraction_method": "api:newsapi",
            "source_type": "api"
        },
        {
            "article_id": "def456",
            "url": "https://example.com/article2",
            "original_url": "https://example.com/article2",
            "title": "Transfer news: New striker joins Turkish club",
            "body": "The club has confirmed the signing of a new striker from Portugal. " * 10,
            "source": "example.com",
            "publish_date": "2025-01-15T11:00:00Z",
            "language": "tr",
            "region": "tr",
            "extraction_method": "api:worldnewsapi",
            "source_type": "api"
        },
        {
            "article_id": "ghi789",
            "url": "https://sports.com/news/123",
            "original_url": "https://sports.com/news/123",
            "title": "Champions League draw results announced",
            "body": "The Champions League quarter-final draw has been completed. " * 10,
            "source": "sports.com",
            "publish_date": "2025-01-15T12:00:00Z",
            "language": "en",
            "region": "eu",
            "extraction_method": "scraped",
            "source_type": "scraped"
        }
    ]


@pytest.fixture
def sample_grouped_articles():
    """Provides sample grouped articles for merge decision testing."""
    return {
        "groups": [
            {
                "group_id": 1,
                "max_similarity": 0.92,
                "articles": [
                    {
                        "article_id": "a1",
                        "url": "https://site1.com/news",
                        "original_url": "https://site1.com/news",
                        "title": "Breaking news about transfer",
                        "body": "Full details about the transfer deal worth 50 million euros. " * 10,
                        "source": "site1.com",
                        "publish_date": "2025-01-15T10:00:00Z",
                        "language": "en",
                        "region": "eu"
                    },
                    {
                        "article_id": "a2",
                        "url": "https://site2.com/news",
                        "original_url": "https://site2.com/news",
                        "title": "Transfer news update",
                        "body": "Similar content about the transfer deal worth 50 million. " * 10,
                        "source": "site2.com",
                        "publish_date": "2025-01-15T10:30:00Z",
                        "language": "en",
                        "region": "eu"
                    }
                ]
            }
        ],
        "group_count": 1,
        "total_articles": 2,
        "source_type": "complete",
        "created_at": "2025-01-15T11:00:00Z"
    }


@pytest.fixture
def sample_singleton_articles():
    """Provides sample singleton articles for enrichment testing."""
    return {
        "articles": [
            {
                "article_id": "single1",
                "url": "https://unique.com/story",
                "original_url": "https://unique.com/story",
                "title": "Unique story about player injury",
                "body": "A detailed report about the player's injury and recovery timeline. " * 15,
                "source": "unique.com",
                "publish_date": "2025-01-15T09:00:00Z",
                "language": "en",
                "region": "eu",
                "_processing_metadata": {
                    "source_type": "complete",
                    "date": "2025-01-15",
                    "run_id": "10-00-00",
                    "group_type": "singleton"
                }
            }
        ],
        "count": 1,
        "source_type": "complete",
        "created_at": "2025-01-15T10:30:00Z"
    }


@pytest.fixture
def sample_processing_metadata():
    """Provides sample processing metadata."""
    return {
        "status": "success",
        "source_type": "complete",
        "date": "2025-01-15",
        "run_id": "10-30-00",
        "input_file": "ingestion/2025-01-15/10-30-00/complete_articles.json",
        "total_input_articles": 50,
        "prefilter_removed": 5,
        "cross_run_removed": 3,
        "articles_after_dedup": 42,
        "singleton_count": 30,
        "group_count": 4,
        "grouped_article_count": 12,
        "thresholds": {
            "cross_run_dedup_tr": 0.85,
            "cross_run_dedup_eu": 0.9,
            "grouping": 0.8
        },
        "created_at": "2025-01-15T10:35:00Z"
    }


@pytest.fixture
def sample_dedup_log():
    """Provides sample deduplication log."""
    return {
        "dropped_articles": [
            {
                "article_id": "dup1",
                "title": "Transfer news about player",
                "url": "https://example.com/dup1",
                "matched_article_url": "https://other.com/original",
                "region": "tr",
                "max_similarity": 0.91,
                "threshold": 0.85,
                "reason": "cross_run_duplicate"
            },
            {
                "article_id": "dup2",
                "title": "Same story different source",
                "url": "https://example.com/dup2",
                "matched_article_url": "https://other.com/original2",
                "region": "eu",
                "max_similarity": 0.95,
                "threshold": 0.9,
                "reason": "cross_run_duplicate"
            }
        ],
        "count": 2,
        "region_thresholds": {"tr": 0.85, "eu": 0.9},
        "created_at": "2025-01-15T10:35:00Z"
    }


# ============================================================================
# ENVIRONMENT FIXTURES
# ============================================================================

@pytest.fixture
def env_local(monkeypatch):
    """Set environment to local mode."""
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GCS_BUCKET_NAME", "test-bucket")
    monkeypatch.setenv("VERTEX_AI_LOCATION", "us-central1")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-004")
    monkeypatch.setenv("CROSS_RUN_DEDUP_THRESHOLD_TR", "0.85")
    monkeypatch.setenv("CROSS_RUN_DEDUP_THRESHOLD_EU", "0.9")
    monkeypatch.setenv("CROSS_RUN_DEDUP_DEPTH", "3")
    monkeypatch.setenv("GROUPING_THRESHOLD", "0.8")


@pytest.fixture
def env_cloud(monkeypatch):
    """Set environment to cloud mode."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GCS_BUCKET_NAME", "aisports-scraping")
    monkeypatch.setenv("VERTEX_AI_LOCATION", "us-central1")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-004")
    monkeypatch.setenv("CROSS_RUN_DEDUP_THRESHOLD_TR", "0.85")
    monkeypatch.setenv("CROSS_RUN_DEDUP_THRESHOLD_EU", "0.9")
    monkeypatch.setenv("CROSS_RUN_DEDUP_DEPTH", "3")
    monkeypatch.setenv("GROUPING_THRESHOLD", "0.8")


# ============================================================================
# HELPER FIXTURES
# ============================================================================

@pytest.fixture
def fixtures_dir():
    """Returns path to fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_data_dir(fixtures_dir):
    """Returns path to sample_data directory."""
    return fixtures_dir / "sample_data"


def load_fixture(fixtures_dir: Path, filename: str) -> dict:
    """Helper to load a JSON fixture file."""
    filepath = fixtures_dir / "sample_data" / filename
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return {}


@pytest.fixture
def load_json_fixture(fixtures_dir):
    """Factory fixture to load JSON fixture files."""
    def _load(filename: str) -> dict:
        return load_fixture(fixtures_dir, filename)
    return _load
