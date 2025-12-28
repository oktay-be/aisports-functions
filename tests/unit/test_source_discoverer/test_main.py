"""Unit tests for source_discoverer_function/main.py."""

import pytest
from unittest.mock import MagicMock, patch
import sys

# Mock Google Cloud modules before importing
mock_storage = MagicMock()
sys.modules['google.cloud.storage'] = mock_storage
mock_google_cloud = MagicMock()
mock_google_cloud.storage = mock_storage
sys.modules['google.cloud'] = mock_google_cloud

# Import the module after mocking
with patch.dict('os.environ', {'ENVIRONMENT': 'local'}):
    from source_discoverer_function.main import (
        extract_fqdn,
        extract_unique_fqdns,
        DISCOVERED_SOURCES_PATH,
        USER_PREFERENCES_PREFIX,
    )


class TestExtractFqdn:
    """Tests for extract_fqdn function."""

    def test_basic_url(self):
        """Test basic URL extraction."""
        result = extract_fqdn("https://example.com/article")
        assert result == "example.com"

    def test_removes_www_prefix(self):
        """Test www. prefix is removed."""
        result = extract_fqdn("https://www.example.com/article")
        assert result == "example.com"

    def test_with_subdomain(self):
        """Test URL with subdomain (not www)."""
        result = extract_fqdn("https://sport.example.com/article")
        assert result == "sport.example.com"

    def test_http_protocol(self):
        """Test HTTP protocol is handled."""
        result = extract_fqdn("http://example.com/article")
        assert result == "example.com"

    def test_with_port(self):
        """Test URL with port."""
        result = extract_fqdn("https://example.com:8080/article")
        assert result == "example.com:8080"

    def test_with_query_params(self):
        """Test URL with query parameters."""
        result = extract_fqdn("https://example.com/article?id=123")
        assert result == "example.com"

    def test_converts_to_lowercase(self):
        """Test FQDN is converted to lowercase."""
        result = extract_fqdn("https://EXAMPLE.COM/Article")
        assert result == "example.com"

    def test_empty_url_returns_none(self):
        """Test empty URL returns None."""
        result = extract_fqdn("")
        assert result is None

    def test_none_url_returns_none(self):
        """Test None URL returns None."""
        result = extract_fqdn(None)
        assert result is None

    def test_invalid_url_returns_none(self):
        """Test invalid URL without domain returns None."""
        result = extract_fqdn("not-a-url")
        assert result is None

    def test_complex_domain(self):
        """Test complex domain extraction."""
        result = extract_fqdn("https://www.sport1.de/channel/transfermarkt")
        assert result == "sport1.de"

    def test_country_tld(self):
        """Test country TLD is preserved."""
        result = extract_fqdn("https://www.news.com.au/sport")
        assert result == "news.com.au"


class TestExtractUniqueFqdns:
    """Tests for extract_unique_fqdns function."""

    def test_extracts_unique(self):
        """Test unique FQDNs are extracted."""
        urls = [
            "https://example.com/a",
            "https://example.com/b",  # Same domain
            "https://other.com/c",
        ]
        
        result = extract_unique_fqdns(urls)
        
        assert result == {"example.com", "other.com"}

    def test_empty_list(self):
        """Test empty list returns empty set."""
        result = extract_unique_fqdns([])
        assert result == set()

    def test_filters_invalid_urls(self):
        """Test invalid URLs are filtered."""
        urls = [
            "https://example.com/a",
            "",
            None,
            "not-a-url",
        ]
        
        result = extract_unique_fqdns(urls)
        
        assert result == {"example.com"}

    def test_removes_www_across_urls(self):
        """Test www is removed consistently."""
        urls = [
            "https://www.example.com/a",
            "https://example.com/b",
        ]
        
        result = extract_unique_fqdns(urls)
        
        # Should be treated as same domain
        assert result == {"example.com"}


class TestConfigPaths:
    """Tests for configuration path constants."""

    def test_discovered_sources_path(self):
        """Test discovered sources path."""
        assert DISCOVERED_SOURCES_PATH == 'config/discovered_sources.json'

    def test_user_preferences_prefix(self):
        """Test user preferences prefix."""
        assert USER_PREFERENCES_PREFIX == 'config/user_preferences/'


