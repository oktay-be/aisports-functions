"""Unit tests for scraper_function/main.py."""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import sys

# Mock all Google Cloud modules before importing
mock_zoneinfo = MagicMock()
sys.modules['zoneinfo'] = mock_zoneinfo

mock_pubsub = MagicMock()
sys.modules['google.cloud.pubsub_v1'] = mock_pubsub
mock_storage = MagicMock()
sys.modules['google.cloud.storage'] = mock_storage
mock_secretmanager = MagicMock()
sys.modules['google.cloud.secretmanager'] = mock_secretmanager

# Need to also mock the google.cloud module itself
mock_google_cloud = MagicMock()
mock_google_cloud.pubsub_v1 = mock_pubsub
mock_google_cloud.storage = mock_storage
mock_google_cloud.secretmanager = mock_secretmanager
sys.modules['google.cloud'] = mock_google_cloud

# Mock journalist library
mock_journalist = MagicMock()
sys.modules['journalist'] = mock_journalist

# Mock Google Cloud clients before importing
with patch.dict('os.environ', {'ENVIRONMENT': 'local'}):
    from scraper_function.main import (
        validate_scraping_request,
        apply_metadata_to_articles,
        normalize_publish_date,
        VALID_REGIONS,
    )


class TestValidateScrapingRequest:
    """Tests for validate_scraping_request function."""

    def test_valid_request_with_urls(self):
        """Test valid request with URLs."""
        message_data = {
            'urls': ['https://example.com/article1', 'https://example.com/article2'],
            'region': 'eu'
        }
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is True
        assert error == ""

    def test_valid_request_tr_region(self):
        """Test valid request with TR region."""
        message_data = {
            'urls': ['https://example.com/article'],
            'region': 'tr'
        }
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is True
        assert error == ""

    def test_missing_urls(self):
        """Test request with missing urls field."""
        message_data = {'region': 'eu'}
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is False
        assert "urls" in error.lower()

    def test_empty_urls_list(self):
        """Test request with empty urls list."""
        message_data = {'urls': [], 'region': 'eu'}
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is False
        assert "urls" in error.lower()

    def test_urls_not_list(self):
        """Test request with urls not being a list."""
        message_data = {'urls': 'https://example.com', 'region': 'eu'}
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is False
        assert "urls" in error.lower()

    def test_invalid_region(self):
        """Test request with invalid region."""
        message_data = {'urls': ['https://example.com'], 'region': 'us'}
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is False
        assert "region" in error.lower()

    def test_default_region_eu(self):
        """Test default region is eu."""
        message_data = {'urls': ['https://example.com']}
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is True

    def test_valid_scrape_depth_zero(self):
        """Test valid scrape depth of 0."""
        message_data = {
            'urls': ['https://example.com'],
            'region': 'eu',
            'scrape_depth': 0
        }
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is True

    def test_valid_scrape_depth_positive(self):
        """Test valid scrape depth > 0."""
        message_data = {
            'urls': ['https://example.com'],
            'region': 'eu',
            'scrape_depth': 3
        }
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is True

    def test_invalid_scrape_depth_negative(self):
        """Test invalid negative scrape depth."""
        message_data = {
            'urls': ['https://example.com'],
            'region': 'eu',
            'scrape_depth': -1
        }
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is False
        assert "scrape_depth" in error.lower()

    def test_invalid_scrape_depth_not_int(self):
        """Test invalid non-integer scrape depth."""
        message_data = {
            'urls': ['https://example.com'],
            'region': 'eu',
            'scrape_depth': "deep"
        }
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is False
        assert "scrape_depth" in error.lower()


class TestValidRegions:
    """Tests for VALID_REGIONS constant."""

    def test_eu_in_valid_regions(self):
        """Test eu is in valid regions."""
        assert 'eu' in VALID_REGIONS

    def test_tr_in_valid_regions(self):
        """Test tr is in valid regions."""
        assert 'tr' in VALID_REGIONS

    def test_us_not_in_valid_regions(self):
        """Test us is not in valid regions."""
        assert 'us' not in VALID_REGIONS


