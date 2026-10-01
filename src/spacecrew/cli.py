import argparse
import importlib.metadata
import json
import os
import re
import sqlite3
import sys
import time
import webbrowser
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import chafa
import requests
from PIL import Image
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

console = Console()

WIKIMEDIA_THUMB_WIDTH: int = 250
CONFIG_DIR = Path.home() / ".config" / "spacecrew"
CACHE_DB = CONFIG_DIR / "cache.db"


class Config:
    """Configuration manager using TOML file."""
    
    DEFAULTS = {
        "nasa_api_key": "",
        "cache_ttl_days": 30,
        "theme": "default",
        "show_iss_position": True,
        "default_mode": "menu",
        "observer_lat": None,
        "observer_lon": None,
        "observer_alt": 0,
    }
    
    def __init__(self):
        self.config_file = CONFIG_DIR / "config.toml"
        self._config = self.DEFAULTS.copy()
        self._toml_load = self._get_toml_loader()
        self.load()
    
    def _get_toml_loader(self):
        try:
            import tomllib
            return tomllib.load
        except ImportError:
            import tomli
            return tomli.load
    
    def load(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, "rb") as f:
                    loaded = self._toml_load(f)
                self._config.update(loaded)
            except Exception:
                pass
    
    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            import tomli_w
            with open(self.config_file, "wb") as f:
                tomli_w.dump(self._config, f)
        except Exception:
            pass
    
    def get(self, key: str, default=None):
        # Check env var first (NASA_API_KEY)
        if key == "nasa_api_key":
            return os.getenv("NASA_API_KEY", self._config.get(key, default))
        return self._config.get(key, default)
    
    def set(self, key: str, value):
        self._config[key] = value
        self.save()


class Cache:
    """Persistent SQLite cache for API responses."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    timestamp INTEGER NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON cache(timestamp)
            """)
            conn.commit()
    
    def get(self, key: str, ttl_days: int = 30) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT data, timestamp FROM cache WHERE key = ?", (key,)
            ).fetchone()
            if row:
                age_days = (time.time() - row["timestamp"]) / 86400
                if age_days <= ttl_days:
                    return json.loads(row["data"])
                else:
                    # Expired, delete
                    conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                    conn.commit()
        return None
    
    def set(self, key: str, data: dict):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, data, timestamp) VALUES (?, ?, ?)",
                (key, json.dumps(data), int(time.time()))
            )
            conn.commit()
    
    def clear_expired(self, ttl_days: int = 30):
        cutoff = int(time.time() - ttl_days * 86400)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM cache WHERE timestamp < ?", (cutoff,))
            conn.commit()


# Global instances
config = Config()
cache = Cache(CACHE_DB)

# In-memory session cache (fallback for current session)
_apod_cache: dict[str, dict] = {}
_launches_cache: list[dict] | None = None
_iss_cache: dict | None = None


def _spacecrew_version() -> str:
    try:
        return importlib.metadata.version("spacecrew")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


USER_AGENT = (
    f"spacecrew/{_spacecrew_version()} "
    f"(https://github.com/jakub-ginal/spacecrew) "
    f"requests/{requests.__version__}"
)


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def to_thumb_url(original_url: str, width: int) -> str:
    m = re.match(r"(.*/commons)/(\w/\w\w)/([^/]+)$", original_url)
    if not m:
        raise ValueError(f"unexpected commons URL format {original_url}")
    base, hashpath, filename = m.groups()
    return f"{base}/thumb/{hashpath}/{filename}/{width}px-{filename}"


def fetch_with_retry(url, headers=None, timeout=5, max_retries=3, backoff_factor=1):
    """Fetch URL with retry on 429 (rate limit) responses."""
    if headers is None:
        headers = {"User-Agent": USER_AGENT}

    for attempt in range(max_retries):
        try:
            res = requests.get(url, headers=headers, timeout=timeout)
            if res.status_code == 200:
                return res
            elif res.status_code == 429:
                if attempt < max_retries - 1:
                    wait_time = backoff_factor * (2 ** attempt)
                    time.sleep(wait_time)
                    continue
            return res
        except requests.RequestException:
            if attempt == max_retries - 1:
                raise
            time.sleep(backoff_factor * (2 ** attempt))
    return None


def fetch_space_data():
    if _global_offline:
        cached = cache.get("people:space", config.get("cache_ttl_days", 30))
        if cached and "people" in cached:
            return cached["people"]
        return None
    
    url = "https://corquaid.github.io/international-space-station-APIs/JSON/people-in-space.json"
    try:
        res = fetch_with_retry(url, timeout=5)
        if res and res.status_code == 200:
            data = res.json()
            cache.set("people:space", data)
            return data["people"]
    except Exception:
        pass
    return None


def group_people_by_station(people):
    iss_groups = defaultdict(list)
    tiangong_groups = defaultdict(list)

    for p in people:
        craft = p.get("spacecraft", "Unknown")
        if p.get("iss"):
            iss_groups[craft].append(p)
        else:
            tiangong_groups[craft].append(p)

    return iss_groups, tiangong_groups


def build_tree_menu(people_count, iss_groups, tiangong_groups):
    tree = Tree(f"[bold white]PEOPLE IN SPACE ({people_count})[/bold white]")
    missions = []
    num = 1

    iss_node = tree.add("[bold green]ISS[/bold green]")
    for craft, members in iss_groups.items():
        m_node = iss_node.add(f"[bold cyan]{num}. {craft}[/bold cyan]")
        for m in members:
            m_node.add(f"{m.get('name')} ({m.get('country')})")
        missions.append((craft, members))
        num += 1

    tiangong_node = tree.add("[bold deep_sky_blue]Tiangong[/bold deep_sky_blue]")
    for craft, members in tiangong_groups.items():
        m_node = tiangong_node.add(f"[bold cyan]{num}. {craft}[/bold cyan]")
        for m in members:
            m_node.add(f"{m.get('name')} ({m.get('country')})")
        missions.append((craft, members))
        num += 1

    return tree, missions


def fetch_photo_panel(url):
    if not url:
        return Panel(Text("No photo", style="dim red"), title="Photo", expand=False)

    try:
        res = fetch_with_retry(url, timeout=5)
        if res and res.status_code == 200:
            img = Image.open(BytesIO(res.content)).convert("RGB")
            width, height = img.size
            pixels = img.tobytes()

            config = chafa.CanvasConfig()
            config.width = 28
            config.height = 16

            canvas = chafa.Canvas(config)
            canvas.draw_all_pixels(
                chafa.PixelType.CHAFA_PIXEL_RGB8, pixels, width, height, width * 3
            )
            out = canvas.print().decode("utf-8")

            return Panel(Text.from_ansi(out), title="Photo", expand=False)
    except Exception:
        pass

    return Panel(Text("No photo", style="dim red"), title="Photo", expand=False)


def create_mission_table(craft, members):
    table = Table(title=f"Mission: {craft}")
    table.add_column("No.", style="cyan", justify="right")
    table.add_column("Name", style="bold white")
    table.add_column("Country", style="green")

    for i, m in enumerate(members, 1):
        table.add_row(str(i), str(m.get("name")), str(m.get("country")))

    return table