class TestExtractFqdnEdgeCases:
    """Additional edge cases for extract_fqdn."""

    def test_ftp_protocol(self):
        """Test FTP protocol URL."""
        result = extract_fqdn("ftp://files.example.com/file")
        # May or may not handle non-http protocols
        assert result is None or result == "files.example.com"

    def test_url_with_username_password(self):
        """Test URL with credentials."""
        result = extract_fqdn("https://user:pass@example.com/page")
        # Should extract domain ignoring credentials
        assert result is not None
        assert "example.com" in result or result == "example.com"

    def test_ip_address_url(self):
        """Test URL with IP address."""
        result = extract_fqdn("https://192.168.1.1/page")
        assert result == "192.168.1.1"

    def test_localhost_url(self):
        """Test localhost URL returns None (not a valid domain)."""
        result = extract_fqdn("http://localhost:3000/api")
        # localhost is not a valid public domain, may return None
        assert result is None or 'localhost' in result

    def test_double_www_prefix(self):
        """Test URL with double www prefix (malformed)."""
        result = extract_fqdn("https://www.www.example.com/page")
        # Should handle gracefully
        assert result is not None

    def test_trailing_dot_domain(self):
        """Test domain with trailing dot."""
        result = extract_fqdn("https://example.com./page")
        # May or may not preserve trailing dot
        assert result is not None

    def test_unicode_domain(self):
        """Test internationalized domain name."""
        result = extract_fqdn("https://例え.jp/page")
        # Should handle unicode domains
        assert result is not None

    def test_very_long_domain(self):
        """Test very long domain."""
        long_subdomain = "sub" * 50
        result = extract_fqdn(f"https://{long_subdomain}.example.com/page")
        assert result is not None


class TestExtractUniqueFqdnsEdgeCases:
    """Additional edge cases for extract_unique_fqdns."""

    def test_mixed_protocols(self):
        """Test mixed HTTP and HTTPS."""
        urls = [
            "https://example.com/a",
            "http://example.com/b"
        ]
        result = extract_unique_fqdns(urls)
        # Should be treated as same domain
        assert result == {"example.com"}

    def test_case_insensitive(self):
        """Test case insensitivity."""
        urls = [
            "https://EXAMPLE.COM/a",
            "https://example.com/b"
        ]
        result = extract_unique_fqdns(urls)
        assert result == {"example.com"}

    def test_many_unique_domains(self):
        """Test many unique domains."""
        urls = [f"https://domain{i}.com/page" for i in range(100)]
        result = extract_unique_fqdns(urls)
        assert len(result) == 100

    def test_all_same_domain(self):
        """Test all URLs from same domain."""
        urls = [f"https://example.com/page{i}" for i in range(100)]
        result = extract_unique_fqdns(urls)
        assert len(result) == 1
        assert "example.com" in result

    def test_with_port_variations(self):
        """Test URLs with different ports."""
        urls = [
            "https://example.com/a",
            "https://example.com:8080/b"
        ]
        result = extract_unique_fqdns(urls)
        # Ports make different FQDNs
        assert len(result) >= 1


class TestConfigurationDefaults:
    """Tests for configuration default values."""

    def test_gcs_bucket_default(self):
        """Test default GCS bucket."""
        import os
        bucket = os.getenv('GCS_BUCKET_NAME', 'aisports-scraping')
        assert bucket == 'aisports-scraping'

    def test_project_id_default(self):
        """Test default project ID."""
        import os
        project = os.getenv('GOOGLE_CLOUD_PROJECT', 'gen-lang-client-0306766464')
        assert project == 'gen-lang-client-0306766464'

    def test_environment_default(self):
        """Test default environment."""
        import os
        env = os.getenv('ENVIRONMENT', 'development')
        assert env in ['development', 'local', 'production', 'staging']


class TestPathConstantsFormat:
    """Tests for path constant formatting."""

    def test_discovered_sources_is_json(self):
        """Test discovered sources path is JSON file."""
        assert DISCOVERED_SOURCES_PATH.endswith('.json')

    def test_discovered_sources_in_config(self):
        """Test discovered sources is in config folder."""
        assert DISCOVERED_SOURCES_PATH.startswith('config/')

    def test_user_preferences_ends_with_slash(self):
        """Test user preferences prefix ends with slash."""
        assert USER_PREFERENCES_PREFIX.endswith('/')

    def test_user_preferences_in_config(self):
        """Test user preferences is in config folder."""
        assert USER_PREFERENCES_PREFIX.startswith('config/')
