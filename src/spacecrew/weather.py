"""
Weather utilities - Cloud cover from Open-Meteo API.
No API key required, 10k requests/day free.
"""

import time

import requests
from datetime import datetime, timezone
from typing import Optional

USER_AGENT = "spacecrew (https://github.com/jakub-ginal/spacecrew)"

# Cache for cloud cover responses (1 hour)
_cloud_cache = {}
_CACHE_DURATION = 3600  # 1 hour in seconds


def get_cloud_cover(lat: float, lon: float, timestamp: datetime, allow_network: bool = True) -> Optional[int]:
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
    
    # Check cache (fresh, then stale fallback when offline)
    cache_key = f"{lat:.2f},{lon:.2f},{date_str}"
    cached = _cloud_cache.get(cache_key)
    if cached:
        age = timestamp.timestamp() - cached['timestamp']
        if age < _CACHE_DURATION:
            if hour < len(cached['data']):
                return cached['data'][hour]
        elif not allow_network:
            if hour < len(cached['data']):
                return cached['data'][hour]
    
    if not allow_network:
        return None

    # Fetch from Open-Meteo (short retry, UA header)
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "cloudcover",
        "timezone": "UTC",
        "start_date": date_str,
        "end_date": date_str
    }
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(2):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
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
                return None
        except Exception:
            if attempt == 0:
                time.sleep(0.5)
            continue

    # Network failed: return stale value if we have one
    if cached and hour < len(cached['data']):
        return cached['data'][hour]

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