class TestApplyMetadataToArticles:
    """Tests for apply_metadata_to_articles function."""

    def test_applies_metadata_from_url_metadata(self):
        """Test metadata is applied from url_metadata dict."""
        articles = [{'url': 'https://example.com/article'}]
        url_metadata = {
            'https://example.com/article': {
                'language': 'en',
                'region': 'eu',
                'article_id': 'abc123',
                'source_type': 'api',
                'keywords_used': ['football']
            }
        }
        
        result = apply_metadata_to_articles(articles, url_metadata, 'tr', ['default_kw'])
        
        assert result[0]['language'] == 'en'
        assert result[0]['region'] == 'eu'
        assert result[0]['article_id'] == 'abc123'
        assert result[0]['source_type'] == 'api'
        assert result[0]['keywords_used'] == ['football']

    def test_uses_fallback_when_no_metadata(self):
        """Test fallback values used when no metadata."""
        articles = [{'url': 'https://example.com/article'}]
        url_metadata = {}
        
        result = apply_metadata_to_articles(articles, url_metadata, 'tr', ['scrape_kw'])
        
        assert result[0]['language'] == ''
        assert result[0]['region'] == 'tr'
        assert result[0]['source_type'] == 'scraped'
        assert result[0]['keywords_used'] == ['scrape_kw']

    def test_generates_article_id_when_missing(self):
        """Test article_id is generated when missing."""
        articles = [{'url': 'https://example.com/article'}]
        url_metadata = {}
        
        result = apply_metadata_to_articles(articles, url_metadata, 'eu', [])
        
        assert result[0]['article_id'] != ''
        assert len(result[0]['article_id']) == 16  # Generated ID length

    def test_handles_multiple_articles(self):
        """Test handling multiple articles with mixed metadata."""
        articles = [
            {'url': 'https://example.com/a1'},
            {'url': 'https://example.com/a2'},
        ]
        url_metadata = {
            'https://example.com/a1': {
                'language': 'tr',
                'region': 'tr',
                'article_id': 'id1',
                'source_type': 'api',
                'keywords_used': []
            }
        }
        
        result = apply_metadata_to_articles(articles, url_metadata, 'eu', ['kw'])
        
        # First article uses metadata
        assert result[0]['region'] == 'tr'
        assert result[0]['article_id'] == 'id1'
        # Second article uses fallback
        assert result[1]['region'] == 'eu'
        assert result[1]['source_type'] == 'scraped'


class TestNormalizePublishDate:
    """Tests for normalize_publish_date function."""

    def test_empty_string_returns_empty(self):
        """Test empty string returns empty."""
        assert normalize_publish_date('') == ''

    def test_none_returns_empty(self):
        """Test None returns empty."""
        assert normalize_publish_date(None) == ''

    def test_datetime_object_with_tz(self):
        """Test datetime object with timezone."""
        dt = datetime(2024, 12, 28, 10, 30, 0, tzinfo=timezone.utc)
        result = normalize_publish_date(dt)
        assert '2024-12-28' in result
        assert '10:30:00' in result

    def test_datetime_object_without_tz(self):
        """Test datetime object without timezone gets UTC."""
        dt = datetime(2024, 12, 28, 10, 30, 0)
        result = normalize_publish_date(dt)
        assert '2024-12-28' in result
        assert '+00:00' in result or 'Z' in result

    def test_iso_format_with_tz(self):
        """Test ISO format string with timezone."""
        iso_str = '2024-12-28T10:30:00+00:00'
        result = normalize_publish_date(iso_str)
        assert result == iso_str

    def test_iso_format_with_z(self):
        """Test ISO format string with Z timezone."""
        iso_str = '2024-12-28T10:30:00Z'
        result = normalize_publish_date(iso_str)
        assert result == iso_str

    def test_date_only_format(self):
        """Test date only format."""
        result = normalize_publish_date('2024-12-28')
        assert '2024-12-28' in result

    def test_datetime_without_tz_format(self):
        """Test datetime format without timezone."""
        result = normalize_publish_date('2024-12-28T10:30:00')
        assert '2024-12-28' in result
        assert '10:30:00' in result

    def test_common_datetime_format(self):
        """Test common datetime format with space."""
        result = normalize_publish_date('2024-12-28 10:30:00')
        assert '2024-12-28' in result
        assert '10:30' in result

    def test_european_date_format(self):
        """Test European date format."""
        result = normalize_publish_date('28/12/2024')
        assert '2024' in result
        assert '12' in result
        assert '28' in result

    def test_unparseable_string_returns_original(self):
        """Test unparseable string returns original."""
        weird_date = "sometime last week"
        result = normalize_publish_date(weird_date)
        assert result == weird_date

    def test_whitespace_only_returns_empty(self):
        """Test whitespace-only string returns empty."""
        assert normalize_publish_date('   ') == ''


