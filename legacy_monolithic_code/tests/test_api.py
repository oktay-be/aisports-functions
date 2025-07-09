"""
Integration tests for API-like functionalities by directly calling service methods.
"""
import json
import sys
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock, call # Added call
import asyncio
from datetime import datetime

from capabilities.news_aggregator import NewsAggregator


@patch('capabilities.news_aggregator.NewsAggregator.fetch_from_source', new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_get_news(mock_fetch_from_source, tmp_path):
    """Test fetching news (simulating /api/news route)."""
    session_id = "test_session_get_news"
    query_param = ["fenerbahçe"]
    workspace_dir = tmp_path / "workspace"
    os.makedirs(workspace_dir, exist_ok=True)
    cache_dir = tmp_path / "cache_news_aggregator"
    os.makedirs(cache_dir, exist_ok=True)

    limit_param = 1
    sources_param = ["newsapi"]

    # Mock the fetch_from_source to return sample articles
    mock_articles = [
        {
            "title": "Fenerbahçe wins important match",
            "url": "https://example.com/news/1",
            "source": "Example News",
            "published_at": "2025-05-24T12:00:00Z",
            "content": "Fenerbahçe won an important match yesterday."
        }
    ]
    mock_fetch_from_source.return_value = mock_articles

    # Instantiate NewsAggregator
    aggregator = NewsAggregator(newsapi_key="test_key", cache_dir=str(cache_dir))

    returned_article_paths = await aggregator.fetch_news_for_session(
        session_id=session_id,
        base_workspace_path=str(workspace_dir),
        query=query_param,
        sources=sources_param,
        limit=limit_param
    )

    # Assert that the mock was called correctly
    mock_fetch_from_source.assert_called_once_with("newsapi")
    
    # The method should return a list of file paths where articles were saved
    assert isinstance(returned_article_paths, list)
    assert len(returned_article_paths) == limit_param


@patch('journalist.Journalist.read', new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_scrape_news(mock_journalist_read, tmp_path):
    """Test scraping news using journalist library (simulating /api/scrape route)."""
    session_id = "test_session_scrape_news"
    keywords = ["testkeyword"]
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    
    # Mock the return value from journalist.read
    mock_scraped_article_1 = {
        "url": "https://example.com/news/1", 
        "title": "Article 1 Title", 
        "content": "Content of article 1", 
        "scraped_at": datetime.now().isoformat(), 
        "site": "example.com", 
        "keywords_used": keywords
    }
    mock_scraped_article_2 = {
        "url": "https://example.com/news/2", 
        "title": "Article 2 Title", 
        "content": "Content of article 2",
        "scraped_at": datetime.now().isoformat(), 
        "site": "example.com", 
        "keywords_used": keywords
    }
    
    # Mock the session data return format (journalist returns a list of source sessions)
    mock_session_data = [
        {
            'source_domain': 'example.com',
            'source_url': 'https://example.com',
            'articles': [mock_scraped_article_1, mock_scraped_article_2],
            'articles_count': 2,
            'session_metadata': {
                'session_id': session_id,
                'start_time': datetime.now().isoformat(),
                'end_time': datetime.now().isoformat(),
                'duration_seconds': 1.5,
                'total_links_processed': 2,
                'keywords_used': keywords
            }
        }
    ]
    
    mock_journalist_read.return_value = mock_session_data
    
    # Create journalist instance and call the method
    from journalist import Journalist
    journalist = Journalist(persist=False)
    urls = ["https://example.com"]
    
    # Call the method with journalist API
    scraped_data = await journalist.read(urls=urls, keywords=keywords)

    # Verify the mocked method was called
    mock_journalist_read.assert_called_once_with(
        urls=urls,
        keywords=keywords
    )
    
    # Verify the return data structure (journalist returns list of source sessions)
    assert scraped_data == mock_session_data
    assert isinstance(scraped_data, list)
    assert len(scraped_data) == 1
    assert 'articles' in scraped_data[0]
    assert 'session_metadata' in scraped_data[0]
    assert len(scraped_data[0]['articles']) == 2
    assert scraped_data[0]['session_metadata']['session_id'] == session_id
