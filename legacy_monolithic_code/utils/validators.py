"""
Validation utilities for the Turkish Sports News API.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
from api.models import NewsRequest, TimeRangeEnum

logger = logging.getLogger(__name__)


def validate_request_data(data: Dict[str, Any]) -> Optional[str]:
    """
    Validate the request data for the news endpoint
    
    Args:
        data: The request data
        
    Returns:
        Error message if validation fails, None otherwise
    """
    # Check if data is a dict
    if not isinstance(data, dict):
        return "Request data must be a JSON object"
    
    # Check if keywords is a list of strings if provided
    if "keywords" in data and not isinstance(data["keywords"], list):
        return "keywords must be a list of strings"
    
    # Check if team_ids is a list of integers if provided
    if "team_ids" in data:
        if not isinstance(data["team_ids"], list):
            return "team_ids must be a list of integers"
        for team_id in data["team_ids"]:
            if not isinstance(team_id, int):
                return "team_ids must be a list of integers"
    
    # Check if time_range is valid if provided
    if "time_range" in data:
        try:
            time_range = data["time_range"]
            if time_range not in [item.value for item in TimeRangeEnum]:
                return f"time_range must be one of {', '.join([item.value for item in TimeRangeEnum])}"
        except Exception:
            return f"time_range must be one of {', '.join([item.value for item in TimeRangeEnum])}"
    
    # Check if custom_start_date and custom_end_date are valid dates if provided
    if "custom_start_date" in data:
        try:
            datetime.fromisoformat(data["custom_start_date"])
        except ValueError:
            return "custom_start_date must be a valid ISO format date (YYYY-MM-DDThh:mm:ss)"
    
    if "custom_end_date" in data:
        try:
            datetime.fromisoformat(data["custom_end_date"])
        except ValueError:
            return "custom_end_date must be a valid ISO format date (YYYY-MM-DDThh:mm:ss)"
    
    # Check if custom date range is valid
    if "custom_start_date" in data and "custom_end_date" in data:
        try:
            start_date = datetime.fromisoformat(data["custom_start_date"])
            end_date = datetime.fromisoformat(data["custom_end_date"])
            if start_date > end_date:
                return "custom_start_date must be before custom_end_date"
        except ValueError:
            pass  # Already handled above
    
    return None