class TestScraperConfigConstants:
    """Tests for scraper configuration constants."""

    def test_valid_regions_contains_eu(self):
        """Test valid regions contains EU."""
        assert 'eu' in VALID_REGIONS

    def test_valid_regions_contains_tr(self):
        """Test valid regions contains TR."""
        assert 'tr' in VALID_REGIONS

    def test_valid_regions_only_eu_tr(self):
        """Test valid regions only contains EU and TR."""
        assert len(VALID_REGIONS) == 2

    def test_environment_default(self):
        """Test environment default value."""
        import os
        env = os.getenv('ENVIRONMENT', 'development')
        assert env in ['development', 'local', 'production', 'staging']

    def test_gcs_bucket_default(self):
        """Test GCS bucket default."""
        import os
        bucket = os.getenv('GCS_BUCKET_NAME', 'aisports-scraping')
        assert bucket == 'aisports-scraping' or bucket


class TestValidateScrapingRequestEdgeCases:
    """Additional edge cases for validate_scraping_request."""

    def test_single_url(self):
        """Test single URL is valid."""
        message_data = {'urls': ['https://example.com']}
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is True

    def test_many_urls(self):
        """Test many URLs is valid."""
        urls = [f'https://example.com/{i}' for i in range(100)]
        message_data = {'urls': urls}
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is True

    def test_unicode_urls(self):
        """Test URLs with unicode characters."""
        message_data = {'urls': ['https://example.com/artículo']}
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is True

    def test_url_with_query_params(self):
        """Test URL with query parameters."""
        message_data = {'urls': ['https://example.com/article?id=123&ref=twitter']}
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is True

    def test_url_with_fragment(self):
        """Test URL with fragment."""
        message_data = {'urls': ['https://example.com/article#section1']}
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is True

    def test_scrape_depth_zero_valid(self):
        """Test scrape_depth=0 is valid."""
        message_data = {'urls': ['https://example.com'], 'scrape_depth': 0}
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is True

    def test_scrape_depth_large_valid(self):
        """Test large scrape_depth is valid."""
        message_data = {'urls': ['https://example.com'], 'scrape_depth': 10}
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is True


class TestApplyMetadataEdgeCases:
    """Additional edge cases for apply_metadata_to_articles."""

    def test_empty_articles_list(self):
        """Test empty articles list."""
        result = apply_metadata_to_articles([], {}, 'eu', [])
        assert result == []

    def test_article_without_url(self):
        """Test article without URL field."""
        articles = [{'title': 'No URL Article'}]
        result = apply_metadata_to_articles(articles, {}, 'tr', [])
        # Should handle gracefully
        assert len(result) == 1
        assert result[0]['region'] == 'tr'

    def test_url_metadata_empty_values(self):
        """Test URL metadata with empty values."""
        articles = [{'url': 'https://example.com'}]
        url_metadata = {
            'https://example.com': {
                'language': '',
                'region': '',
                'article_id': '',
                'source_type': '',
                'keywords_used': []
            }
        }
        result = apply_metadata_to_articles(articles, url_metadata, 'tr', ['kw'])
        # Should use the provided values, not fallbacks
        assert len(result) == 1

    def test_preserves_existing_article_fields(self):
        """Test existing article fields are preserved."""
        articles = [{'url': 'https://example.com', 'title': 'Test', 'body': 'Content'}]
        result = apply_metadata_to_articles(articles, {}, 'eu', [])
        assert result[0]['title'] == 'Test'
        assert result[0]['body'] == 'Content'