def calculate_space_experience(launched_timestamp, previous_days):
    if not launched_timestamp:
        return "N/A", f"{previous_days} days"

    dt = datetime.fromtimestamp(launched_timestamp)
    launched_str = dt.strftime("%Y-%m-%d %H:%M UTC")

    current_mission_days = (time.time() - launched_timestamp) / 86400
    total_days = previous_days + current_mission_days

    total_str = f"{total_days:.1f} days ({previous_days}p + {current_mission_days:.1f}c)"
    return launched_str, total_str


def create_profile_table(person):
    table = Table(title=f"Profile: {person.get('name')}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white", max_width=40)

    table.add_row("Country", f"{person.get('country')} {person.get('flag', '')}")
    table.add_row("Position", str(person.get("position") or "N/A"))
    table.add_row("Agency", str(person.get("agency") or "N/A"))
    table.add_row("Spacecraft", str(person.get("spacecraft") or "N/A"))

    launched_ts = person.get("launched")
    prev_days = person.get("days_in_space", 0)
    launched_date, total_experience = calculate_space_experience(launched_ts, prev_days)

    table.add_row("Launched At", launched_date)
    table.add_row("Time in Space", total_experience)

    links = [
        ("Image URL", person.get("image")),
        ("Wikipedia", person.get("url")),
        ("X (Twitter)", person.get("twitter")),
        ("Instagram", person.get("instagram")),
    ]

    for label, link_url in links:
        if link_url:
            table.add_row(label, f"[link={link_url}]Open Link[/link]")
        else:
            table.add_row(label, "N/A")

    return table


def show_astronaut_view(person):
    clear_screen()
    img_url = person.get("image")
    if "thumb" not in img_url:
        img_url = to_thumb_url(img_url, WIKIMEDIA_THUMB_WIDTH)
    photo_panel = fetch_photo_panel(img_url)
    profile_table = create_profile_table(person)
    console.print(Columns([photo_panel, profile_table]))
    input("\nPress Enter to return to menu...")


def handle_mission_view(craft, members):
    clear_screen()
    console.print(create_mission_table(craft, members))

    astro_choice = input("\nSelect astronaut number (or 'menu'/'quit'): ").strip().lower()

    if astro_choice == "quit":
        return "quit"
    elif astro_choice == "menu":
        return "menu"

    if astro_choice.isdigit():
        a_idx = int(astro_choice) - 1
        if 0 <= a_idx < len(members):
            show_astronaut_view(members[a_idx])

    return "ok"


def get_nasa_api_key() -> str:
    return config.get("nasa_api_key", "DEMO_KEY")


def fetch_apod_date(target_date: str | None):
    """Fetch APOD for specific date (YYYY-MM-DD) or today if None."""
    cache_key = target_date or "today"
    mem_key = f"apod:{cache_key}"
    
    # Check memory cache first
    if mem_key in _apod_cache:
        return _apod_cache[mem_key]
    
    # Check persistent cache
    cached = cache.get(mem_key, config.get("cache_ttl_days", 30))
    if cached:
        _apod_cache[mem_key] = cached
        return cached
    
    if _global_offline:
        return None
    
    base_url = "https://api.nasa.gov/planetary/apod"
    params = {"api_key": get_nasa_api_key()}
    if target_date:
        params["date"] = target_date

    url = f"{base_url}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
    try:
        res = fetch_with_retry(url, timeout=10)
        if res and res.status_code == 200:
            data = res.json()
            _apod_cache[mem_key] = data
            cache.set(mem_key, data)
            return data
    except Exception:
        pass
    return None


def show_apod_view(target_date: str | None = None):
    while True:
        clear_screen()
        date_label = target_date or "today"
        console.print(f"[bold cyan]Fetching NASA APOD for {date_label}...[/bold cyan]\n")

        apod = fetch_apod_date(target_date)
        if not apod:
            console.print("[bold red]Error: Could not fetch APOD data[/bold red]")
            input("\nPress Enter to return to menu...")
            return

        title = apod.get("title", "Unknown")
        date = apod.get("date", "Unknown")
        explanation = apod.get("explanation", "No explanation available")
        media_type = apod.get("media_type", "image")
        url = apod.get("url", "")
        hdurl = apod.get("hdurl", "")
        copyright_text = apod.get("copyright", "")
        author = apod.get("author", "")  # Not always present

        if media_type == "image":
            img_url = hdurl if hdurl else url
            photo_panel = fetch_photo_panel(img_url)
        else:
            photo_panel = Panel(Text(f"[Video] {url}", style="dim yellow"), title="Media", expand=False)

        info_text = Text()
        info_text.append(f"Title: ", style="bold cyan")
        info_text.append(f"{title}\n", style="white")
        info_text.append(f"Date: ", style="bold cyan")
        info_text.append(f"{date}\n", style="white")
        if author:
            info_text.append(f"Author: ", style="bold cyan")
            info_text.append(f"{author}\n", style="white")
        if copyright_text:
            info_text.append(f"Copyright: ", style="bold cyan")
            info_text.append(f"{copyright_text}\n", style="white")
        if hdurl:
            info_text.append(f"HD URL: ", style="bold cyan")
            info_text.append(f"[link={hdurl}]Open in browser[/link]\n", style="blue")
        info_text.append(f"\nExplanation:\n", style="bold cyan")
        info_text.append(explanation, style="white")

        info_panel = Panel(info_text, title="APOD Info", expand=False)

        console.print(Columns([photo_panel, info_panel]))

        actions = []
        if media_type == "image" and hdurl:
            actions.append("[cyan]o[/cyan] - Open HD in browser")
        actions.append("[cyan]p[/cyan] - Previous day")
        actions.append("[cyan]Enter[/cyan] - Back to menu")

        console.print(f"\n[bold yellow]Actions:[/bold yellow]  {'  '.join(actions)}")
        action = input("> ").strip().lower()

        if action == "o" and media_type == "image" and hdurl:
            webbrowser.open(hdurl)
            console.print("[green]Opened in browser[/green]")
            time.sleep(1)
        elif action == "p":
            # Calculate previous day
            try:
                current = datetime.fromisoformat(date) if date != "Unknown" else datetime.now()
            except ValueError:
                current = datetime.now()
            prev_date = (current - timedelta(days=1)).date().isoformat()
            target_date = prev_date
            continue
        else:
            return


def show_iss_position():
    """Show current ISS position."""
    clear_screen()
    console.print("[bold cyan]Fetching ISS position...[/bold cyan]\n")
    
    data = fetch_iss_position()
    if not data:
        console.print("[bold red]Error: Could not fetch ISS position[/bold red]")
        input("\nPress Enter to return to menu...")
        return
    
    from rich.panel import Panel
    console.print(Panel(format_iss_position(data), title="ISS Tracker", border_style="cyan"))
    
    console.print("\n[bold yellow]Actions:[/bold yellow]  [cyan]r[/cyan] - Refresh  [cyan]Enter[/cyan] - Back")
    choice = input("> ").strip().lower()
    if choice == "r":
        global _iss_cache
        _iss_cache = None
        show_iss_position()


# Launches feature
LAUNCHES_API_URL = "https://ll.thespacedevs.com/2.2.0/launch/upcoming/"


