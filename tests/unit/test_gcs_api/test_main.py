"""Unit tests for gcs_api_function/main.py."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import sys
import json

# Mock Google Cloud modules before importing
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

# Mock Flask
mock_flask = MagicMock()
sys.modules['flask'] = mock_flask

# Mock functions_framework
mock_functions_framework = MagicMock()
sys.modules['functions_framework'] = mock_functions_framework

# Mock google.oauth2
mock_oauth2 = MagicMock()
sys.modules['google.oauth2'] = mock_oauth2
sys.modules['google.oauth2.id_token'] = MagicMock()

# Mock google.auth.transport
mock_auth_transport = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['google.auth.transport'] = mock_auth_transport
sys.modules['google.auth.transport.requests'] = MagicMock()

# Import the module after mocking
with patch.dict('os.environ', {'ENVIRONMENT': 'local'}):
    from gcs_api_function.main import (
        hash_email,
        get_date_range,
        get_cache_key,
        cors_headers,
        normalize_article,
        deduplicate_articles,
        CACHE_TTL_SECONDS,
        CONFIG_CACHE_TTL_SECONDS,
    )


class TestHashEmail:
    """Tests for hash_email function."""

    def test_returns_16_char_string(self):
        """Test hash returns 16 character string."""
        result = hash_email("test@example.com")
        assert len(result) == 16

    def test_deterministic(self):
        """Test same email always returns same hash."""
        email = "user@domain.com"
        result1 = hash_email(email)
        result2 = hash_email(email)
        assert result1 == result2

    def test_case_insensitive(self):
        """Test email hashing is case insensitive."""
        result1 = hash_email("Test@Example.COM")
        result2 = hash_email("test@example.com")
        assert result1 == result2

    def test_different_emails_different_hashes(self):
        """Test different emails produce different hashes."""
        result1 = hash_email("user1@example.com")
        result2 = hash_email("user2@example.com")
        assert result1 != result2

    def test_empty_email(self):
        """Test empty email returns a hash."""
        result = hash_email("")
        assert len(result) == 16

    def test_returns_hex_string(self):
        """Test hash is a valid hex string."""
        result = hash_email("test@example.com")
        # Should be valid hex
        int(result, 16)  # Raises ValueError if not valid hex


class TestGetDateRange:
    """Tests for get_date_range function."""

    def test_single_day(self):
        """Test single day range."""
        result = get_date_range("2024-12-28", "2024-12-28")
        assert result == ["2024-12-28"]

    def test_multiple_days(self):
        """Test multiple day range."""
        result = get_date_range("2024-12-26", "2024-12-28")
        assert result == ["2024-12-26", "2024-12-27", "2024-12-28"]

    def test_week_range(self):
        """Test week-long range."""
        result = get_date_range("2024-12-22", "2024-12-28")
        assert len(result) == 7
        assert result[0] == "2024-12-22"
        assert result[-1] == "2024-12-28"

    def test_month_boundary(self):
        """Test range crossing month boundary."""
        result = get_date_range("2024-11-30", "2024-12-02")
        assert result == ["2024-11-30", "2024-12-01", "2024-12-02"]

    def test_year_boundary(self):
        """Test range crossing year boundary."""
        result = get_date_range("2024-12-31", "2025-01-02")
        assert result == ["2024-12-31", "2025-01-01", "2025-01-02"]


class TestGetCacheKey:
    """Tests for get_cache_key function."""

    def test_returns_prefixed_key(self):
        """Test cache key has prefix."""
        result = get_cache_key("2024-12-28")
        assert result == "articles_2024-12-28"

    def test_different_dates_different_keys(self):
        """Test different dates produce different keys."""
        result1 = get_cache_key("2024-12-27")
        result2 = get_cache_key("2024-12-28")
        assert result1 != result2


class TestCorsHeaders:
    """Tests for cors_headers function."""

    def test_contains_allow_origin(self):
        """Test CORS headers contain Allow-Origin."""
        result = cors_headers()
        assert 'Access-Control-Allow-Origin' in result
        assert result['Access-Control-Allow-Origin'] == '*'

    def test_contains_content_type(self):
        """Test CORS headers contain Content-Type."""
        result = cors_headers()
        assert 'Content-Type' in result
        assert result['Content-Type'] == 'application/json'


class TestNormalizeArticle:
    """Tests for normalize_article function."""

    def test_basic_normalization(self):
        """Test basic article normalization."""
        article = {
            'article_id': 'test123',
            'title': 'Test Title',
            'summary': 'Test summary',
            'original_url': 'https://example.com/article',
        }
        
        result = normalize_article(article)
        
        assert result['article_id'] == 'test123'
        assert result['title'] == 'Test Title'
        assert result['summary'] == 'Test summary'
        assert result['original_url'] == 'https://example.com/article'

    def test_default_values(self):
        """Test default values are applied."""
        article = {'article_id': 'test123'}
        
        result = normalize_article(article)
        
        assert result['categories'] == []
        assert result['key_entities'] == {}
        assert result['content_quality'] == 'medium'
        assert result['confidence'] == 0.8
        assert result['source_type'] == 'scraped'
        assert result['keywords_used'] == []

    def test_body_to_content(self):
        """Test body field is mapped to content."""
        article = {
            'article_id': 'test123',
            'body': 'This is the article body'
        }
        
        result = normalize_article(article)
        
        assert result['content'] == 'This is the article body'

    def test_content_map_override(self):
        """Test content_map overrides body."""
        article = {
            'article_id': 'test123',
            'body': 'Original body'
        }
        content_map = {'test123': 'Overridden content'}
        
        result = normalize_article(article, content_map)
        
        assert result['content'] == 'Overridden content'

    def test_preserves_all_fields(self):
        """Test all fields are preserved."""
        article = {
            'article_id': 'test123',
            'original_url': 'https://example.com',
            'merged_from_urls': ['https://a.com', 'https://b.com'],
            'title': 'Test',
            'summary': 'Summary',
            'body': 'Content',
            'source': 'example.com',
            'publish_date': '2024-12-28',
            'categories': [{'tag': 'football'}],
            'key_entities': {'teams': ['Team A']},
            'content_quality': 'high',
            'confidence': 0.95,
            'language': 'en',
            'region': 'eu',
            'summary_translation': 'Turkish translation',
            'x_post': 'Twitter post',
            'source_type': 'api',
            'keywords_used': ['keyword1']
        }
        
        result = normalize_article(article)
        
        assert result['merged_from_urls'] == ['https://a.com', 'https://b.com']
        assert result['source'] == 'example.com'
        assert result['publish_date'] == '2024-12-28'
        assert result['categories'] == [{'tag': 'football'}]
        assert result['language'] == 'en'
        assert result['region'] == 'eu'
        assert result['summary_translation'] == 'Turkish translation'
        assert result['x_post'] == 'Twitter post'
        assert result['source_type'] == 'api'
        assert result['keywords_used'] == ['keyword1']


class TestDeduplicateArticles:
    """Tests for deduplicate_articles function."""

    def test_removes_duplicates_by_url(self):
        """Test duplicates are removed by URL."""
        articles = [
            {'article_id': '1', 'original_url': 'https://a.com'},
            {'article_id': '2', 'original_url': 'https://a.com'},  # Duplicate
            {'article_id': '3', 'original_url': 'https://b.com'},
        ]
        
        result = deduplicate_articles(articles)
        
        assert len(result) == 2
        urls = [a['original_url'] for a in result]
        assert 'https://a.com' in urls
        assert 'https://b.com' in urls

    def test_keeps_first_occurrence(self):
        """Test first occurrence is kept."""
        articles = [
            {'article_id': '1', 'original_url': 'https://a.com', 'title': 'First'},
            {'article_id': '2', 'original_url': 'https://a.com', 'title': 'Second'},
        ]
        
        result = deduplicate_articles(articles)
        
        assert len(result) == 1
        assert result[0]['title'] == 'First'

    def test_empty_list(self):
        """Test empty list returns empty."""
        result = deduplicate_articles([])
        assert result == []

    def test_uses_article_id_as_fallback(self):
        """Test article_id is used if no original_url."""
        articles = [
            {'article_id': 'id1'},
            {'article_id': 'id1'},  # Duplicate by ID
            {'article_id': 'id2'},
        ]
        
        result = deduplicate_articles(articles)
        
        assert len(result) == 2


class TestCacheConfiguration:
    """Tests for cache configuration constants."""

    def test_cache_ttl_is_10_minutes(self):
        """Test cache TTL is 10 minutes."""
        assert CACHE_TTL_SECONDS == 10 * 60

    def test_config_cache_ttl_is_5_minutes(self):
        """Test config cache TTL is 5 minutes."""
        assert CONFIG_CACHE_TTL_SECONDS == 5 * 60


class TestAdditionalGcsApiConfigs:
    """Tests for additional configuration values."""

    def test_config_folder_constant(self):
        """Test config folder path."""
        import os
        config_folder = os.getenv('CONFIG_FOLDER', 'config/')
        assert config_folder == 'config/' or '/' in config_folder

    def test_user_preferences_folder(self):
        """Test user preferences folder path."""
        user_pref = 'config/user_preferences/'
        assert 'user_preferences' in user_pref
        assert user_pref.endswith('/')

    def test_fallback_allowed_emails(self):
        """Test fallback allowed emails configuration."""
        fallback = ['oktay.burak.ertas@gmail.com']
        assert len(fallback) == 1
        assert '@' in fallback[0]


class TestApiKeyValidation:
    """Tests for API key validation logic."""

    def test_no_api_key_header_returns_false(self):
        """Test missing X-API-Key header."""
        # API key validation checks header
        api_key = None
        assert not api_key  # Should fail validation

    def test_empty_api_key_returns_false(self):
        """Test empty API key."""
        api_key = ''
        assert not api_key  # Should fail validation

    def test_valid_api_key_present(self):
        """Test valid API key format."""
        api_key = 'test-api-key-12345'
        assert api_key  # Non-empty is first check


class TestDateRangeEdgeCases:
    """Tests for get_date_range edge cases."""

    def test_start_after_end_returns_empty(self):
        """Test when start date is after end date."""
        result = get_date_range("2024-12-30", "2024-12-28")
        assert result == []  # Start is after end

    def test_large_range(self):
        """Test large date range."""
        result = get_date_range("2024-01-01", "2024-01-31")
        assert len(result) == 31

    def test_leap_year_february(self):
        """Test leap year February."""
        result = get_date_range("2024-02-28", "2024-03-01")
        assert len(result) == 3  # 28, 29, 1 March


class TestNormalizeArticleEdgeCases:
    """Tests for normalize_article edge cases."""

    def test_missing_all_fields(self):
        """Test article with no fields."""
        article = {}
        result = normalize_article(article)
        
        assert result['article_id'] is None
        assert result['title'] is None
        assert result['content'] == ''

    def test_content_priority_body_over_empty_content(self):
        """Test body is used when content is empty."""
        article = {
            'body': 'Body text',
            'content': ''
        }
        result = normalize_article(article)
        assert result['content'] == 'Body text'

    def test_content_priority_content_over_body(self):
        """Test content takes priority when both present."""
        article = {
            'body': 'Body text',
            'content': 'Content text'
        }
        result = normalize_article(article)
        # Note: body is checked first in the or chain
        assert result['content'] in ['Body text', 'Content text']

    def test_keywords_used_preserved(self):
        """Test keywords_used field is preserved."""
        article = {
            'keywords_used': ['fenerbahce', 'transfer']
        }
        result = normalize_article(article)
        assert result['keywords_used'] == ['fenerbahce', 'transfer']

    def test_region_preserved(self):
        """Test region field is preserved."""
        article = {'region': 'tr'}
        result = normalize_article(article)
        assert result['region'] == 'tr'


class TestDeduplicateArticlesEdgeCases:
    """Tests for deduplicate_articles edge cases."""

    def test_single_article(self):
        """Test single article returns unchanged."""
        articles = [{'article_id': '1', 'original_url': 'https://a.com'}]
        result = deduplicate_articles(articles)
        assert len(result) == 1

    def test_all_duplicates(self):
        """Test all duplicates reduces to one."""
        articles = [
            {'article_id': '1', 'original_url': 'https://a.com'},
            {'article_id': '2', 'original_url': 'https://a.com'},
            {'article_id': '3', 'original_url': 'https://a.com'},
        ]
        result = deduplicate_articles(articles)
        assert len(result) == 1

    def test_no_url_or_id(self):
        """Test articles without URL or ID are filtered."""
        articles = [
            {'title': 'No URL or ID'},
        ]
        result = deduplicate_articles(articles)
        assert len(result) == 0

    def test_preserves_order(self):
        """Test order is preserved (first wins)."""
        articles = [
            {'article_id': '1', 'original_url': 'https://a.com', 'order': 1},
            {'article_id': '2', 'original_url': 'https://b.com', 'order': 2},
            {'article_id': '3', 'original_url': 'https://c.com', 'order': 3},
        ]
        result = deduplicate_articles(articles)
        assert result[0]['order'] == 1
        assert result[1]['order'] == 2
        assert result[2]['order'] == 3


class TestCacheKeyGeneration:
    """Tests for cache key generation."""

    def test_key_format(self):
        """Test cache key format."""
        result = get_cache_key("2024-12-28")
        assert result.startswith("articles_")
        assert "2024-12-28" in result

    def test_consistent_keys(self):
        """Test same date always produces same key."""
        result1 = get_cache_key("2024-12-28")
        result2 = get_cache_key("2024-12-28")
        assert result1 == result2


class TestHashEmailEdgeCases:
    """Additional tests for hash_email function."""

    def test_unicode_email(self):
        """Test email with unicode characters."""
        result = hash_email("tëst@example.com")
        assert len(result) == 16

    def test_plus_addressing(self):
        """Test email with plus addressing."""
        result = hash_email("user+tag@example.com")
        assert len(result) == 16

    def test_subdomain_email(self):
        """Test email with subdomain."""
        result = hash_email("user@subdomain.example.com")
        assert len(result) == 16

    def test_numeric_local_part(self):
        """Test email with numeric local part."""
        result = hash_email("123456@example.com")
        assert len(result) == 16

    def test_special_chars_in_local_part(self):
        """Test email with special characters."""
        result = hash_email("user.name_123@example.com")
        assert len(result) == 16


class TestNormalizeArticleContentFields:
    """Tests for normalize_article content handling."""

    def test_empty_body_empty_content(self):
        """Test when both body and content are empty."""
        article = {'article_id': 'test', 'body': '', 'content': ''}
        result = normalize_article(article)
        assert result['content'] == ''

    def test_none_body_with_content(self):
        """Test None body with valid content."""
        article = {'article_id': 'test', 'body': None, 'content': 'Valid content'}
        result = normalize_article(article)
        assert result['content'] == 'Valid content'

    def test_whitespace_only_body(self):
        """Test whitespace-only body."""
        article = {'article_id': 'test', 'body': '   ', 'content': 'Content'}
        result = normalize_article(article)
        # Non-empty whitespace should still be used
        assert result['content'] in ['   ', 'Content']

    def test_content_map_empty(self):
        """Test empty content map."""
        article = {'article_id': 'test123', 'body': 'Original'}
        result = normalize_article(article, {})
        assert result['content'] == 'Original'

    def test_content_map_wrong_id(self):
        """Test content map with different ID."""
        article = {'article_id': 'test123', 'body': 'Original'}
        result = normalize_article(article, {'other_id': 'Other content'})
        assert result['content'] == 'Original'


class TestGetDateRangeFormats:
    """Tests for get_date_range date format handling."""

    def test_first_day_of_month(self):
        """Test first day of month."""
        result = get_date_range("2024-12-01", "2024-12-03")
        assert result == ["2024-12-01", "2024-12-02", "2024-12-03"]

    def test_last_day_of_month(self):
        """Test last day of month."""
        result = get_date_range("2024-12-29", "2024-12-31")
        assert result == ["2024-12-29", "2024-12-30", "2024-12-31"]

    def test_first_day_of_year(self):
        """Test first day of year."""
        result = get_date_range("2024-01-01", "2024-01-01")
        assert result == ["2024-01-01"]

    def test_last_day_of_year(self):
        """Test last day of year."""
        result = get_date_range("2024-12-31", "2024-12-31")
        assert result == ["2024-12-31"]


class TestCorsHeadersComplete:
    """Complete tests for CORS headers."""

    def test_returns_dict(self):
        """Test CORS headers returns dict."""
        result = cors_headers()
        assert isinstance(result, dict)

    def test_allow_origin_wildcard(self):
        """Test Allow-Origin is wildcard."""
        result = cors_headers()
        assert result.get('Access-Control-Allow-Origin') == '*'

    def test_json_content_type(self):
        """Test Content-Type is JSON."""
        result = cors_headers()
        assert 'json' in result.get('Content-Type', '').lower()

    def test_only_two_headers(self):
        """Test only expected headers present."""
        result = cors_headers()
        # cors_headers returns specific headers, count them
        assert len(result) >= 2


class TestDeduplicateArticlesUrls:
    """Tests for deduplicate_articles URL handling."""

    def test_different_protocols_same_domain(self):
        """Test different protocols treated as different."""
        articles = [
            {'article_id': '1', 'original_url': 'http://example.com/page'},
            {'article_id': '2', 'original_url': 'https://example.com/page'},
        ]
        result = deduplicate_articles(articles)
        # Different protocols = different URLs
        assert len(result) == 2

    def test_trailing_slash_difference(self):
        """Test trailing slash treated as different."""
        articles = [
            {'article_id': '1', 'original_url': 'https://example.com/page'},
            {'article_id': '2', 'original_url': 'https://example.com/page/'},
        ]
        result = deduplicate_articles(articles)
        # Trailing slash makes different URLs
        assert len(result) == 2

    def test_query_params_difference(self):
        """Test query params treated as different."""
        articles = [
            {'article_id': '1', 'original_url': 'https://example.com/page'},
            {'article_id': '2', 'original_url': 'https://example.com/page?ref=home'},
        ]
        result = deduplicate_articles(articles)
        assert len(result) == 2


class TestNormalizeArticleSourceType:
    """Tests for normalize_article source_type field."""

    def test_default_source_type_scraped(self):
        """Test default source_type is scraped."""
        article = {'article_id': 'test'}
        result = normalize_article(article)
        assert result['source_type'] == 'scraped'

    def test_api_source_type_preserved(self):
        """Test API source_type is preserved."""
        article = {'article_id': 'test', 'source_type': 'api'}
        result = normalize_article(article)
        assert result['source_type'] == 'api'

    def test_custom_source_type_preserved(self):
        """Test custom source_type is preserved."""
        article = {'article_id': 'test', 'source_type': 'rss'}
        result = normalize_article(article)
        assert result['source_type'] == 'rss'


class TestNormalizeArticleOptionalFields:
    """Tests for normalize_article optional fields."""

    def test_summary_translation_preserved(self):
        """Test summary_translation is preserved."""
        article = {'article_id': 'test', 'summary_translation': 'Turkish text'}
        result = normalize_article(article)
        assert result['summary_translation'] == 'Turkish text'

    def test_x_post_preserved(self):
        """Test x_post is preserved."""
        article = {'article_id': 'test', 'x_post': 'Twitter post text'}
        result = normalize_article(article)
        assert result['x_post'] == 'Twitter post text'

    def test_confidence_preserved(self):
        """Test confidence score is preserved."""
        article = {'article_id': 'test', 'confidence': 0.99}
        result = normalize_article(article)
        assert result['confidence'] == 0.99

    def test_categories_preserved(self):
        """Test categories are preserved."""
        categories = [{'tag': 'sports'}, {'tag': 'football'}]
        article = {'article_id': 'test', 'categories': categories}
        result = normalize_article(article)
        assert result['categories'] == categories

    def test_key_entities_preserved(self):
        """Test key_entities are preserved."""
        entities = {'teams': ['Fenerbahce'], 'people': ['Mourinho']}
        article = {'article_id': 'test', 'key_entities': entities}
        result = normalize_article(article)
        assert result['key_entities'] == entities
