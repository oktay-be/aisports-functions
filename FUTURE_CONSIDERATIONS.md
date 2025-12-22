# Future Considerations

This document outlines potential improvements and architectural enhancements for the AISports pipeline. These items are captured for future reference and should be evaluated based on actual usage patterns and business requirements.

---

## 1. Region-Specific Within-Run Grouping Threshold

### Current State
- **Cross-run deduplication**: Now supports region-specific thresholds (TR: 0.7, EU: 0.9)
- **Within-run grouping**: Uses a uniform threshold (0.8) for all regions

### Consideration
The within-run grouping threshold (`GROUPING_THRESHOLD`) currently applies uniformly across all regions. Similar to cross-run deduplication, different regions may benefit from region-specific grouping thresholds:

- **Turkish content (TR)**: Higher content overlap across sources may warrant a lower grouping threshold (e.g., 0.75) to group related articles more aggressively
- **European content (EU)**: More diverse content may need a higher threshold (e.g., 0.85) to avoid grouping unrelated articles

### Implementation Approach
If implemented, follow the same pattern used for cross-run deduplication:

```python
# Environment variables
GROUPING_THRESHOLD_TR = float(os.getenv('GROUPING_THRESHOLD_TR', '0.8'))
GROUPING_THRESHOLD_EU = float(os.getenv('GROUPING_THRESHOLD_EU', '0.8'))

# Pass to GroupingService
region_grouping_thresholds = {
    'tr': GROUPING_THRESHOLD_TR,
    'eu': GROUPING_THRESHOLD_EU,
}
```

### Decision Factors
- Monitor grouping behavior across regions after deploying region-specific dedup thresholds
- Analyze merge_decider output to see if groups contain unrelated articles (threshold too low) or miss related articles (threshold too high)
- Consider user feedback on article grouping quality

---

## 2. GCS-Based Configuration for Runtime Updates

### Current State
All thresholds and configuration parameters are managed via environment variables:
- `CROSS_RUN_DEDUP_THRESHOLD`
- `CROSS_RUN_DEDUP_THRESHOLD_TR`
- `CROSS_RUN_DEDUP_THRESHOLD_EU`
- `GROUPING_THRESHOLD`

Changing these values requires redeploying Cloud Functions.

### Consideration
Implement a configuration file stored in GCS that functions read at startup or periodically. This enables:

1. **Runtime updates**: Change thresholds without redeployment
2. **A/B testing**: Test different threshold values across runs
3. **Region expansion**: Add new regions without code changes
4. **Audit trail**: GCS versioning provides configuration history

### Proposed Structure

```
gs://aisports-scraping/config/
├── pipeline_config.json          # Main configuration
├── pipeline_config_backup.json   # Backup/previous version
```

**Example `pipeline_config.json`:**
```json
{
  "version": "1.0.0",
  "updated_at": "2024-12-22T10:00:00Z",
  "cross_run_dedup": {
    "default_threshold": 0.7,
    "region_thresholds": {
      "tr": 0.7,
      "eu": 0.9,
      "us": 0.85
    }
  },
  "grouping": {
    "default_threshold": 0.8,
    "region_thresholds": {
      "tr": 0.8,
      "eu": 0.8
    }
  },
  "embedding": {
    "model": "text-embedding-004",
    "batch_size": 40
  }
}
```

### Implementation Approach

```python
class ConfigManager:
    def __init__(self, storage_client, bucket_name, config_path="config/pipeline_config.json"):
        self.storage_client = storage_client
        self.bucket_name = bucket_name
        self.config_path = config_path
        self._config = None
        self._loaded_at = None
        self._cache_ttl = 300  # 5 minutes
    
    def get_config(self):
        """Load config from GCS with caching."""
        now = datetime.now(timezone.utc)
        if self._config and self._loaded_at:
            if (now - self._loaded_at).total_seconds() < self._cache_ttl:
                return self._config
        
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(self.config_path)
            content = blob.download_as_text()
            self._config = json.loads(content)
            self._loaded_at = now
            logger.info(f"Loaded config version {self._config.get('version')}")
        except Exception as e:
            logger.warning(f"Failed to load GCS config, using env vars: {e}")
            # Fall back to environment variables
            self._config = self._build_config_from_env()
        
        return self._config
    
    def get_cross_run_threshold(self, region=None):
        config = self.get_config()
        thresholds = config.get('cross_run_dedup', {})
        if region and region.lower() in thresholds.get('region_thresholds', {}):
            return thresholds['region_thresholds'][region.lower()]
        return thresholds.get('default_threshold', 0.7)
```

### Decision Factors
- Frequency of threshold adjustments (if rare, env vars are sufficient)
- Operational overhead of managing GCS config files
- Need for A/B testing or gradual rollouts
- Multi-region deployment considerations

### Migration Path
1. Implement ConfigManager with fallback to env vars
2. Deploy and verify env var fallback works
3. Create initial GCS config file
4. Gradually transition to GCS-based config
5. Remove env var dependencies (optional)

---

## 3. Additional Considerations (Low Priority)

### 3.1 Source-Specific Thresholds
Different sources may have different content characteristics. Consider:
```json
{
  "source_thresholds": {
    "fanatik.com.tr": 0.65,
    "bbc.com": 0.9
  }
}
```

### 3.2 Time-Based Threshold Decay
Older articles might need different similarity thresholds than same-day articles. For example, articles from the same day might use 0.7, but cross-day comparison might use 0.8.

### 3.3 Content-Type Thresholds
Breaking news vs. analysis articles might benefit from different thresholds.

---

## Implementation Priority

| Consideration | Priority | Complexity | Impact |
|--------------|----------|------------|--------|
| Region-specific grouping | Medium | Low | Medium |
| GCS-based config | Low | Medium | High (when needed) |
| Source-specific thresholds | Low | Medium | Medium |
| Time-based threshold decay | Low | High | Low |
| Content-type thresholds | Low | High | Low |

---

*Last updated: December 2024*