def fetch_launches(limit: int = 15) -> list[dict]:
    """Fetch upcoming launches from The Space Devs API."""
    global _launches_cache
    cache_key = f"launches:{limit}"
    
    # Check memory cache first
    if _launches_cache is not None:
        return _launches_cache
    
    # Check persistent cache
    cached = cache.get(cache_key, config.get("cache_ttl_days", 30))
    if cached:
        _launches_cache = cached
        return cached
    
    if _global_offline:
        return []

    params = {
        "limit": limit,
        "mode": "compact",
        "ordering": "window_start",
    }
    url = f"{LAUNCHES_API_URL}?{'&'.join(f'{k}={v}' for k, v in params.items())}"

    try:
        res = fetch_with_retry(url, timeout=10)
        if res and res.status_code == 200:
            data = res.json()
            launches = data.get("results", [])
            _launches_cache = launches
            cache.set(cache_key, launches)
            return launches
    except Exception:
        pass
    return []


def fetch_iss_position() -> dict | None:
    """Fetch current ISS position - prefer wheretheiss.at (real-time TLE) over open-notify."""
    global _iss_cache
    
    if _iss_cache is not None:
        return _iss_cache
    
    # In offline mode, ignore TTL and return any cached data
    ttl = 30 if _global_offline else 1/1440
    cached = cache.get("iss:position", ttl)
    if cached:
        _iss_cache = cached
        return cached
    
    if _global_offline:
        return None
    
    # Try wheretheiss.at first (more accurate - real-time TLE calculation)
    try:
        res = fetch_with_retry("https://api.wheretheiss.at/v1/satellites/25544", timeout=20, max_retries=2)
        if res and res.status_code == 200:
            data = res.json()
            timestamp = data.get("timestamp", 0)
            if timestamp > 0:
                _iss_cache = {
                    "message": "success",
                    "iss_position": {
                        "latitude": str(data.get("latitude", "")),
                        "longitude": str(data.get("longitude", "")),
                    },
                    "timestamp": timestamp,
                    "source": "wheretheiss_at",
                    "altitude": data.get("altitude"),
                    "velocity": data.get("velocity"),
                    "visibility": data.get("visibility"),
                }
                cache.set("iss:position", _iss_cache)
                return _iss_cache
    except Exception:
        pass
    
    # Fallback to open-notify
    try:
        res = fetch_with_retry("http://api.open-notify.org/iss-now.json", timeout=5)
        if res and res.status_code == 200:
            data = res.json()
            if data.get("message") == "success":
                timestamp = data.get("timestamp", 0)
                _iss_cache = {
                    "message": "success",
                    "iss_position": {
                        "latitude": data["iss_position"]["latitude"],
                        "longitude": data["iss_position"]["longitude"],
                    },
                    "timestamp": timestamp,
                    "source": "open_notify",
                }
                cache.set("iss:position", _iss_cache)
                return _iss_cache
    except Exception:
        pass
    
    console.print("[red]All ISS position sources failed[/red]")
    return None


def get_location_name(lat: float, lon: float) -> str:
    """Get country/region name from coordinates using reverse geocoding."""
    try:
        # Use a simple free API - OpenStreetMap Nominatim
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=3&addressdetails=1"
        headers = {"User-Agent": USER_AGENT}
        res = requests.get(url, headers=headers, timeout=5)
        if res and res.status_code == 200:
            data = res.json()
            address = data.get("address", {})
            # Try to get country
            country = address.get("country")
            if country:
                return country
            # Check for ocean/sea
            for key in ["sea", "ocean", "water_body", "strait", "bay", "gulf"]:
                if key in address:
                    return f"Over {address[key]}"
            # Check for other geographic features
            for key in ["island", "archipelago", "continent"]:
                if key in address:
                    return address[key]
    except Exception:
        pass
    
    # Fallback: rough ocean detection
    if lat < -60:
        return "Over Southern Ocean / Antarctica"
    elif lat > 60:
        return "Over Arctic Ocean"
    elif -60 <= lat <= 60:
        # Rough ocean detection by longitude
        if -180 <= lon <= -70 or 100 <= lon <= 180:
            return "Over Pacific Ocean"
        elif -70 < lon < 20:
            return "Over Atlantic Ocean"
        elif 20 <= lon < 100:
            return "Over Indian Ocean"
    return "Unknown"


def format_iss_position(data: dict) -> str:
    """Format ISS position for display."""
    if not data:
        return "[red]Unable to fetch ISS position[/red]"
    
    pos = data.get("iss_position", {})
    lat = pos.get("latitude", "N/A")
    lon = pos.get("longitude", "N/A")
    timestamp = data.get("timestamp", 0)
    
    dt = datetime.fromtimestamp(timestamp) if timestamp else datetime.now()
    time_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # Try to get location name
    location_name = "Unknown"
    try:
        lat_f = float(lat)
        lon_f = float(lon)
        location_name = get_location_name(lat_f, lon_f)
    except (ValueError, TypeError):
        pass
    
    # Get extra data from WhereTheISS.at if available
    extra_info = ""
    if data.get("source") == "wheretheiss_at":
        # We need to fetch fresh data for altitude/velocity
        try:
            res = fetch_with_retry("https://api.wheretheiss.at/v1/satellites/25544", timeout=15, max_retries=1)
            if res and res.status_code == 200:
                w_data = res.json()
                altitude = w_data.get("altitude")
                velocity = w_data.get("velocity")
                visibility = w_data.get("visibility")
                if altitude:
                    extra_info += f"Altitude:  {altitude:.1f} km\n"
                if velocity:
                    extra_info += f"Velocity:  {velocity:.0f} km/h\n"
                if visibility:
                    extra_info += f"Visibility: {visibility}\n"
        except Exception:
            pass
    
    # Google Maps link with red pin marker
    maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
    
    text = Text()
    text.append("ISS Current Position\n", style="bold cyan")
    text.append(f"Latitude:  {lat}\n", style="white")
    text.append(f"Longitude: {lon}\n", style="white")
    text.append(f"Location:  {location_name}\n", style="white")
    if extra_info:
        text.append(f"{extra_info}", style="white")
    text.append(f"Time:      {time_str}\n", style="white")
    text.append(f"\nView on map: ", style="dim")
    text.append(f"[link={maps_url}]Google Maps (with marker)[/link]", style="blue")
    
    return text


# Space Weather feature
DONKI_API_BASE = "https://ccmc.gsfc.nasa.gov/DONKI/WS/get"
NOAA_SWPC_BASE = "https://services.swpc.noaa.gov"


