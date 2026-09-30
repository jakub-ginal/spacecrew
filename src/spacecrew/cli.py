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
from datetime import datetime, timedelta
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
    
    cached = cache.get("iss:position", 1/1440)  # 1 minute TTL
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


def format_launch_datetime(iso_str: str) -> str:
    """Format ISO datetime to readable local time."""
    if not iso_str:
        return "TBD"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return iso_str


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
    """Show main menu with 4 options."""
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
        description="Spacecrew - Track people in space, NASA APOD, launches, and ISS position",
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {_spacecrew_version()}"
    )
    parser.add_argument(
        "--mode",
        choices=["people", "apod", "launches", "iss"],
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
        return
    
    while True:
        clear_screen()
        show_main_menu()
        console.print()
        choice = console.input("[bold cyan]Select option [1-5]: [/bold cyan]").strip().lower()

        if choice in ("5", "quit", "exit", "q"):
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
        else:
            console.print("[red]Invalid option[/red]")
            time.sleep(1)


if __name__ == "__main__":
    main()