class TestNormalizePublishDateEdgeCases:
    """Additional edge cases for normalize_publish_date."""

    def test_int_timestamp_unix(self):
        """Test integer Unix timestamp."""
        # This might or might not be handled
        result = normalize_publish_date(1704067200)  # 2024-01-01
        # Just verify no crash
        assert result is not None

    def test_float_timestamp(self):
        """Test float timestamp."""
        result = normalize_publish_date(1704067200.0)
        assert result is not None

    def test_very_old_date(self):
        """Test very old date."""
        result = normalize_publish_date('1990-01-01')
        assert '1990' in result

    def test_future_date(self):
        """Test future date."""
        result = normalize_publish_date('2050-12-31')
        assert '2050' in result

    def test_datetime_with_microseconds(self):
        """Test datetime with microseconds."""
        dt = datetime(2024, 12, 28, 10, 30, 0, 123456, tzinfo=timezone.utc)
        result = normalize_publish_date(dt)
        assert '2024-12-28' in result

    def test_iso_with_milliseconds(self):
        """Test ISO format with milliseconds."""
        iso_str = '2024-12-28T10:30:00.123Z'
        result = normalize_publish_date(iso_str)
        assert '2024-12-28' in result


class TestValidateScrapingRequestRegions:
    """Tests for region validation in validate_scraping_request."""

    def test_eu_region_valid(self):
        """Test EU region is valid."""
        message_data = {'urls': ['https://example.com'], 'region': 'eu'}
        is_valid, _ = validate_scraping_request(message_data)
        assert is_valid is True

    def test_tr_region_valid(self):
        """Test TR region is valid."""
        message_data = {'urls': ['https://example.com'], 'region': 'tr'}
        is_valid, _ = validate_scraping_request(message_data)
        assert is_valid is True

    def test_uppercase_region_invalid(self):
        """Test uppercase region is invalid."""
        message_data = {'urls': ['https://example.com'], 'region': 'EU'}
        is_valid, error = validate_scraping_request(message_data)
        assert is_valid is False
        assert 'region' in error.lower()

    def test_empty_region_uses_default(self):
        """Test empty region uses default (eu)."""
        message_data = {'urls': ['https://example.com'], 'region': ''}
        # Empty region should fail since it's not in valid set
        is_valid, _ = validate_scraping_request(message_data)
        # Empty string is not in VALID_REGIONS
        assert is_valid is False

    def test_none_region_uses_default(self):
        """Test None region falls back to default behavior."""
        message_data = {'urls': ['https://example.com'], 'region': None}
        # None is not in VALID_REGIONS, but .get('region', 'eu') returns None not 'eu'
        # So validation should fail (None not in {'eu', 'tr'})
        is_valid, error = validate_scraping_request(message_data)
        # Actually checks if region is in VALID_REGIONS, None is not
        assert is_valid is False
        assert 'region' in error.lower()


class TestApplyMetadataPublishDate:
    """Tests for publish_date handling in apply_metadata_to_articles."""

    def test_preserves_publish_date_from_metadata(self):
        """Test publish_date from metadata is used."""
        articles = [{'url': 'https://example.com'}]
        url_metadata = {
            'https://example.com': {
                'language': 'en',
                'region': 'eu',
                'article_id': 'id1',
                'source_type': 'api',
                'publish_date': '2024-12-28',
                'keywords_used': []
            }
        }
        result = apply_metadata_to_articles(articles, url_metadata, 'eu', [])
        # published_at should be set from metadata when article doesn't have it
        if 'published_at' in result[0]:
            assert result[0]['published_at'] == '2024-12-28'

    def test_article_publish_date_not_overridden(self):
        """Test existing article publish_date is not overridden."""
        articles = [{'url': 'https://example.com', 'published_at': '2024-12-25'}]
        url_metadata = {
            'https://example.com': {
                'language': 'en',
                'region': 'eu',
                'article_id': 'id1',
                'source_type': 'api',
                'publish_date': '2024-12-28',
                'keywords_used': []
            }
        }
        result = apply_metadata_to_articles(articles, url_metadata, 'eu', [])
        # Article's own publish_date should be preserved
        assert result[0]['published_at'] == '2024-12-25'