def fetch_space_weather(limit: int = 5) -> dict:
    """Fetch space weather data from NOAA/DONKI APIs."""
    global _space_weather_cache
    cache_key = f"space_weather:{limit}"
    
    if _space_weather_cache is not None:
        return _space_weather_cache
    
    cached = cache.get(cache_key, config.get("cache_ttl_days", 1))
    if cached:
        _space_weather_cache = cached
        return cached
    
    if _global_offline:
        return {}
    
    result = {"flares": [], "cmes": [], "kp_index": [], "forecast": ""}
    
    # Fetch recent solar flares (last 10 days)
    try:
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=10)
        url = f"{DONKI_API_BASE}/FLR?startDate={start_date}&endDate={end_date}&api_key={get_nasa_api_key()}"
        res = fetch_with_retry(url, timeout=10)
        if res and res.status_code == 200:
            flares = res.json()
            # Sort by peak time, most recent first
            flares.sort(key=lambda x: x.get("peakTime", ""), reverse=True)
            result["flares"] = flares[:limit]
    except Exception:
        pass
    
    # Fetch recent CMEs (last 10 days)
    try:
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=10)
        url = f"{DONKI_API_BASE}/CME?startDate={start_date}&endDate={end_date}&api_key={get_nasa_api_key()}"
        res = fetch_with_retry(url, timeout=10)
        if res and res.status_code == 200:
            cmes = res.json()
            cmes.sort(key=lambda x: x.get("startTime", ""), reverse=True)
            result["cmes"] = cmes[:limit]
    except Exception:
        pass
    
    # Fetch planetary Kp index (last 24 hours)
    try:
        url = f"{NOAA_SWPC_BASE}/json/planetary_k_index_1m.json"
        res = fetch_with_retry(url, timeout=10)
        if res and res.status_code == 200:
            kp_data = res.json()
            # Get last 24 entries (3-hour intervals)
            result["kp_index"] = kp_data[-24:] if len(kp_data) > 24 else kp_data
    except Exception:
        pass
    
    # Fetch 3-day forecast text
    try:
        url = f"{NOAA_SWPC_BASE}/text/3-day-forecast.txt"
        res = fetch_with_retry(url, timeout=10)
        if res and res.status_code == 200:
            result["forecast"] = res.text
    except Exception:
        pass
    
    _space_weather_cache = result
    cache.set(cache_key, result)
    return result


_space_weather_cache: dict | None = None


def format_flare_class(class_type: str) -> str:
    """Format flare class with color."""
    if not class_type:
        return "[dim]Unknown[/dim]"
    if class_type.startswith("X"):
        return f"[bold red]{class_type}[/bold red]"
    elif class_type.startswith("M"):
        return f"[bold yellow]{class_type}[/bold yellow]"
    elif class_type.startswith("C"):
        return f"[bold cyan]{class_type}[/bold cyan]"
    elif class_type.startswith("B"):
        return f"[bold green]{class_type}[/bold green]"
    return class_type


def format_kp_index(kp: float) -> str:
    """Format Kp index with color based on storm level."""
    if kp >= 5:
        return f"[bold red]{kp:.1f}[/bold red]"
    elif kp >= 4:
        return f"[bold yellow]{kp:.1f}[/bold yellow]"
    elif kp >= 3:
        return f"[bold cyan]{kp:.1f}[/bold cyan]"
    return f"[green]{kp:.1f}[/green]"


def create_space_weather_table(data: dict) -> Table:
    """Create table for space weather overview."""
    table = Table(title="Space Weather Overview", show_header=True, header_style="bold cyan", expand=True)
    table.add_column("Category", style="cyan", width=18, no_wrap=True)
    table.add_column("Details", style="white")
    
    # Solar Flares
    flares = data.get("flares", [])
    if flares:
        flare_text = ""
        for i, flare in enumerate(flares[:3]):
            cls = format_flare_class(flare.get("classType", ""))
            peak = flare.get("peakTime", "").replace("T", " ").replace("Z", " UTC")
            region = flare.get("activeRegionNum", "N/A")
            flare_text += f"{cls}  {peak}  AR{region}\n"
        table.add_row("Recent Flares", flare_text.strip())
    else:
        table.add_row("Recent Flares", "[dim]No recent flares[/dim]")
    
    # CMEs
    cmes = data.get("cmes", [])
    if cmes:
        cme_text = ""
        for i, cme in enumerate(cmes[:3]):
            start = cme.get("startTime", "").replace("T", " ").replace("Z", " UTC")
            speed = "N/A"
            if cme.get("cmeAnalyses"):
                speed = f"{cme['cmeAnalyses'][0].get('speed', 0):.0f} km/s"
            cme_text += f"{start}  {speed}\n"
        table.add_row("Recent CMEs", cme_text.strip())
    else:
        table.add_row("Recent CMEs", "[dim]No recent CMEs[/dim]")
    
    # Kp Index (current and max last 24h)
    kp_data = data.get("kp_index", [])
    if kp_data:
        current_kp = kp_data[-1].get("kp_index", 0) if kp_data else 0
        max_kp = max((d.get("kp_index", 0) for d in kp_data), default=0)
        table.add_row("Current Kp", format_kp_index(current_kp))
        table.add_row("Max Kp (24h)", format_kp_index(max_kp))
        # Storm level
        if max_kp >= 5:
            storm = "[bold red]G1-G5 Storm[/bold red]"
        elif max_kp >= 4:
            storm = "[bold yellow]G1 Minor Storm[/bold yellow]"
        else:
            storm = "[green]Quiet[/green]"
        table.add_row("Storm Level", storm)
    else:
        table.add_row("Kp Index", "[dim]No data[/dim]")
    
    return table


def show_space_weather():
    """Show space weather dashboard."""
    clear_screen()
    console.print("[bold cyan]Fetching space weather data...[/bold cyan]\n")
    
    data = fetch_space_weather()
    if not data:
        console.print("[bold red]Error: Could not fetch space weather data[/bold red]")
        input("\nPress Enter to return to menu...")
        return
    
    while True:
        clear_screen()
        console.print(create_space_weather_table(data))
        
        # Show forecast summary
        forecast = data.get("forecast", "")
        if forecast:
            # Extract key lines
            lines = forecast.split("\n")
            key_lines = [l for l in lines if any(k in l.lower() for k in ["kp", "storm", "flare", "cme", "geomagnetic", "radiation", "g1", "g2", "g3", "g4", "g5"])]
            if key_lines:
                forecast_text = Text()
                forecast_text.append("3-Day Forecast Highlights:\n", style="bold cyan")
                for line in key_lines[:6]:
                    forecast_text.append(f"  {line.strip()}\n", style="white")
                console.print(Panel(forecast_text, title="NOAA SWPC Forecast", border_style="cyan"))
        
        console.print("\n[bold yellow]Actions:[/bold yellow]  [cyan]r[/cyan] - Refresh  [cyan]Enter[/cyan] - Back")
        choice = input("> ").strip().lower()
        
        if not choice:
            return
        if choice == "r":
            global _space_weather_cache
            _space_weather_cache = None
            console.print("[dim]Refreshing...[/dim]")
            time.sleep(1)
            return show_space_weather()


# Satellite Passes feature
CELESTRAK_TLE_URLS = {
    "iss": "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=tle",
    "stations": "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle",
    "starlink": "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle",
    "iridium": "https://celestrak.org/NORAD/elements/gp.php?GROUP=iridium&FORMAT=tle",
    "gps": "https://celestrak.org/NORAD/elements/gp.php?GROUP=gps-ops&FORMAT=tle",
    "geo": "https://celestrak.org/NORAD/elements/gp.php?GROUP=geo&FORMAT=tle",
    "weather": "https://celestrak.org/NORAD/elements/gp.php?GROUP=weather&FORMAT=tle",
    "science": "https://celestrak.org/NORAD/elements/gp.php?GROUP=science&FORMAT=tle",
    "amateur": "https://celestrak.org/NORAD/elements/gp.php?GROUP=amateur&FORMAT=tle",
    "military": "https://celestrak.org/NORAD/elements/gp.php?GROUP=military&FORMAT=tle",
    "radar": "https://celestrak.org/NORAD/elements/gp.php?GROUP=radar&FORMAT=tle",
    "cubesat": "https://celestrak.org/NORAD/elements/gp.php?GROUP=cubesat&FORMAT=tle",
    "other": "https://celestrak.org/NORAD/elements/gp.php?GROUP=other&FORMAT=tle",
}


