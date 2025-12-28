"""Unit tests for news_api_fetcher_function/news_aggregator.py."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from news_api_fetcher_function.news_aggregator import (
    is_content_complete,
    TimeRangeEnum,
    NewsAggregator,
)


class TestIsContentComplete:
    """Tests for is_content_complete function."""

    def test_empty_content_returns_false(self):
        """Test that empty content returns False."""
        assert is_content_complete("") is False

    def test_none_content_returns_false(self):
        """Test that None content returns False."""
        assert is_content_complete(None) is False

    def test_short_content_returns_false(self):
        """Test that suspiciously short content returns False."""
        short_content = "This is a very short article."
        assert is_content_complete(short_content) is False

    def test_truncation_marker_plus_chars_returns_false(self):
        """Test content with [+N chars] marker returns False."""
        content = "Some article text that ends with a truncation marker [+497 chars]"
        assert is_content_complete(content) is False

    def test_truncation_marker_chars_returns_false(self):
        """Test content with [N chars] marker (no plus) returns False."""
        content = "Some article text that ends with a truncation marker [500 chars]"
        assert is_content_complete(content) is False

    def test_truncation_marker_char_singular_returns_false(self):
        """Test content with [N char] marker (singular) returns False."""
        content = "Some article text that ends with a truncation marker [1 char]"
        assert is_content_complete(content) is False

    def test_complete_long_content_returns_true(self):
        """Test that complete long content returns True."""
        # Create content > 200 chars
        complete_content = "This is a complete article. " * 20
        assert len(complete_content) > 200
        assert is_content_complete(complete_content) is True

    def test_content_exactly_200_chars_returns_true(self):
        """Test content with exactly 200 chars returns True."""
        content = "A" * 200
        assert is_content_complete(content) is True

    def test_content_199_chars_returns_false(self):
        """Test content with 199 chars returns False."""
        content = "A" * 199
        assert is_content_complete(content) is False

    def test_whitespace_only_content_returns_false(self):
        """Test that whitespace-only content returns False."""
        assert is_content_complete("   \n\t   ") is False


class TestTimeRangeEnum:
    """Tests for TimeRangeEnum."""

    def test_last_hour_value(self):
        """Test LAST_HOUR enum value."""
        assert TimeRangeEnum.LAST_HOUR.value == "last_hour"

    def test_last_6_hours_value(self):
        """Test LAST_6_HOURS enum value."""
        assert TimeRangeEnum.LAST_6_HOURS.value == "last_6_hours"

    def test_last_12_hours_value(self):
        """Test LAST_12_HOURS enum value."""
        assert TimeRangeEnum.LAST_12_HOURS.value == "last_12_hours"

    def test_last_24_hours_value(self):
        """Test LAST_24_HOURS enum value."""
        assert TimeRangeEnum.LAST_24_HOURS.value == "last_24_hours"

    def test_last_week_value(self):
        """Test LAST_WEEK enum value."""
        assert TimeRangeEnum.LAST_WEEK.value == "last_week"

    def test_last_month_value(self):
        """Test LAST_MONTH enum value."""
        assert TimeRangeEnum.LAST_MONTH.value == "last_month"

    def test_custom_value(self):
        """Test CUSTOM enum value."""
        assert TimeRangeEnum.CUSTOM.value == "custom"

    def test_enum_from_string(self):
        """Test creating enum from string value."""
        assert TimeRangeEnum("last_24_hours") == TimeRangeEnum.LAST_24_HOURS

    def test_invalid_string_raises_error(self):
        """Test invalid string raises ValueError."""
        with pytest.raises(ValueError):
            TimeRangeEnum("invalid_range")


class TestNewsAggregatorInit:
    """Tests for NewsAggregator initialization."""

    def test_default_initialization(self):
        """Test default initialization values."""
        aggregator = NewsAggregator()
        
        assert aggregator.newsapi_key is None
        assert aggregator.worldnewsapi_key is None
        assert aggregator.gnews_api_key is None
        assert aggregator.enable_cache is False
        assert aggregator.keywords == []
        assert aggregator.languages == ["tr", "en"]
        assert aggregator.domains == []
        assert aggregator.max_results == 100
        assert aggregator.time_range == TimeRangeEnum.LAST_24_HOURS

    def test_initialization_with_api_keys(self):
        """Test initialization with API keys."""
        aggregator = NewsAggregator(
            newsapi_key="newsapi_key_123",
            worldnewsapi_key="worldnews_key_456",
            gnews_api_key="gnews_key_789"
        )
        
        assert aggregator.newsapi_key == "newsapi_key_123"
        assert aggregator.worldnewsapi_key == "worldnews_key_456"
        assert aggregator.gnews_api_key == "gnews_key_789"

    def test_initialization_with_cache_enabled(self):
        """Test initialization with cache enabled."""
        aggregator = NewsAggregator(enable_cache=True)
        assert aggregator.enable_cache is True


class TestNewsAggregatorConfigure:
    """Tests for NewsAggregator.configure method."""

    def test_configure_languages(self):
        """Test configuring languages."""
        aggregator = NewsAggregator()
        aggregator.configure(languages=["en", "de", "fr"])
        
        assert aggregator.languages == ["en", "de", "fr"]

    def test_configure_domains(self):
        """Test configuring domains."""
        aggregator = NewsAggregator()
        aggregator.configure(domains=["bbc.com", "cnn.com"])
        
        assert aggregator.domains == ["bbc.com", "cnn.com"]

    def test_configure_max_results(self):
        """Test configuring max_results."""
        aggregator = NewsAggregator()
        aggregator.configure(max_results=50)
        
        assert aggregator.max_results == 50

    def test_configure_time_range(self):
        """Test configuring time_range."""
        aggregator = NewsAggregator()
        aggregator.configure(time_range="last_week")
        
        assert aggregator.time_range == TimeRangeEnum.LAST_WEEK

    def test_configure_invalid_time_range_keeps_default(self):
        """Test configuring with invalid time_range keeps default."""
        aggregator = NewsAggregator()
        original_time_range = aggregator.time_range
        aggregator.configure(time_range="invalid_range")
        
        assert aggregator.time_range == original_time_range

    def test_configure_custom_dates(self):
        """Test configuring custom date range."""
        aggregator = NewsAggregator()
        aggregator.configure(
            time_range="custom",
            custom_start_date="2024-01-01",
            custom_end_date="2024-01-31"
        )
        
        assert aggregator.time_range == TimeRangeEnum.CUSTOM
        assert aggregator.custom_start_date == "2024-01-01"
        assert aggregator.custom_end_date == "2024-01-31"


class TestNewsAggregatorUpdateKeywords:
    """Tests for NewsAggregator.update_keywords method."""

    def test_update_keywords_with_list(self):
        """Test updating keywords with a list."""
        aggregator = NewsAggregator()
        aggregator.update_keywords(["football", "soccer", "sports"])
        
        assert aggregator.keywords == ["football", "soccer", "sports"]

    def test_update_keywords_with_nested_list(self):
        """Test updating keywords with nested list (edge case)."""
        aggregator = NewsAggregator()
        aggregator.update_keywords([["football", "soccer"]])
        
        assert aggregator.keywords == ["football", "soccer"]

    def test_update_keywords_with_empty_list(self):
        """Test updating keywords with empty list."""
        aggregator = NewsAggregator()
        aggregator.keywords = ["old", "keywords"]
        aggregator.update_keywords([])
        
        assert aggregator.keywords == []

    def test_update_keywords_filters_non_strings(self):
        """Test that non-string values are filtered."""
        aggregator = NewsAggregator()
        aggregator.update_keywords(["valid", 123, "also_valid", None])
        
        assert aggregator.keywords == ["valid", "also_valid"]


class TestNewsAggregatorGetDateRange:
    """Tests for NewsAggregator.get_date_range method."""

    def test_get_date_range_custom(self):
        """Test getting custom date range."""
        aggregator = NewsAggregator()
        aggregator.configure(
            time_range="custom",
            custom_start_date="2024-06-01",
            custom_end_date="2024-06-30"
        )
        
        date_range = aggregator.get_date_range()
        
        assert date_range["from"] == "2024-06-01"
        assert date_range["to"] == "2024-06-30"

    def test_get_date_range_default_24_hours(self):
        """Test default 24 hour date range."""
        aggregator = NewsAggregator()
        
        date_range = aggregator.get_date_range()
        
        # Should have from and to keys
        assert "from" in date_range
        assert "to" in date_range
        # Both should be valid date format
        assert len(date_range["from"]) == 10  # YYYY-MM-DD
        assert len(date_range["to"]) == 10

    def test_get_date_range_returns_date_format(self):
        """Test that date range returns YYYY-MM-DD format."""
        aggregator = NewsAggregator()
        aggregator.configure(time_range="last_week")
        
        date_range = aggregator.get_date_range()
        
        # Verify format by parsing
        from_date = datetime.strptime(date_range["from"], "%Y-%m-%d")
        to_date = datetime.strptime(date_range["to"], "%Y-%m-%d")
        
        # Should be roughly 7 days apart
        diff = to_date - from_date
        assert diff.days >= 6 and diff.days <= 7


class TestNewsAggregatorExtractDomain:
    """Tests for NewsAggregator._extract_domain method."""

    def test_extract_domain_with_www(self):
        """Test extracting domain from URL with www."""
        aggregator = NewsAggregator()
        domain = aggregator._extract_domain("https://www.bbc.com/news/article-123")
        
        assert domain == "Bbc"

    def test_extract_domain_without_www(self):
        """Test extracting domain from URL without www."""
        aggregator = NewsAggregator()
        domain = aggregator._extract_domain("https://cnn.com/news/article")
        
        assert domain == "Cnn"

    def test_extract_domain_invalid_url(self):
        """Test extracting domain from invalid URL."""
        aggregator = NewsAggregator()
        domain = aggregator._extract_domain("not-a-valid-url")
        
        # Should return "Unknown" or a reasonable fallback
        assert domain is not None

    def test_extract_domain_empty_url(self):
        """Test extracting domain from empty URL."""
        aggregator = NewsAggregator()
        domain = aggregator._extract_domain("")
        
        assert domain == "Unknown"