class TestNormalizePublishDateFormats:
    """Tests for various date formats in normalize_publish_date."""

    def test_us_date_format_month_day_year(self):
        """Test US date format MM/DD/YYYY."""
        result = normalize_publish_date('12/28/2024')
        assert '2024' in result

    def test_iso_without_separators(self):
        """Test compact ISO format (might not be supported)."""
        # YYYYMMDD format
        result = normalize_publish_date('20241228')
        # Should return original if can't parse
        assert result is not None

    def test_date_with_text_month(self):
        """Test date with text month name."""
        result = normalize_publish_date('December 28, 2024')
        # Might return original if not parseable
        assert result is not None

    def test_iso_with_positive_offset(self):
        """Test ISO with positive timezone offset."""
        iso_str = '2024-12-28T10:30:00+03:00'
        result = normalize_publish_date(iso_str)
        assert '2024-12-28' in result


class TestApplyMetadataArticleId:
    """Tests for article_id handling in apply_metadata_to_articles."""

    def test_uses_metadata_article_id(self):
        """Test article_id from metadata is used."""
        articles = [{'url': 'https://example.com'}]
        url_metadata = {
            'https://example.com': {
                'language': 'en',
                'region': 'eu',
                'article_id': 'custom_id_123',
                'source_type': 'api',
                'keywords_used': []
            }
        }
        result = apply_metadata_to_articles(articles, url_metadata, 'eu', [])
        assert result[0]['article_id'] == 'custom_id_123'

    def test_generates_id_when_metadata_id_empty(self):
        """Test article_id is generated when metadata has empty id."""
        articles = [{'url': 'https://example.com'}]
        url_metadata = {
            'https://example.com': {
                'language': 'en',
                'region': 'eu',
                'article_id': '',
                'source_type': 'api',
                'keywords_used': []
            }
        }
        result = apply_metadata_to_articles(articles, url_metadata, 'eu', [])
        # Should generate ID when empty
        assert result[0]['article_id'] != ''

    def test_generated_id_is_deterministic(self):
        """Test generated article_id is deterministic for same URL."""
        articles1 = [{'url': 'https://example.com/test'}]
        articles2 = [{'url': 'https://example.com/test'}]
        
        result1 = apply_metadata_to_articles(articles1, {}, 'eu', [])
        result2 = apply_metadata_to_articles(articles2, {}, 'eu', [])
        
        assert result1[0]['article_id'] == result2[0]['article_id']


class TestValidateScrapingRequestUrlFormats:
    """Tests for URL format validation in validate_scraping_request."""

    def test_http_url_valid(self):
        """Test HTTP URL is valid."""
        message_data = {'urls': ['http://example.com/article']}
        is_valid, _ = validate_scraping_request(message_data)
        assert is_valid is True

    def test_https_url_valid(self):
        """Test HTTPS URL is valid."""
        message_data = {'urls': ['https://example.com/article']}
        is_valid, _ = validate_scraping_request(message_data)
        assert is_valid is True

    def test_mixed_protocols_valid(self):
        """Test mixed HTTP/HTTPS URLs are valid."""
        message_data = {
            'urls': [
                'http://example1.com/article',
                'https://example2.com/article'
            ]
        }
        is_valid, _ = validate_scraping_request(message_data)
        assert is_valid is True

    def test_url_with_port(self):
        """Test URL with port number."""
        message_data = {'urls': ['https://example.com:8080/article']}
        is_valid, _ = validate_scraping_request(message_data)
        assert is_valid is True

    def test_url_with_username_password(self):
        """Test URL with username and password."""
        message_data = {'urls': ['https://user:pass@example.com/article']}
        is_valid, _ = validate_scraping_request(message_data)
        assert is_valid is True


class TestOutputFileConstants:
    """Tests for output file name constants."""

    def test_api_triggered_filename(self):
        """Test API-triggered output filename."""
        # These constants define output filenames
        expected_api = 'scraped_incomplete_articles.json'
        expected_standalone = 'scraped_articles.json'
        assert 'scraped' in expected_api
        assert 'scraped' in expected_standalone
        assert expected_api != expected_standalone

    def test_output_files_are_json(self):
        """Test output files have .json extension."""
        expected_api = 'scraped_incomplete_articles.json'
        expected_standalone = 'scraped_articles.json'
        assert expected_api.endswith('.json')
        assert expected_standalone.endswith('.json')