def fetch_tle_data(group: str = "stations") -> list[dict]:
    """Fetch TLE data from Celestrak."""
    global _tle_cache
    cache_key = f"tle:{group}"
    
    if _tle_cache is not None:
        return _tle_cache
    
    cached = cache.get(cache_key, 1)  # 1 day TTL
    if cached:
        _tle_cache = cached
        return cached
    
    if _global_offline:
        return []
    
    url = CELESTRAK_TLE_URLS.get(group, CELESTRAK_TLE_URLS["stations"])
    try:
        res = fetch_with_retry(url, timeout=15)
        if res and res.status_code == 200:
            lines = res.text.strip().split("\n")
            satellites = []
            for i in range(0, len(lines), 3):
                if i + 2 < len(lines):
                    name = lines[i].strip()
                    line1 = lines[i + 1].strip()
                    line2 = lines[i + 2].strip()
                    if line1.startswith("1 ") and line2.startswith("2 "):
                        satellites.append({"name": name, "line1": line1, "line2": line2})
            _tle_cache = satellites
            cache.set(cache_key, satellites)
            return satellites
    except Exception:
        pass
    return []


_tle_cache: list[dict] | None = None


def calculate_visible_passes(satellites: list[dict], obs_lat: float, obs_lon: float, obs_alt: float, days: int = 3) -> list[dict]:
    """Calculate visible passes for satellites from observer location."""
    from sgp4.api import Satrec, jday
    from math import degrees, radians, sin, cos, sqrt, atan2, asin
    
    passes = []
    now = datetime.now(timezone.utc)
    
    # Observer position in ECEF
    obs_lat_rad = radians(obs_lat)
    obs_lon_rad = radians(obs_lon)
    R_earth = 6371.0 + obs_alt / 1000.0  # km
    obs_x = R_earth * cos(obs_lat_rad) * cos(obs_lon_rad)
    obs_y = R_earth * cos(obs_lat_rad) * sin(obs_lon_rad)
    obs_z = R_earth * sin(obs_lat_rad)
    
    for sat_data in satellites:
        try:
            sat = Satrec.twoline2rv(sat_data["line1"], sat_data["line2"])
            sat_name = sat_data["name"]
            
            # Track pass state
            in_pass = False
            pass_start = None
            pass_max_el = 0
            pass_max_time = None
            pass_start_az = 0
            pass_end_az = 0
            
            # Check every minute for better accuracy
            for day_offset in range(days):
                check_date = now + timedelta(days=day_offset)
                for minute_offset in range(0, 1440, 1):  # every minute
                    check_time = check_date.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=minute_offset)
                    jd, fr = jday(check_time.year, check_time.month, check_time.day, check_time.hour, check_time.minute, check_time.second)
                    e, r, v = sat.sgp4(jd, fr)
                    if e != 0:
                        continue
                    
                    # r is in TEME frame (km), convert to ECEF
                    # TEME to ECEF rotation: rotate around Z by GAST
                    # Greenwich Apparent Sidereal Time (simplified)
                    gast = (280.46061837 + 360.98564736629 * (jd - 2451545.0) + fr * 360.98564736629) % 360
                    gast_rad = radians(gast)
                    
                    # Rotate TEME to ECEF (Z-axis rotation)
                    cos_g = cos(gast_rad)
                    sin_g = sin(gast_rad)
                    sat_x = r[0] * cos_g - r[1] * sin_g
                    sat_y = r[0] * sin_g + r[1] * cos_g
                    sat_z = r[2]
                    
                    # Vector from observer to satellite
                    dx = sat_x - obs_x
                    dy = sat_y - obs_y
                    dz = sat_z - obs_z
                    
                    # Range
                    range_km = sqrt(dx*dx + dy*dy + dz*dz)
                    
                    # Convert to topocentric horizon coordinates
                    # Local East, North, Up basis vectors
                    east_x = -sin(obs_lon_rad)
                    east_y = cos(obs_lon_rad)
                    east_z = 0
                    
                    north_x = -sin(obs_lat_rad) * cos(obs_lon_rad)
                    north_y = -sin(obs_lat_rad) * sin(obs_lon_rad)
                    north_z = cos(obs_lat_rad)
                    
                    up_x = cos(obs_lat_rad) * cos(obs_lon_rad)
                    up_y = cos(obs_lat_rad) * sin(obs_lon_rad)
                    up_z = sin(obs_lat_rad)
                    
                    # Project satellite vector onto local basis
                    east = dx * east_x + dy * east_y + dz * east_z
                    north = dx * north_x + dy * north_y + dz * north_z
                    up = dx * up_x + dy * up_y + dz * up_z
                    
                    # Elevation and azimuth
                    horizontal_dist = sqrt(east*east + north*north)
                    elevation = degrees(atan2(up, horizontal_dist))
                    azimuth = degrees(atan2(east, north)) % 360
                    
                    # Sun position (simplified)
                    sun_el, sun_az = calculate_sun_position(check_time, obs_lat, obs_lon)
                    
                    # Check visibility: satellite above 10°, sun below -6° (civil twilight), satellite illuminated
                    sat_illuminated = is_satellite_illuminated(r, check_time)
                    ground_dark = sun_el < -6
                    above_horizon = elevation > 10
                    
                    visible = above_horizon and ground_dark and sat_illuminated
                    
                    if visible and not in_pass:
                        # Pass start
                        in_pass = True
                        pass_start = check_time
                        pass_max_el = elevation
                        pass_max_time = check_time
                        pass_start_az = azimuth
                    elif visible and in_pass:
                        # Continue pass, track max elevation
                        if elevation > pass_max_el:
                            pass_max_el = elevation
                            pass_max_time = check_time
                    elif not visible and in_pass:
                        # Pass end
                        in_pass = False
                        pass_end_az = azimuth
                        if pass_start and pass_max_el > 15:  # Only keep passes with decent max elevation
                            duration = (check_time - pass_start).total_seconds() / 60
                            if duration > 1:  # At least 1 minute
                                passes.append({
                                    "name": sat_name,
                                    "start": pass_start,
                                    "end": check_time,
                                    "max_elevation": pass_max_el,
                                    "max_time": pass_max_time,
                                    "start_azimuth": pass_start_az,
                                    "end_azimuth": pass_end_az,
                                    "duration": duration,
                                    "visible": True
                                })
        
        except Exception:
            continue
    
    return passes


