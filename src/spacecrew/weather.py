"""
Weather utilities - Cloud cover from Open-Meteo API.
No API key required, 10k requests/day free.
"""

import requests
from datetime import datetime, timezone
from typing import Optional
from functools import lru_cache

# Cache for cloud cover responses (1 hour)
_cloud_cache = {}
_CACHE_DURATION = 3600  # 1 hour in seconds


def get_cloud_cover(lat: float, lon: float, timestamp: datetime) -> Optional[int]:
    """
    Get cloud cover percentage at specific location and time.
    
    Args:
        lat: Latitude in degrees
        lon: Longitude in degrees
        timestamp: UTC datetime for the pass
        
    Returns:
        Cloud cover percentage (0-100) or None if unavailable
    """
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    else:
        timestamp = timestamp.astimezone(timezone.utc)
    
    date_str = timestamp.date().isoformat()
    hour = timestamp.hour
    
    # Check cache
    cache_key = f"{lat:.2f},{lon:.2f},{date_str}"
    if cache_key in _cloud_cache:
        cached = _cloud_cache[cache_key]
        if timestamp.timestamp() - cached['timestamp'] < 3600:
            if hour < len(cached['data']):
                return cached['data'][hour]
    
    # Fetch from Open-Meteo
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "cloudcover",
            "timezone": "UTC",
            "start_date": date_str,
            "end_date": date_str
        }
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            hourly = data.get("hourly", {})
            cloudcovers = hourly.get("cloudcover", [])
            
            # Cache the full day's data
            _cloud_cache[cache_key] = {
                'timestamp': timestamp.timestamp(),
                'data': cloudcovers
            }
            
            if hour < len(cloudcovers):
                return cloudcovers[hour]
    except Exception:
        pass
    
    return None


def clear_cloud_cache():
    """Clear the cloud cover cache."""
    global _cloud_cache
    _cloud_cache = {}


if __name__ == "__main__":
    # Test
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    cover = get_cloud_cover(29.7604, -95.3698, now)
    print(f"Cloud cover: {cover}%")
