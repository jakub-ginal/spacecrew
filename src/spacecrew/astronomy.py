"""
Astronomy calculations - Moon phase using Meeus algorithm.
Zero API calls, unlimited, works offline.
"""

from datetime import datetime, timezone
from math import sin, cos, tan, asin, acos, atan2, radians, degrees, floor


def calculate_moon_phase(date: datetime, lat: float, lon: float) -> dict:
    """
    Calculate moon phase using Meeus algorithm.
    
    Returns:
        dict with: phase_name, illumination_pct, rise_time, set_time, 
                   altitude, azimuth
    """
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    else:
        date = date.astimezone(timezone.utc)
    
    # Julian Day
    jd = date.timestamp() / 86400 + 2440587.5
    
    # Days since J2000
    T = (jd - 2451545.0) / 36525
    
    # Mean elongation of Moon
    D = 297.8501921 + 445267.1114034 * T - 0.0018819 * T * T + T * T * T / 545868
    
    # Mean anomaly of Sun
    M = 357.5291092 + 35999.0502909 * T - 0.0001536 * T * T + T * T * T / 24490000
    
    # Mean anomaly of Moon
    M_prime = 134.9633964 + 477198.8675055 * T + 0.0087414 * T * T + T * T * T / 69699
    
    # Moon's argument of latitude
    F = 93.2720950 + 483202.0175233 * T - 0.0036539 * T * T - T * T * T / 3526000
    
    # Longitude of Moon
    lon_moon = 218.3164477 + 481267.88123421 * T - 0.0015786 * T * T + T * T * T / 538841 - 0.0000014 * T * T * T * T
    
    # Latitude of Moon
    lat_moon = 5.1281221 * sin(radians(F)) + 0.280602 * sin(radians(M_prime + F)) + 0.277693 * sin(radians(M_prime - F)) + 0.173237 * sin(radians(2 * D - F)) + 0.055413 * sin(radians(2 * D + F - M_prime)) + 0.046271 * sin(radians(2 * D - F - M)) + 0.032573 * sin(radians(2 * D + F - M)) + 0.017198 * sin(radians(2 * M_prime + F))
    
    # Distance to Moon
    dist_moon = 385000.56 + 20905.355 * cos(radians(M_prime)) + 3699.111 * cos(radians(2 * D - M_prime)) + 2955.968 * cos(radians(2 * D)) + 569.925 * cos(radians(2 * M_prime)) + 488.889 * cos(radians(2 * D - M)) + 314.9 * cos(radians(2 * D - 2 * M_prime - F)) + 246.158 * cos(radians(2 * D - F)) + 152.138 * cos(radians(2 * D - M_prime - F))
    
    # Sun's longitude
    lon_sun = 280.46646 + 36000.76983 * T + 0.0003032 * T * T
    M = radians(357.5291092 + 35999.0502909 * T - 0.0001536 * T * T + T * T * T / 24490000)
    
    # Phase angle
    i = 180 - D - 6.289 * sin(radians(M_prime)) + 2.1 * sin(radians(M)) - 1.274 * sin(radians(2 * D - M_prime)) - 0.658 * sin(radians(2 * D)) - 0.214 * sin(radians(2 * M_prime)) - 0.11 * sin(radians(D))
    
    # Illumination fraction
    illumination = (1 + cos(radians(i))) / 2
    
    # Phase name from elongation (0=new, 180=full) so waxing/waning differ
    elongation = D % 360
    phase = elongation / 360
    if phase < 0.03 or phase >= 0.97:
        phase_name = "NEW"
    elif phase < 0.22:
        phase_name = "WAXING CRESCENT"
    elif phase < 0.28:
        phase_name = "FIRST QUARTER"
    elif phase < 0.47:
        phase_name = "WAXING GIBBOUS"
    elif phase < 0.53:
        phase_name = "FULL"
    elif phase < 0.72:
        phase_name = "WANING GIBBOUS"
    elif phase < 0.78:
        phase_name = "LAST QUARTER"
    else:
        phase_name = "WANING CRESCENT"
    
    # Moon rise/set (simplified)
    # Using approximate formula
    ra_moon = degrees(atan2(sin(radians(lon_moon)) * cos(radians(23.439 - 0.0000004 * (jd - 2451545.0 / 365.25 * 36525))), cos(radians(lon_moon))))
    dec_moon = degrees(asin(sin(radians(lon_moon)) * sin(radians(23.439 - 0.0000004 * (jd - 2451545.0 / 365.25 * 36525)))))
    
    # Local sidereal time
    gmst = 6.697375 + 0.0657098242 * (jd - 2451545.0) + date.hour + date.minute / 60 + date.second / 3600
    lmst = gmst + lon / 15
    
    # Hour angle
    ha = radians(lmst * 15 - ra_moon)
    
    # Altitude and azimuth
    lat_rad = radians(lat)
    dec_rad = radians(dec_moon)
    
    altitude = degrees(asin(sin(dec_rad) * sin(lat_rad) + cos(dec_rad) * cos(lat_rad) * cos(ha)))
    azimuth = degrees(atan2(-sin(ha), tan(dec_rad) * cos(lat_rad) - sin(lat_rad) * cos(ha))) % 360
    
    # Rise/set times (approximate)
    cos_ha_rise = -tan(lat_rad) * tan(dec_rad)
    if abs(cos_ha_rise) <= 1:
        ha_rise = acos(max(-1, min(1, cos_ha_rise)))
        rise_time = lmst - degrees(ha_rise) / 15
        set_time = lmst + degrees(ha_rise) / 15
        rise_time = rise_time % 24
        set_time = set_time % 24
    else:
        rise_time = None
        set_time = None
    
    return {
        "phase_name": phase_name,
        "illumination_pct": round(illumination * 100, 1),
        "rise_time": rise_time,
        "set_time": set_time,
        "altitude": round(altitude, 1),
        "azimuth": round(azimuth, 1),
        "distance_km": round(dist_moon, 1)
    }


if __name__ == "__main__":
    # Test
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    result = calculate_moon_phase(now, 29.7604, -95.3698)
    print(f"Moon Phase: {result['phase_name']}")
    print(f"Illumination: {result['illumination_pct']}%")
    print(f"Altitude: {result['altitude']}°")
    print(f"Azimuth: {result['azimuth']}°")
    print(f"Rise: {result['rise_time']:.2f}h" if result['rise_time'] else "Rise: N/A")
    print(f"Set: {result['set_time']:.2f}h" if result['set_time'] else "Set: N/A")