def calculate_sun_position(time: datetime, lat: float, lon: float) -> tuple[float, float]:
    """Calculate sun elevation and azimuth (simplified)."""
    from math import radians, degrees, sin, cos, tan, atan2, asin
    
    # Days since J2000
    jd = time.timestamp() / 86400 + 2440587.5
    n = jd - 2451545.0
    
    # Mean longitude of sun
    L = radians(280.460 + 0.9856474 * n)
    # Mean anomaly
    g = radians(357.528 + 0.9856003 * n)
    # Ecliptic longitude
    lambda_sun = L + radians(1.915) * sin(g) + radians(0.020) * sin(2*g)
    # Obliquity of ecliptic
    epsilon = radians(23.439 - 0.0000004 * n)
    
    # Right ascension and declination
    ra = atan2(cos(epsilon) * sin(lambda_sun), cos(lambda_sun))
    dec = asin(sin(epsilon) * sin(lambda_sun))
    
    # Greenwich hour angle
    gmst = 6.697375 + 0.0657098242 * n + time.hour + time.minute/60 + time.second/3600
    lmst = gmst + lon/15
    ha = radians(lmst * 15 - degrees(ra))
    
    lat_rad = radians(lat)
    # Elevation
    el = asin(sin(dec) * sin(lat_rad) + cos(dec) * cos(lat_rad) * cos(ha))
    # Azimuth
    az = atan2(-sin(ha), tan(dec) * cos(lat_rad) - sin(lat_rad) * cos(ha))
    
    return degrees(el), degrees(az) % 360


def is_satellite_illuminated(sat_pos, time: datetime) -> bool:
    """Check if satellite is illuminated by sun (simplified)."""
    from math import sqrt, radians, sin, cos, atan2, asin
    # Sun direction vector (unit vector from Earth to sun)
    sat_x, sat_y, sat_z = sat_pos
    sat_dist = sqrt(sat_x*sat_x + sat_y*sat_y + sat_z*sat_z)
    
    # Sun direction vector (unit vector from Earth to sun)
    n = time.timestamp() / 86400 + 2440587.5 - 2451545.0
    L = radians(280.460 + 0.9856474 * n)
    g = radians(357.528 + 0.9856003 * n)
    lambda_sun = L + radians(1.915) * sin(g) + radians(0.020) * sin(2*g)
    epsilon = radians(23.439 - 0.0000004 * n)
    ra = atan2(cos(epsilon) * sin(lambda_sun), cos(lambda_sun))
    dec = asin(sin(epsilon) * sin(lambda_sun))
    
    sun_x = cos(ra) * cos(dec)
    sun_y = sin(ra) * cos(dec)
    sun_z = sin(dec)
    
    # Satellite position vector from Earth center
    dot = sat_x * sun_x + sat_y * sun_y + sat_z * sun_z
    
    # Satellite is illuminated if not in Earth's umbra
    # Umbra condition: dot(R, S) < -R_earth (satellite behind Earth, within shadow cone)
    # R_earth = 6371 km
    return dot > -6371


def show_satellite_passes():
    """Show satellite passes menu and predictions."""
    from rich.prompt import Prompt
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    
    # Get or set observer location
    lat = config.get("observer_lat")
    lon = config.get("observer_lon")
    alt = config.get("observer_alt", 0)
    
    if lat is None or lon is None:
        clear_screen()
        console.print("[bold cyan]Satellite Passes - Set Your Location[/bold cyan]\n")
        console.print("Enter your location for accurate pass predictions.\n")
        
        try:
            lat_str = Prompt.ask("Latitude (e.g., 51.5074)", default="0")
            lon_str = Prompt.ask("Longitude (e.g., -0.1278)", default="0")
            alt_str = Prompt.ask("Altitude in meters (optional)", default="0")
            
            lat = float(lat_str)
            lon = float(lon_str)
            alt = float(alt_str)
            
            config.set("observer_lat", lat)
            config.set("observer_lon", lon)
            config.set("observer_alt", alt)
            console.print(f"\n[green]Location saved: {lat:.4f}, {lon:.4f}, {alt}m[/green]")
            time.sleep(1)
        except Exception:
            console.print("[red]Invalid coordinates[/red]")
            time.sleep(1)
            return
    
    while True:
        clear_screen()
        console.print(f"[bold cyan]Satellite Passes[/bold cyan] (Location: {lat:.4f}, {lon:.4f})\n")
        console.print("  [bold white]1[/bold white] Predict passes for next 3 days")
        console.print("  [bold white]2[/bold white] Predict passes for specific satellite")
        console.print("  [bold white]3[/bold white] Change location")
        console.print("  [bold white]4[/bold white] Back to main menu\n")
        
        choice = Prompt.ask("Select option", choices=["1", "2", "3", "4"], default="1")
        
        if choice == "4":
            return
        elif choice == "3":
            # Reset location
            config.set("observer_lat", None)
            config.set("observer_lon", None)
            console.print("[yellow]Location reset[/yellow]")
            time.sleep(1)
            continue
        elif choice == "1":
            predict_passes(lat, lon, alt, days=3)
        elif choice == "2":
            predict_specific_satellite(lat, lon, alt)


def predict_passes(lat: float, lon: float, alt: float, days: int = 3):
    """Predict passes for all tracked satellites."""
    clear_screen()
    console.print(f"[bold cyan]Fetching TLE data and calculating passes for {days} days...[/bold cyan]\n")
    
    # Fetch TLE data for stations (ISS, Tiangong, etc.) and Starlink
    all_satellites = []
    for group in ["stations", "starlink"]:
        sats = fetch_tle_data(group)
        all_satellites.extend(sats)
    
    if not all_satellites:
        console.print("[bold red]Error: Could not fetch satellite data[/bold red]")
        input("\nPress Enter to return...")
        return
    
    console.print(f"[green]Loaded {len(all_satellites)} satellites[/green]\n")
    console.print("[dim]Calculating passes...[/dim]")
    
    passes = calculate_visible_passes(all_satellites, lat, lon, alt, days)
    
    if not passes:
        console.print("[yellow]No visible passes found for the next {} days[/yellow]".format(days))
        input("\nPress Enter to return...")
        return
    
    # Group by satellite
    from collections import defaultdict
    passes_by_sat = defaultdict(list)
    for p in passes:
        passes_by_sat[p["name"]].append(p)
    
    # Sort by first pass time
    sorted_sats = sorted(passes_by_sat.items(), key=lambda x: x[1][0]["start"])
    
    clear_screen()
    console.print(f"[bold cyan]Visible Satellite Passes ({days} days)[/bold cyan]")
    console.print(f"Location: {lat:.4f}, {lon:.4f}, {alt}m\n")
    
    for name, sat_passes in sorted_sats:
        if not sat_passes:
            continue
        console.print(f"\n[bold white]{name}[/bold white]")
        for p in sat_passes[:5]:  # Limit to 5 passes per satellite
            start_str = p["start"].strftime("%m-%d %H:%M UTC")
            end_str = p["end"].strftime("%H:%M")
            max_el = p["max_elevation"]
            dir_str = f"{p['start_azimuth']:.0f}°→{p['end_azimuth']:.0f}°"
            dur = int(p["duration"])
            visible = "✓" if p["visible"] else "✗"
            color = "green" if p["visible"] else "dim"
            console.print(f"  [{color}]{start_str}-{end_str}  max {max_el:.0f}°  {dir_str}  {dur}min  {visible}[/{color}]")
    
    input("\nPress Enter to return...")


