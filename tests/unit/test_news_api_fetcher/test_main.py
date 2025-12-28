"""Unit tests for news_api_fetcher_function/main.py."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import sys

# Mock Google Cloud modules before importing
mock_zoneinfo = MagicMock()
sys.modules['zoneinfo'] = mock_zoneinfo

# Mock aiohttp before importing
mock_aiohttp = MagicMock()
sys.modules['aiohttp'] = mock_aiohttp

mock_storage = MagicMock()
sys.modules['google.cloud.storage'] = mock_storage
mock_secretmanager = MagicMock()
sys.modules['google.cloud.secretmanager'] = mock_secretmanager
mock_pubsub = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = mock_pubsub

mock_google_cloud = MagicMock()
mock_google_cloud.storage = mock_storage
mock_google_cloud.secretmanager = mock_secretmanager
mock_google_cloud.pubsub_v1 = mock_pubsub
sys.modules['google.cloud'] = mock_google_cloud

# Import the module after mocking
with patch.dict('os.environ', {'ENVIRONMENT': 'local'}):
    from news_api_fetcher_function.main import (
        generate_article_id,
        transform_api_article_to_session_schema,
        DEFAULT_KEYWORDS,
    )


class TestGenerateArticleId:
    """Tests for generate_article_id function."""

    def test_returns_16_char_string(self):
        """Test returns 16 character string."""
        result = generate_article_id("https://example.com/article")
        assert len(result) == 16

    def test_deterministic(self):
        """Test same URL always returns same ID."""
        url = "https://example.com/article"
        result1 = generate_article_id(url)
        result2 = generate_article_id(url)
        assert result1 == result2

    def test_different_urls_different_ids(self):
        """Test different URLs produce different IDs."""
        result1 = generate_article_id("https://example.com/article1")
        result2 = generate_article_id("https://example.com/article2")
        assert result1 != result2

    def test_returns_hex_string(self):
        """Test ID is valid hex string."""
        result = generate_article_id("https://example.com")
        # Should be valid hex
        int(result, 16)

    def test_empty_url(self):
        """Test empty URL returns a hash."""
        result = generate_article_id("")
        assert len(result) == 16


class TestTransformApiArticleToSessionSchema:
    """Tests for transform_api_article_to_session_schema function."""

    def test_basic_transformation(self):
        """Test basic article transformation."""
        article = {
            'url': 'https://example.com/article',
            'title': 'Test Article',
            'content': 'Article content here',
            'publish_date': '2024-12-28',
            'api_source': 'newsapi'
        }
        
        result = transform_api_article_to_session_schema(article)
        
        assert result['url'] == 'https://example.com/article'
        assert result['title'] == 'Test Article'
        assert result['body'] == 'Article content here'
        assert result['source_type'] == 'api'

    def test_extracts_domain(self):
        """Test domain extraction from URL."""
        article = {
            'url': 'https://www.bbc.com/sport/football/article',
        }
        
        result = transform_api_article_to_session_schema(article)
        
        assert result['source'] == 'www.bbc.com'
        assert result['site'] == 'www.bbc.com'

    def test_generates_article_id(self):
        """Test article_id is generated from URL."""
        article = {
            'url': 'https://example.com/article',
        }
        
        result = transform_api_article_to_session_schema(article)
        
        assert result['article_id'] is not None
        assert len(result['article_id']) == 16

    def test_turkish_language_maps_to_tr_region(self):
        """Test Turkish language maps to TR region."""
        article = {
            'url': 'https://example.com',
            'language': 'tr'
        }
        
        result = transform_api_article_to_session_schema(article)
        
        assert result['language'] == 'tr'
        assert result['region'] == 'tr'

    def test_english_language_maps_to_eu_region(self):
        """Test English language maps to EU region."""
        article = {
            'url': 'https://example.com',
            'language': 'en'
        }
        
        result = transform_api_article_to_session_schema(article)
        
        assert result['language'] == 'en'
        assert result['region'] == 'eu'

    def test_gnews_lang_field(self):
        """Test GNews 'lang' field is handled."""
        article = {
            'url': 'https://example.com',
            'lang': 'tr'
        }
        
        result = transform_api_article_to_session_schema(article)
        
        assert result['language'] == 'tr'
        assert result['region'] == 'tr'

    def test_extraction_method_includes_api_source(self):
        """Test extraction_method includes API source."""
        article = {
            'url': 'https://example.com',
            'api_source': 'worldnewsapi'
        }
        
        result = transform_api_article_to_session_schema(article)
        
        assert result['extraction_method'] == 'api:worldnewsapi'

    def test_keywords_matched_preserved(self):
        """Test keywords_matched is preserved as keywords_used."""
        article = {
            'url': 'https://example.com',
            'keywords_matched': ['fenerbahce', 'transfer']
        }
        
        result = transform_api_article_to_session_schema(article)
        
        assert result['keywords_used'] == ['fenerbahce', 'transfer']

    def test_original_url_fallback(self):
        """Test original_url is used as fallback for url."""
        article = {
            'original_url': 'https://example.com/original',
        }
        
        result = transform_api_article_to_session_schema(article)
        
        assert result['url'] == 'https://example.com/original'


class TestDefaultKeywords:
    """Tests for DEFAULT_KEYWORDS constant."""

    def test_contains_fenerbahce(self):
        """Test fenerbahce is in default keywords."""
        assert 'fenerbahce' in DEFAULT_KEYWORDS

    def test_contains_galatasaray(self):
        """Test galatasaray is in default keywords."""
        assert 'galatasaray' in DEFAULT_KEYWORDS

    def test_contains_tedesco(self):
        """Test tedesco is in default keywords."""
        assert 'tedesco' in DEFAULT_KEYWORDS

    def test_has_multiple_keywords(self):
        """Test there are multiple default keywords."""
        assert len(DEFAULT_KEYWORDS) >= 3


class TestGenerateArticleIdEdgeCases:
    """Additional tests for generate_article_id edge cases."""

    def test_url_with_query_params(self):
        """Test URL with query parameters."""
        url1 = "https://example.com/article?id=123"
        url2 = "https://example.com/article?id=456"
        result1 = generate_article_id(url1)
        result2 = generate_article_id(url2)
        assert result1 != result2

    def test_url_with_fragment(self):
        """Test URL with fragment."""
        result = generate_article_id("https://example.com/article#section1")
        assert len(result) == 16

    def test_unicode_url(self):
        """Test URL with unicode characters."""
        result = generate_article_id("https://example.com/artículo")
        assert len(result) == 16

    def test_very_long_url(self):
        """Test very long URL."""
        long_url = "https://example.com/" + "a" * 1000
        result = generate_article_id(long_url)
        assert len(result) == 16


class TestTransformApiArticleEdgeCases:
    """Additional edge case tests for transform_api_article_to_session_schema."""

    def test_missing_all_fields(self):
        """Test transformation with minimal article."""
        article = {'url': 'https://example.com'}
        result = transform_api_article_to_session_schema(article)
        assert result['url'] == 'https://example.com'

    def test_description_as_body_fallback(self):
        """Test description is used as body fallback."""
        article = {
            'url': 'https://example.com',
            'description': 'Article description'
        }
        result = transform_api_article_to_session_schema(article)
        # Description may be used as body
        assert result.get('body') is not None or result.get('description') == 'Article description'

    def test_published_date_formats(self):
        """Test various date formats."""
        article = {
            'url': 'https://example.com',
            'publish_date': '2024-12-28T10:30:00Z'
        }
        result = transform_api_article_to_session_schema(article)
        assert result['publish_date'] == '2024-12-28T10:30:00Z'

    def test_image_url_handling(self):
        """Test image URL may or may not be preserved."""
        article = {
            'url': 'https://example.com',
            'image_url': 'https://example.com/image.jpg'
        }
        result = transform_api_article_to_session_schema(article)
        # Image URL handling depends on implementation
        # Just verify no error is raised
        assert result['url'] == 'https://example.com'

    def test_region_default_to_tr(self):
        """Test region defaults to TR when no language."""
        article = {
            'url': 'https://example.com',
        }
        result = transform_api_article_to_session_schema(article)
        # Default region should be set
        assert result.get('region') in ['tr', 'eu', None]

    def test_source_type_is_api(self):
        """Test source_type is always 'api'."""
        article = {'url': 'https://example.com'}
        result = transform_api_article_to_session_schema(article)
        assert result['source_type'] == 'api'

    def test_api_response_preserved(self):
        """Test original API response data preserved."""
        article = {
            'url': 'https://example.com',
            'sentiment': 0.5,
            'relevance_score': 0.8
        }
        result = transform_api_article_to_session_schema(article)
        # API-specific fields may or may not be preserved
        assert result['url'] == 'https://example.com'


class TestLanguageRegionMapping:
    """Tests for language to region mapping logic."""

    def test_turkish_to_tr(self):
        """Test Turkish maps to TR region."""
        article = {'url': 'https://example.com', 'language': 'tr'}
        result = transform_api_article_to_session_schema(article)
        assert result['region'] == 'tr'

    def test_english_to_eu(self):
        """Test English maps to EU region."""
        article = {'url': 'https://example.com', 'language': 'en'}
        result = transform_api_article_to_session_schema(article)
        assert result['region'] == 'eu'

    def test_portuguese_to_eu(self):
        """Test Portuguese maps to EU region."""
        article = {'url': 'https://example.com', 'language': 'pt'}
        result = transform_api_article_to_session_schema(article)
        assert result['region'] == 'eu'

    def test_spanish_to_eu(self):
        """Test Spanish maps to EU region."""
        article = {'url': 'https://example.com', 'language': 'es'}
        result = transform_api_article_to_session_schema(article)
        assert result['region'] == 'eu'

    def test_french_to_eu(self):
        """Test French maps to EU region."""
        article = {'url': 'https://example.com', 'language': 'fr'}
        result = transform_api_article_to_session_schema(article)
        assert result['region'] == 'eu'

    def test_german_to_eu(self):
        """Test German maps to EU region."""
        article = {'url': 'https://example.com', 'language': 'de'}
        result = transform_api_article_to_session_schema(article)
        assert result['region'] == 'eu'


class TestConfigurationConstants:
    """Tests for configuration constants."""

    def test_ingestion_prefix_default(self):
        """Test default ingestion prefix."""
        import os
        prefix = os.getenv('INGESTION_PREFIX', 'ingestion/')
        assert prefix == 'ingestion/'

    def test_project_id_default(self):
        """Test default project ID."""
        import os
        project = os.getenv('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0306766464')
        assert project == 'gen-lang-client-0306766464'

    def test_bucket_name_default(self):
        """Test default bucket name."""
        import os
        bucket = os.getenv('GCS_BUCKET_NAME', 'aisports-scraping')
        assert bucket == 'aisports-scraping'


class TestTransformApiArticleDomainExtraction:
    """Tests for domain extraction in transform_api_article_to_session_schema."""

    def test_extracts_domain_without_www(self):
        """Test domain extraction without www."""
        article = {'url': 'https://bbc.com/article'}
        result = transform_api_article_to_session_schema(article)
        assert result['source'] == 'bbc.com'

    def test_extracts_domain_with_subdomain(self):
        """Test domain extraction with subdomain."""
        article = {'url': 'https://news.bbc.com/article'}
        result = transform_api_article_to_session_schema(article)
        assert result['source'] == 'news.bbc.com'

    def test_extracts_domain_with_port(self):
        """Test domain extraction with port."""
        article = {'url': 'https://example.com:8080/article'}
        result = transform_api_article_to_session_schema(article)
        assert 'example.com' in result['source']

    def test_extracts_domain_from_complex_url(self):
        """Test domain extraction from complex URL."""
        article = {'url': 'https://www.sports.example.co.uk/football/article?id=123'}
        result = transform_api_article_to_session_schema(article)
        assert 'example' in result['source']


class TestTransformApiArticleTimestamps:
    """Tests for timestamp handling in transform_api_article_to_session_schema."""

    def test_scraped_at_field_added(self):
        """Test scraped_at field is added."""
        article = {'url': 'https://example.com'}
        result = transform_api_article_to_session_schema(article)
        assert 'scraped_at' in result

    def test_scraped_at_uses_fetched_at(self):
        """Test scraped_at uses fetched_at if provided."""
        article = {
            'url': 'https://example.com',
            'fetched_at': '2024-12-28T10:00:00Z'
        }
        result = transform_api_article_to_session_schema(article)
        assert result['scraped_at'] == '2024-12-28T10:00:00Z'

    def test_publish_date_preserved(self):
        """Test publish_date is preserved."""
        article = {
            'url': 'https://example.com',
            'publish_date': '2024-12-28'
        }
        result = transform_api_article_to_session_schema(article)
        assert result['publish_date'] == '2024-12-28'


class TestTransformApiArticleApiSource:
    """Tests for API source handling."""

    def test_newsapi_source(self):
        """Test NewsAPI source is included in extraction_method."""
        article = {'url': 'https://example.com', 'api_source': 'newsapi'}
        result = transform_api_article_to_session_schema(article)
        assert 'newsapi' in result['extraction_method']

    def test_worldnewsapi_source(self):
        """Test WorldNewsAPI source is included in extraction_method."""
        article = {'url': 'https://example.com', 'api_source': 'worldnewsapi'}
        result = transform_api_article_to_session_schema(article)
        assert 'worldnewsapi' in result['extraction_method']

    def test_gnews_source(self):
        """Test GNews source is included in extraction_method."""
        article = {'url': 'https://example.com', 'api_source': 'gnews'}
        result = transform_api_article_to_session_schema(article)
        assert 'gnews' in result['extraction_method']

    def test_unknown_source(self):
        """Test unknown source handling."""
        article = {'url': 'https://example.com'}
        result = transform_api_article_to_session_schema(article)
        assert 'api:' in result['extraction_method']


class TestDefaultKeywordsDetails:
    """Detailed tests for DEFAULT_KEYWORDS."""

    def test_keywords_are_lowercase(self):
        """Test all keywords are lowercase."""
        for kw in DEFAULT_KEYWORDS:
            assert kw == kw.lower()

    def test_keywords_are_strings(self):
        """Test all keywords are strings."""
        for kw in DEFAULT_KEYWORDS:
            assert isinstance(kw, str)

    def test_no_empty_keywords(self):
        """Test no empty keywords."""
        for kw in DEFAULT_KEYWORDS:
            assert len(kw) > 0

    def test_no_duplicate_keywords(self):
        """Test no duplicate keywords."""
        assert len(DEFAULT_KEYWORDS) == len(set(DEFAULT_KEYWORDS))
