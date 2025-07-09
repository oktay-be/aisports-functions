"""
Unit tests for PyMongo async MongoDB client implementation.
Tests all database operations including post management and article retrieval.
"""

import pytest
import pytest_asyncio
import asyncio
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, List

# Try to import the MongoDB client
try:
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from database.mongodb_client import MongoDBClient
    MONGODB_CLIENT_AVAILABLE = True
except ImportError:
    MONGODB_CLIENT_AVAILABLE = False


@pytest.mark.skipif(not MONGODB_CLIENT_AVAILABLE, reason="MongoDB client not available")
class TestMongoDBClient:
    """Test MongoDB client functionality."""
    
    @pytest.fixture
    def mock_client(self):
        """Create a mocked MongoDB client for testing."""
        with patch('database.mongodb_client.AsyncMongoClient') as mock_pymongo:
            client = MongoDBClient("mongodb://test:27017", "test_db")
            
            # Mock the database and collections  
            mock_db = Mock()
            mock_pymongo_instance = Mock()
            mock_pymongo_instance.admin.command = AsyncMock(return_value=True)
            mock_pymongo_instance.__getitem__ = Mock(return_value=mock_db)
            mock_pymongo_instance.close = AsyncMock()
            mock_pymongo.return_value = mock_pymongo_instance
              # Setup collection mocking
            def mock_get_collection(collection_name):
                """Mock collection getter for database"""
                mock_collection = Mock()
                mock_collection.insert_one = AsyncMock()
                mock_collection.find_one = AsyncMock()
                mock_collection.find = Mock()
                mock_collection.update_one = AsyncMock()
                mock_collection.create_index = AsyncMock()
                mock_collection.aggregate = Mock()
                mock_collection.count_documents = AsyncMock()
                return mock_collection
            
            # Create a side_effect function that ignores self parameter
            mock_db.__getitem__ = Mock(side_effect=lambda collection_name: mock_get_collection(collection_name))
            client.client = mock_pymongo_instance
            client.db = mock_db
            client._connected = True
            
            return client, mock_db
    
    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test MongoDB client initialization."""
        client = MongoDBClient()        
        assert client.connection_string == "mongodb://localhost:27017"
        assert client.database_name == "aisports"
        assert client.AI_POSTS == "ai_posts"
        assert client.AI_SUMMARIES_PER_SOURCE == "ai_summaries_per_source"
    
    @pytest.mark.asyncio
    async def test_save_prepared_post(self, mock_client):
        """Test saving a prepared social media post."""
        client, mock_db = mock_client
        
        # Set up the collection mock directly
        mock_result = Mock()
        mock_result.inserted_id = "test_object_id"
          # Patch the specific collection access
        with patch.object(client.db, '__getitem__') as mock_get_collection:
            mock_collection = Mock()
            mock_collection.insert_one = AsyncMock(return_value=mock_result)
            mock_get_collection.return_value = mock_collection
            
            post_data = {
                "post_id": "post_20250624_001",
                "based_on_articles": ["article_1"],
                "post_content": {
                    "text": "Test post content",
                    "hashtags": ["#test"],
                    "mentions": ["@test"],
                    "character_count": 17
                },
                "post_status": "prepared"
            }
            
            result = await client.save_prepared_post(post_data)
            
            assert result == "test_object_id"
            mock_collection.insert_one.assert_called_once()
            
            # Verify that created_at was added
            call_args = mock_collection.insert_one.call_args[0][0]
            assert "created_at" in call_args
            assert isinstance(call_args["created_at"], datetime)
    
    @pytest.mark.asyncio
    async def test_get_prepared_posts(self, mock_client):
        """Test retrieving prepared posts."""
        client, mock_db = mock_client
        
        # Mock posts data
        mock_posts = [
            {
                "post_id": "post_001",
                "post_status": "prepared",
                "created_at": datetime.now(timezone.utc)
            },
            {
                "post_id": "post_002", 
                "post_status": "published",
                "created_at": datetime.now(timezone.utc)
            }
        ]
        
        # Create a proper async mock cursor chain
        mock_cursor = Mock()
        mock_cursor.sort = Mock(return_value=mock_cursor)
        mock_cursor.limit = Mock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=mock_posts)
        
        # Create collection mock
        mock_collection = Mock()
        mock_collection.find = Mock(return_value=mock_cursor)
        
        # Setup the database mock to return our collection for ai_posts
        with patch.object(client.db, '__getitem__') as mock_get_collection:
            mock_get_collection.return_value = mock_collection
            
            # Test without status filter
            result = await client.get_prepared_posts(limit=5)
            
            assert len(result) == 2
            mock_collection.find.assert_called_with({})
            mock_cursor.sort.assert_called_with("created_at", -1)
            mock_cursor.limit.assert_called_with(5)
            mock_cursor.to_list.assert_called_with(length=5)
              # Test with status filter
            mock_collection.find.reset_mock()  # Reset mock to clear previous calls
            await client.get_prepared_posts(limit=5, status="prepared")
            mock_collection.find.assert_called_with({"post_status": "prepared"})
    
    @pytest.mark.asyncio
    async def test_update_post_status(self, mock_client):
        """Test updating post status."""
        client, mock_db = mock_client
        
        # Mock the update_one method (async)
        mock_collection = Mock()
        mock_result = Mock()
        mock_result.modified_count = 1
        mock_collection.update_one = AsyncMock(return_value=mock_result)
        
        # Setup the database mock
        with patch.object(client.db, '__getitem__') as mock_get_collection:
            mock_get_collection.return_value = mock_collection
            
            # Test publishing a post
            result = await client.update_post_status("post_001", "published", "x_12345")
            
            assert result is True
            mock_collection.update_one.assert_called_once()
            
            call_args = mock_collection.update_one.call_args
            query = call_args[0][0]
            update_data = call_args[0][1]["$set"]
            
            assert query == {"post_id": "post_001"}
            assert update_data["post_status"] == "published"
            assert update_data["x_post_id"] == "x_12345"
            assert "published_at" in update_data
            assert "updated_at" in update_data
    
    @pytest.mark.asyncio
    async def test_get_posts_by_articles(self, mock_client):
        """Test retrieving posts based on articles."""
        client, mock_db = mock_client
        
        # Mock posts data
        mock_posts = [
            {
                "post_id": "post_001",
                "based_on_articles": ["article_1", "article_2"]
            }
        ]
        
        # Create proper async mock cursor chain
        mock_cursor = Mock()
        mock_cursor.sort = Mock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=mock_posts)
        
        # Create collection mock
        mock_collection = Mock()
        mock_collection.find = Mock(return_value=mock_cursor)
          # Setup the database mock
        with patch.object(client.db, '__getitem__') as mock_get_collection:
            mock_get_collection.return_value = mock_collection
            
            article_ids = ["article_1", "article_3"]
            result = await client.get_posts_by_articles(article_ids)
            assert len(result) == 1
            mock_collection.find.assert_called_with({
                "based_on_articles": {"$in": article_ids}
            })
            mock_cursor.sort.assert_called_with("created_at", -1)

    @pytest.mark.asyncio
    async def test_get_articles_by_source(self, mock_client):
        """Test retrieving articles from a specific source."""
        client, mock_db = mock_client
        
        # Mock summary data
        mock_summary = {
            "run_id": "test_run",
            "source_domain": "www_test_com",
            "summary_data": {
                "processed_articles": [
                    {
                        "id": "article_1",
                        "title": "Test Article",
                        "source": "www_test_com"
                    },
                    {
                        "id": "article_2", 
                        "title": "Another Article",
                        "source": "www_test_com"
                    }
                ]
            }
        }
        
        # Create collection mock
        mock_collection = Mock()
        mock_collection.find_one = AsyncMock(return_value=mock_summary)
          # Setup the database mock
        with patch.object(client.db, '__getitem__') as mock_get_collection:
            mock_get_collection.return_value = mock_collection
            
            result = await client.get_articles_by_source("test_run", "www_test_com")
            
            assert len(result) == 2
            assert result[0]["id"] == "article_1"
            assert result[1]["id"] == "article_2"
            mock_collection.find_one.assert_called_with({
                "run_id": "test_run",
                "source_domain": "www_test_com"
            })

    @pytest.mark.asyncio
    async def test_get_articles_by_source_not_found(self, mock_client):
        """Test retrieving articles when source not found."""
        client, mock_db = mock_client
        
        # Create collection mock
        mock_collection = Mock()
        mock_collection.find_one = AsyncMock(return_value=None)
          # Setup the database mock
        with patch.object(client.db, '__getitem__') as mock_get_collection:
            mock_get_collection.return_value = mock_collection
            
            result = await client.get_articles_by_source("test_run", "www_nonexistent_com")
            
            assert result == []

    @pytest.mark.asyncio
    async def test_search_articles(self, mock_client):
        """Test searching articles across runs."""
        client, mock_db = mock_client
        
        # Mock articles data
        mock_articles = [
            {
                "id": "article_1",
                "title": "Fenerbahçe Transfer News",
                "summary": "Transfer news about Fenerbahçe"
            },
            {
                "id": "article_2",
                "title": "Football Update",
                "summary": "General football news"
            }
        ]
        
        # Create proper async mock cursor
        mock_cursor = Mock()
        mock_cursor.to_list = AsyncMock(return_value=mock_articles)
        
        # Create collection mock
        mock_collection = Mock()
        mock_collection.aggregate = Mock(return_value=mock_cursor)
        
        # Setup the database mock
        with patch.object(client.db, '__getitem__') as mock_get_collection:
            mock_get_collection.return_value = mock_collection
            
            result = await client.search_articles("fenerbahce")
            
            assert len(result) == 2
            mock_collection.aggregate.assert_called_once()              # Verify the aggregation pipeline
            pipeline = mock_collection.aggregate.call_args[0][0]
            assert any("$unwind" in stage for stage in pipeline)
            assert any("$match" in stage for stage in pipeline)
            assert any("$replaceRoot" in stage for stage in pipeline)

    @pytest.mark.asyncio
    async def test_save_collection_run(self, mock_client):
        """Test saving a collection run."""
        client, mock_db = mock_client
        
        # Mock result object
        mock_result = Mock()
        mock_result.inserted_id = "test_object_id"
        
        # Create collection mock
        mock_collection = Mock()
        mock_collection.insert_one = AsyncMock(return_value=mock_result)
        
        # Setup the database mock
        with patch.object(client.db, '__getitem__') as mock_get_collection:
            mock_get_collection.return_value = mock_collection
            
            run_data = {
                "run_id": "test_run_123",
                "run_type": "full_collection",
                "status": "running",
                "parameters": {
                    "keywords": ["fenerbahce", "test"],
                    "regions": ["TR", "EU"]
                }
            }
            
            result = await client.save_collection_run(run_data)
            
            assert result == "test_run_123"
            mock_collection.insert_one.assert_called_once()
            
            # Verify that created_at was added
            call_args = mock_collection.insert_one.call_args[0][0]
            assert "created_at" in call_args
            assert isinstance(call_args["created_at"], datetime)

    @pytest.mark.asyncio
    async def test_save_source_summary(self, mock_client):
        """Test saving source summary data."""
        client, mock_db = mock_client
        
        # Mock result object
        mock_result = Mock()
        mock_result.inserted_id = "test_object_id"
        
        # Create collection mock
        mock_collection = Mock()
        mock_collection.insert_one = AsyncMock(return_value=mock_result)
        
        # Setup the database mock
        with patch.object(client.db, '__getitem__') as mock_get_collection:
            mock_get_collection.return_value = mock_collection
            
            summary_data = {
                "run_id": "test_run",                "source_domain": "www_test_com",
                "region": "TR",
                "summary_data": {
                    "processing_summary": {"total_articles": 5},
                    "processed_articles": []
                }
            }
            
            result = await client.save_source_summary(summary_data)
            
            assert result == "test_object_id"
            mock_collection.insert_one.assert_called_once()
            
            # Verify that created_at was added
            call_args = mock_collection.insert_one.call_args[0][0]
            assert "created_at" in call_args

    @pytest.mark.asyncio
    async def test_error_handling(self, mock_client):
        """Test error handling in database operations."""
        client, mock_db = mock_client
        
        # Create collection mock that raises an exception
        mock_collection = Mock()
        mock_collection.insert_one = AsyncMock(side_effect=Exception("Database error"))
        
        # Setup the database mock
        with patch.object(client.db, '__getitem__') as mock_get_collection:
            mock_get_collection.return_value = mock_collection
            
            # Test that exceptions are properly handled
            with pytest.raises(Exception):
                await client.save_prepared_post({"test": "data"})
        
        # Test methods that return empty results on error
        mock_cursor = Mock()
        mock_cursor.to_list = AsyncMock(side_effect=Exception("Database error"))
        mock_collection.find = Mock(return_value=mock_cursor)
        
        with patch.object(client.db, '__getitem__') as mock_get_collection:
            mock_get_collection.return_value = mock_collection
            
            result = await client.get_prepared_posts()
            assert result == []
        
        # Test find_one error handling
        mock_collection.find_one = AsyncMock(side_effect=Exception("Database error"))
        
        with patch.object(client.db, '__getitem__') as mock_get_collection:
            mock_get_collection.return_value = mock_collection
            
            result = await client.get_articles_by_source("test", "test")
            assert result == []


@pytest.mark.skipif(not MONGODB_CLIENT_AVAILABLE, reason="MongoDB client not available")
class TestMongoDBClientIntegration:
    """Integration tests for MongoDB client (requires running MongoDB)."""
    
    @pytest_asyncio.fixture
    async def real_client(self):
        """Create a real MongoDB client for integration testing."""
        # Only run if MongoDB is available and MONGODB_TEST_URI is set
        test_uri = os.getenv("MONGODB_TEST_URI", "mongodb://localhost:27017")
        
        client = MongoDBClient(test_uri, "aisports_test")
        connected = await client.connect()
        
        if not connected:
            pytest.skip("Could not connect to test MongoDB")
        
        yield client
        
        # Cleanup: disconnect
        await client.disconnect()
    
    @pytest.mark.asyncio
    async def test_real_database_operations(self, real_client):
        """Test actual database operations against a real MongoDB instance."""
        client = real_client
        
        # Test saving a collection run
        run_data = {
            "run_id": f"integration_test_{int(datetime.now().timestamp())}",
            "run_type": "full_collection", 
            "status": "running",
            "parameters": {
                "keywords": ["test"],
                "regions": ["TR"]
            }
        }
        
        run_id = await client.save_collection_run(run_data)
        assert run_id == run_data["run_id"]
        
        # Test updating run status
        updated = await client.update_collection_run_status(run_id, "completed")
        assert updated is True
        
        # Test retrieving the run
        retrieved_run = await client.get_collection_run(run_id)
        assert retrieved_run is not None
        assert retrieved_run["status"] == "completed"
        
        print("✅ Integration tests passed")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