def predict_specific_satellite(lat: float, lon: float, alt: float):
    """Predict passes for a specific satellite."""
    clear_screen()
    console.print("[bold cyan]Specific Satellite Prediction[/bold cyan]\n")
    console.print("[yellow]Feature in development[/yellow]")
    input("\nPress Enter to return...")
    """Format ISS position for display."""
    if not data:
        return "[red]Unable to fetch ISS position[/red]"
    
    pos = data.get("iss_position", {})
    lat = pos.get("latitude", "N/A")
    lon = pos.get("longitude", "N/A")
    timestamp = data.get("timestamp", 0)
    
    dt = datetime.fromtimestamp(timestamp) if timestamp else datetime.now()
    time_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # Try to get location name
    location_name = "Unknown"
    try:
        lat_f = float(lat)
        lon_f = float(lon)
        location_name = get_location_name(lat_f, lon_f)
    except (ValueError, TypeError):
        pass
    
    # Get extra data from WhereTheISS.at if available
    extra_info = ""
    if data.get("source") == "wheretheiss_at":
        # We need to fetch fresh data for altitude/velocity
        try:
            res = fetch_with_retry("https://api.wheretheiss.at/v1/satellites/25544", timeout=15, max_retries=1)
            if res and res.status_code == 200:
                w_data = res.json()
                altitude = w_data.get("altitude")
                velocity = w_data.get("velocity")
                visibility = w_data.get("visibility")
                if altitude:
                    extra_info += f"Altitude:  {altitude:.1f} km\n"
                if velocity:
                    extra_info += f"Velocity:  {velocity:.0f} km/h\n"
                if visibility:
                    extra_info += f"Visibility: {visibility}\n"
        except Exception:
            pass
    
    # Google Maps link with red pin marker
    maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
    
    text = Text()
    text.append("ISS Current Position\n", style="bold cyan")
    text.append(f"Latitude:  {lat}\n", style="white")
    text.append(f"Longitude: {lon}\n", style="white")
    text.append(f"Location:  {location_name}\n", style="white")
    if extra_info:
        text.append(f"{extra_info}", style="white")
    text.append(f"Time:      {time_str}\n", style="white")
    text.append(f"\nView on map: ", style="dim")
    text.append(f"[link={maps_url}]Google Maps (with marker)[/link]", style="blue")
    
    return text


def format_launch_datetime(iso_str: str) -> str:
    """Format ISO datetime to readable local time."""
    if not iso_str:
        return "TBD"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return iso_str


def get_launch_countdown(window_start: str) -> str:
    """Calculate time until launch window start."""
    if not window_start or window_start == "TBD":
        return ""
    try:
        dt = datetime.fromisoformat(window_start.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if dt <= now:
            return "[bold red]LAUNCHED[/bold red]"
        diff = dt - now
        days = diff.days
        hours, rem = divmod(diff.seconds, 3600)
        minutes, _ = divmod(rem, 60)
        if days > 0:
            return f"[bold cyan]T-{days}d {hours:02d}h {minutes:02d}m[/bold cyan]"
        elif hours > 0:
            color = "bold yellow" if hours < 1 else "bold cyan"
            return f"[{color}]T-{hours}h {minutes:02d}m[/{color}]"
        else:
            return f"[bold red]T-{minutes}m[/bold red]"
    except Exception:
        return ""


def format_launch_status(status: dict) -> str:
    """Format launch status with color."""
    if not status:
        return "[dim]Unknown[/dim]"
    name = status.get("name", "Unknown")
    status_id = status.get("id", 0)
    if status_id == 1:
        return f"[bold green]{name}[/bold green]"
    elif status_id == 2:
        return f"[bold yellow]{name}[/bold yellow]"
    elif status_id == 3:
        return f"[bold red]{name}[/bold red]"
    elif status_id == 4:
        return f"[dim]{name}[/dim]"
    return name


def create_launches_table(launches: list[dict]) -> Table:
    """Create table for launches list - compact single-line format."""
    table = Table(title="Upcoming Launches", show_header=True, header_style="bold cyan", expand=True)
    table.add_column("#", style="cyan", justify="right", width=4, no_wrap=True)
    table.add_column("Mission", style="bold white", min_width=40, overflow="fold")
    table.add_column("Rocket / Provider", style="green", min_width=25, overflow="fold")
    table.add_column("Date (UTC)", style="white", width=18, no_wrap=True)
    table.add_column("Status", style="white", width=12, no_wrap=True)

    for idx, launch in enumerate(launches, 1):
        mission = launch.get("name", "Unknown")
        rocket = launch.get("rocket", {}).get("configuration", {}).get("name", "TBD")
        provider = launch.get("launch_service_provider", {}).get("name", "TBD")
        window_start = format_launch_datetime(launch.get("window_start", ""))
        status = format_launch_status(launch.get("status", {}))

        rocket_provider = f"{rocket} / {provider}"

        table.add_row(
            str(idx),
            mission,
            rocket_provider,
            window_start,
            status,
        )

    return table


def create_launches_panel_list(launches: list[dict]) -> list:
    """Create a list of Panels for each launch - cleaner than table."""
    from rich.panel import Panel
    from rich.text import Text

    panels = []
    for idx, launch in enumerate(launches, 1):
        mission = launch.get("name", "Unknown")
        rocket = launch.get("rocket", {}).get("configuration", {}).get("name", "TBD")
        provider = launch.get("launch_service_provider", {}).get("name", "TBD")
        window_start = format_launch_datetime(launch.get("window_start", ""))
        status = launch.get("status", {}).get("name", "Unknown")
        status_id = launch.get("status", {}).get("id", 0)
        countdown = get_launch_countdown(launch.get("window_start", ""))

        # Color based on status
        if status_id == 1:
            status_style = "bold green"
        elif status_id == 2:
            status_style = "bold yellow"
        elif status_id == 3:
            status_style = "bold red"
        else:
            status_style = "dim"

        text = Text()
        text.append(f"{idx}. ", style="bold cyan")
        text.append(f"{mission}\n", style="bold white")
        text.append(f"    {rocket} / {provider}\n", style="green")
        text.append(f"    {window_start}  ", style="white")
        if countdown:
            countdown_text = Text.from_markup(countdown)
            text.append(" ")
            text.append_text(countdown_text)
            text.append("  ")
        text.append(f"[{status}]", style=status_style)

        panels.append(Panel(text, border_style="dim", padding=(0, 1)))

    return panels


def create_launch_detail_table(launch: dict) -> Table:
    """Create detailed table for a single launch."""
    table = Table(title=f"Launch Details: {launch.get('name', 'Unknown')}", show_header=True, expand=True)
    table.add_column("Property", style="cyan", width=22, no_wrap=True)
    table.add_column("Value", style="white")

    # Basic info
    table.add_row("Mission", launch.get("name", "N/A"))
    desc = launch.get("description", "N/A")
    if desc and len(desc) > 300:
        desc = desc[:300] + "..."
    table.add_row("Description", desc)

    # Rocket
    rocket = launch.get("rocket", {}).get("configuration", {})
    table.add_row("Rocket", rocket.get("name", "N/A"))
    table.add_row("Rocket Family", rocket.get("family", "N/A"))
    table.add_row("Variant", rocket.get("variant", "N/A"))

    # Provider
    provider = launch.get("launch_service_provider", {})
    table.add_row("Provider", provider.get("name", "N/A"))
    table.add_row("Provider Type", provider.get("type", "N/A"))

    # Pad & Location
    pad = launch.get("pad", {})
    table.add_row("Launch Pad", pad.get("name", "N/A"))
    location = pad.get("location", {})
    table.add_row("Location", f"{location.get('name', 'N/A')}, {location.get('country_code', 'N/A')}")

    # Times
    table.add_row("Window Start", format_launch_datetime(launch.get("window_start", "")))
    table.add_row("Window End", format_launch_datetime(launch.get("window_end", "")))

    # Status
    status = launch.get("status", {})
    table.add_row("Status", status.get("name", "N/A"))
    table.add_row("Status Description", status.get("description", "N/A"))

    # Links
    has_links = False
    if launch.get("webcast_live") and launch.get("streams"):
        streams = launch.get("streams", [])
        if streams:
            table.add_row("Webcast", f"[link={streams[0].get('url', '')}]Watch Live[/link]")
            has_links = True

    if launch.get("video_url"):
        table.add_row("Video URL", f"[link={launch.get('video_url')}]Open[/link]")
        has_links = True

    if launch.get("info_url"):
        table.add_row("Info URL", f"[link={launch.get('info_url')}]Open[/link]")
        has_links = True

    if launch.get("wiki_url"):
        table.add_row("Wikipedia", f"[link={launch.get('wiki_url')}]Open[/link]")
        has_links = True

    # Image
    if launch.get("image"):
        table.add_row("Mission Patch", f"[link={launch.get('image')}]View Image[/link]")
        has_links = True

    if not has_links:
        table.add_row("Links", "[dim]No links available yet[/dim]")

    return table


def show_launches_list():
    """Show list of upcoming launches."""
    clear_screen()
    console.print("[bold cyan]Fetching upcoming launches...[/bold cyan]\n")

    launches = fetch_launches()
    if not launches:
        console.print("[bold red]Error: Could not fetch launches data[/bold red]")
        input("\nPress Enter to return to menu...")
        return

    while True:
        clear_screen()
        panels = create_launches_panel_list(launches)
        for panel in panels:
            console.print(panel)
        console.print("\n[bold yellow]Actions:[/bold yellow]  [cyan]1-{n}[/cyan] - Details  [cyan]r[/cyan] - Refresh  [cyan]Enter[/cyan] - Back".format(n=len(launches)))
        choice = input("> ").strip().lower()

        if not choice:
            return
        if choice == "r":
            global _launches_cache
            _launches_cache = None
            console.print("[dim]Refreshing...[/dim]")
            time.sleep(1)
            return show_launches_list()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(launches):
                show_launch_detail(launches[idx])


def show_launch_detail(launch: dict):
    """Show detailed view of a launch."""
    while True:
        clear_screen()
        console.print(create_launch_detail_table(launch))

        console.print("\n[bold yellow]Actions:[/bold yellow]  [cyan]w[/cyan] - Open webcast  [cyan]Enter[/cyan] - Back")
        choice = input("> ").strip().lower()

        if choice == "w" and launch.get("webcast_live") and launch.get("streams"):
            url = launch["streams"][0].get("url", "")
            if url:
                webbrowser.open(url)
                console.print("[green]Opened webcast in browser[/green]")
                time.sleep(1)
        else:
            return


def show_main_menu():
    """Show main menu with 6 options."""
    from rich.align import Align
    from rich.panel import Panel
    from rich.text import Text

    menu_text = Text()
    menu_text.append("         SPACECREW", style="bold white")
    menu_text.append("\n\n")
    menu_text.append("  1 ", style="bold white")
    menu_text.append("People in Space", style="cyan")
    menu_text.append("\n")
    menu_text.append("  2 ", style="bold white")
    menu_text.append("NASA APOD", style="cyan")
    menu_text.append("\n")
    menu_text.append("  3 ", style="bold white")
    menu_text.append("Upcoming Launches", style="cyan")
    menu_text.append("\n")
    menu_text.append("  4 ", style="bold white")
    menu_text.append("ISS Position", style="cyan")
    menu_text.append("\n")
    menu_text.append("  5 ", style="bold white")
    menu_text.append("Space Weather", style="cyan")
    menu_text.append("\n")
    menu_text.append("  6 ", style="bold white")
    menu_text.append("Satellite Passes", style="cyan")
    menu_text.append("\n")
    menu_text.append("  7 ", style="bold white")
    menu_text.append("Exit", style="cyan")

    panel = Panel(
        Align.center(menu_text),
        border_style="white",
        title_align="center",
    )
    console.print(panel)


def handle_people_in_space():
    """Handle the people in space workflow."""
    clear_screen()
    people = fetch_space_data()

    if people is None:
        console.print("[bold red]Error: No internet connection. Please check your network and try again.[/bold red]")
        input("\nPress Enter to return to menu...")
        return

    iss_groups, tiangong_groups = group_people_by_station(people)
    tree, missions = build_tree_menu(len(people), iss_groups, tiangong_groups)

    console.print(tree)
    console.print("\n[bold yellow]Commands:[/bold yellow] [cyan]menu[/cyan] - Back  [cyan]quit[/cyan] - Exit")
    choice = input("\n> ").strip().lower()

    if choice == "quit":
        return "quit"
    elif choice == "menu":
        return "menu"

    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(missions):
            craft, members = missions[idx]
            result = handle_mission_view(craft, members)
            if result == "quit":
                return "quit"
    return "ok"


_global_offline = False


def parse_args():
    parser = argparse.ArgumentParser(
        prog="spacecrew",
        description="Spacecrew - Track people in space, NASA APOD, launches, ISS position, and space weather",
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {_spacecrew_version()}"
    )
    parser.add_argument(
        "--mode",
        choices=["people", "apod", "launches", "iss", "weather", "passes"],
        help="Start directly in a specific mode",
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="Disable persistent cache for this run"
    )
    parser.add_argument(
        "--clear-cache", action="store_true", help="Clear expired cache entries and exit"
    )
    parser.add_argument(
        "--offline", action="store_true", help="Offline mode: use only cached data, no network requests"
    )
    return parser.parse_args()


def main():
    global _global_offline
    args = parse_args()
    
    if args.offline:
        _global_offline = True
        console.print("[yellow]Offline mode: using cached data only[/yellow]")
        time.sleep(0.5)
    
    if args.clear_cache:
        cache.clear_expired(config.get("cache_ttl_days", 30))
        console.print("[green]Cache cleared[/green]")
        return
    
    # Direct mode handling
    if args.mode:
        if args.mode == "people":
            handle_people_in_space()
        elif args.mode == "apod":
            show_apod_view()
        elif args.mode == "launches":
            show_launches_list()
        elif args.mode == "iss":
            show_iss_position()
        elif args.mode == "weather":
            show_space_weather()
        elif args.mode == "passes":
            show_satellite_passes()
        return
    
    while True:
        clear_screen()
        show_main_menu()
        console.print()
        choice = console.input("[bold cyan]Select option [1-7]: [/bold cyan]").strip().lower()

        if choice in ("7", "quit", "exit", "q"):
            break
        elif choice == "1":
            result = handle_people_in_space()
            if result == "quit":
                break
        elif choice == "2":
            show_apod_view()
        elif choice == "3":
            show_launches_list()
        elif choice == "4":
            show_iss_position()
        elif choice == "5":
            show_space_weather()
        elif choice == "6":
            show_satellite_passes()
        else:
            console.print("[red]Invalid option[/red]")
            time.sleep(1)


if __name__ == "__main__":
    main()