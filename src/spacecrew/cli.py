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
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.tree import Tree

THEMES = {
    "catppuccin-mocha": Theme({
        "info": "#89b4fa",
        "warning": "#f9e2af",
        "error": "#f38ba8",
        "success": "#a6e3a1",
        "muted": "#6c7086",
        "highlight": "#cdd6f4",
        "title": "#cba6f7",
        "border": "#313244",
        "text": "#cdd6f4",
        "number": "#89b4fa",
        "name": "#cdd6f4",
        "country": "#a6e3a1",
        "rocket": "#fab387",
        "provider": "#f5c2e7",
        "date": "#bac2de",
        "status": "#94e2d5",
    }),
    "tokyo-night": Theme({
        "info": "#7aa2f7",
        "warning": "#e0af68",
        "error": "#f7768e",
        "success": "#9ece6a",
        "muted": "#565f89",
        "highlight": "#c0caf5",
        "title": "#bb9af7",
        "border": "#292e42",
        "text": "#c0caf5",
        "number": "#7aa2f7",
        "name": "#c0caf5",
        "country": "#9ece6a",
        "rocket": "#ff9e64",
        "provider": "#c0caf5",
        "date": "#a9b1d6",
        "status": "#73daca",
    }),
    "gruvbox": Theme({
        "info": "#83a598",
        "warning": "#fabd2f",
        "error": "#fb4934",
        "success": "#b8bb26",
        "muted": "#928374",
        "highlight": "#ebdbb2",
        "title": "#d3869b",
        "border": "#3c3836",
        "text": "#ebdbb2",
        "number": "#83a598",
        "name": "#ebdbb2",
        "country": "#b8bb26",
        "rocket": "#fe8019",
        "provider": "#d3869b",
        "date": "#a89984",
        "status": "#8ec07c",
    }),
    "nord": Theme({
        "info": "#88c0d0",
        "warning": "#ebcb8b",
        "error": "#bf616a",
        "success": "#a3be8c",
        "muted": "#4c566a",
        "highlight": "#eceff4",
        "title": "#b48ead",
        "border": "#3b4252",
        "text": "#eceff4",
        "number": "#88c0d0",
        "name": "#eceff4",
        "country": "#a3be8c",
        "rocket": "#d08770",
        "provider": "#81a1c1",
        "date": "#d8dee9",
        "status": "#8fbcbb",
    }),
    "everforest": Theme({
        "info": "#7fbbb3",
        "warning": "#dbbc7f",
        "error": "#e67e80",
        "success": "#a7c080",
        "muted": "#7a8478",
        "highlight": "#d3c6aa",
        "title": "#d699b6",
        "border": "#3a3f3b",
        "text": "#d3c6aa",
        "number": "#7fbbb3",
        "name": "#d3c6aa",
        "country": "#a7c080",
        "rocket": "#e69875",
        "provider": "#d699b6",
        "date": "#a7c080",
        "status": "#83c092",
    }),
    "rose-pine": Theme({
        "info": "#9ccfd8",
        "warning": "#f6c177",
        "error": "#eb6f92",
        "success": "#31748f",
        "muted": "#6e6a86",
        "highlight": "#e0def4",
        "title": "#c4a7e7",
        "border": "#26233a",
        "text": "#e0def4",
        "number": "#9ccfd8",
        "name": "#e0def4",
        "country": "#31748f",
        "rocket": "#f6c177",
        "provider": "#ebbcba",
        "date": "#908caa",
        "status": "#9ccfd8",
    }),
    "kanagawa": Theme({
        "info": "#7fb4ca",
        "warning": "#c0a36e",
        "error": "#c34043",
        "success": "#76946a",
        "muted": "#727169",
        "highlight": "#dcd7ba",
        "title": "#957fb8",
        "border": "#363646",
        "text": "#dcd7ba",
        "number": "#7fb4ca",
        "name": "#dcd7ba",
        "country": "#76946a",
        "rocket": "#ffa066",
        "provider": "#957fb8",
        "date": "#c8c093",
        "status": "#6a9589",
    }),
    "catppuccin-latte": Theme({
        "info": "#1e66f5",
        "warning": "#df8e1d",
        "error": "#d20f39",
        "success": "#40a02b",
        "muted": "#7287fd",
        "highlight": "#4c4f69",
        "title": "#8839ef",
        "border": "#ccd0da",
        "text": "#4c4f69",
        "number": "#1e66f5",
        "name": "#4c4f69",
        "country": "#40a02b",
        "rocket": "#fe640b",
        "provider": "#8839ef",
        "date": "#5c5f77",
        "status": "#179299",
    }),
}

def get_console(theme_name: str = "catppuccin-mocha") -> Console:
    return Console(theme=THEMES.get(theme_name, THEMES["catppuccin-mocha"]))

console = get_console()


def refresh_console():
    global console
    console = get_console(config.get("theme", "catppuccin-mocha"))


def fetch_with_progress(url: str, description: str = "Fetching...", **kwargs):
    """Fetch URL with a progress spinner."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[info]{task.description}[/info]"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(description, total=None)
        try:
            response = requests.get(url, timeout=kwargs.get("timeout", 30), **kwargs)
            progress.update(task, completed=1)
            return response
        except Exception as e:
            progress.update(task, completed=1)
            raise e


def multi_fetch_with_progress(urls: list[tuple[str, str]], description: str = "Fetching data..."):
    """Fetch multiple URLs with progress bar."""
    results = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[info]{task.description}[/info]"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(description, total=len(urls))
        for url, label in urls:
            try:
                response = requests.get(url, timeout=30)
                results.append((label, response))
            except Exception:
                results.append((label, None))
            progress.advance(task)
    return results


WIKIMEDIA_THUMB_WIDTH: int = 250
CONFIG_DIR = Path.home() / ".config" / "spacecrew"
CACHE_DB = CONFIG_DIR / "cache.db"


class Config:
    """Configuration manager using TOML file."""
    
    DEFAULTS = {
        "nasa_api_key": "",
        "cache_ttl_days": 30,
        "theme": "catppuccin-mocha",
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
        if key == "theme":
            refresh_console()


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


config = Config()
cache = Cache(CACHE_DB)
refresh_console()

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
    table.add_column("No.", style="number", justify="right")
    table.add_column("Name", style="name")
    table.add_column("Country", style="country")

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
    table = Table(title=f"Profile: {person.get('name')}", border_style="border")
    table.add_column("Property", style="number")
    table.add_column("Value", style="text", max_width=40)

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
        info_text.append(f"Title: ", style="title")
        info_text.append(f"{title}\n", style="text")
        info_text.append(f"Date: ", style="title")
        info_text.append(f"{date}\n", style="text")
        if author:
            info_text.append(f"Author: ", style="title")
            info_text.append(f"{author}\n", style="text")
        if copyright_text:
            info_text.append(f"Copyright: ", style="title")
            info_text.append(f"{copyright_text}\n", style="text")
        if hdurl:
            info_text.append(f"HD URL: ", style="title")
            info_text.append(f"[link={hdurl}]Open in browser[/link]\n", style="info")
        info_text.append(f"\nExplanation:\n", style="title")
        info_text.append(explanation, style="text")

        info_panel = Panel(info_text, title="APOD Info", expand=False, border_style="border")

        console.print(Columns([photo_panel, info_panel]))

        actions = []
        if media_type == "image" and hdurl:
            actions.append("[info]o[/info] - Open HD in browser")
        actions.append("[info]p[/info] - Previous day")
        actions.append("[info]Enter[/info] - Back to menu")

        console.print(f"\n[warning]Actions:[/warning]  {'  '.join(actions)}")
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
    console.print("[info]Fetching ISS position...[/info]\n")
    
    data = fetch_iss_position()
    if not data:
        console.print("[error]Error: Could not fetch ISS position[/error]")
        input("\nPress Enter to return to menu...")
        return
    
    from rich.panel import Panel
    console.print(Panel(format_iss_position(data), title="ISS Tracker", border_style="border"))
    
    console.print("\n[warning]Actions:[/warning]  [info]r[/info] - Refresh  [info]Enter[/info] - Back")
    choice = input("> ").strip().lower()
    if choice == "r":
        global _iss_cache
        _iss_cache = None
        show_iss_position()


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
    text.append("ISS Current Position\n", style="title")
    text.append(f"Latitude:  {lat}\n", style="text")
    text.append(f"Longitude: {lon}\n", style="text")
    text.append(f"Location:  {location_name}\n", style="text")
    if extra_info:
        text.append(f"{extra_info}", style="text")
    text.append(f"Time:      {time_str}\n", style="text")
    text.append(f"\nView on map: ", style="muted")
    text.append(f"[link={maps_url}]Google Maps (with marker)[/link]", style="info")
    
    return text


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
        return "[muted]Unknown[/muted]"
    if class_type.startswith("X"):
        return f"[error]{class_type}[/error]"
    elif class_type.startswith("M"):
        return f"[warning]{class_type}[/warning]"
    elif class_type.startswith("C"):
        return f"[info]{class_type}[/info]"
    elif class_type.startswith("B"):
        return f"[success]{class_type}[/success]"
    return class_type


def format_kp_index(kp: float) -> str:
    """Format Kp index with color based on storm level."""
    if kp >= 5:
        return f"[error]{kp:.1f}[/error]"
    elif kp >= 4:
        return f"[warning]{kp:.1f}[/warning]"
    elif kp >= 3:
        return f"[info]{kp:.1f}[/info]"
    return f"[success]{kp:.1f}[/success]"


def create_space_weather_table(data: dict) -> Table:
    """Create table for space weather overview."""
    table = Table(title="Space Weather Overview", show_header=True, header_style="title", expand=True, border_style="border")
    table.add_column("Category", style="number", width=18, no_wrap=True)
    table.add_column("Details", style="text")
    
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
        table.add_row("Recent Flares", "[muted]No recent flares[/muted]")
    
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
        table.add_row("Recent CMEs", "[muted]No recent CMEs[/muted]")
    
    # Kp Index (current and max last 24h)
    kp_data = data.get("kp_index", [])
    if kp_data:
        current_kp = kp_data[-1].get("kp_index", 0) if kp_data else 0
        max_kp = max((d.get("kp_index", 0) for d in kp_data), default=0)
        table.add_row("Current Kp", format_kp_index(current_kp))
        table.add_row("Max Kp (24h)", format_kp_index(max_kp))
        # Storm level
        if max_kp >= 5:
            storm = "[error]G1-G5 Storm[/error]"
        elif max_kp >= 4:
            storm = "[warning]G1 Minor Storm[/warning]"
        else:
            storm = "[success]Quiet[/success]"
        table.add_row("Storm Level", storm)
    else:
        table.add_row("Kp Index", "[muted]No data[/muted]")
    
    return table


def show_space_weather():
    """Show space weather dashboard."""
    clear_screen()
    console.print("[info]Fetching space weather data...[/info]\n")
    
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
                forecast_text.append("3-Day Forecast Highlights:\n", style="title")
                for line in key_lines[:6]:
                    forecast_text.append(f"  {line.strip()}\n", style="text")
                console.print(Panel(forecast_text, title="NOAA SWPC Forecast", border_style="border"))
        
        console.print("\n[warning]Actions:[/warning]  [info]r[/info] - Refresh  [info]Enter[/info] - Back")
        choice = input("> ").strip().lower()
        
        if not choice:
            return
        if choice == "r":
            global _space_weather_cache
            _space_weather_cache = None
            console.print("[muted]Refreshing...[/muted]")
            time.sleep(1)
            return show_space_weather()


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


def fetch_tle_data(group: str = "stations", show_progress: bool = False) -> list[dict]:
    """Fetch TLE data from Celestrak."""
    global _tle_cache
    cache_key = f"tle:{group}"
    
    if group in _tle_cache:
        return _tle_cache[group]
    
    cached = cache.get(cache_key, 1)  # 1 day TTL
    if cached:
        _tle_cache[group] = cached
        return cached
    
    if _global_offline:
        return []
    
    url = CELESTRAK_TLE_URLS.get(group, CELESTRAK_TLE_URLS["stations"])
    try:
        if show_progress:
            res = fetch_with_progress(url, f"Fetching {group} TLE...", timeout=15)
        else:
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
            _tle_cache[group] = satellites
            cache.set(cache_key, satellites)
            return satellites
    except Exception:
        pass
    return []


_tle_cache: dict[str, list[dict]] = {}


def calculate_visible_passes(satellites: list[dict], obs_lat: float, obs_lon: float, obs_alt: float, days: int = 3) -> list[dict]:
    """Calculate visible passes for satellites from observer location."""
    from sgp4.api import Satrec, jday
    from math import degrees, radians, sin, cos, sqrt, atan2, asin, acos
    
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
            pass_max_pos = None
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
                        pass_max_pos = r  # store TEME position at max
                        pass_start_az = azimuth
                    elif visible and in_pass:
                        # Continue pass, track max elevation
                        if elevation > pass_max_el:
                            pass_max_el = elevation
                            pass_max_time = check_time
                            pass_max_pos = r  # update TEME position at max
                    elif not visible and in_pass:
                        # Pass end
                        in_pass = False
                        pass_end_az = azimuth
                        if pass_start and pass_max_el > 15:  # Only keep passes with decent max elevation
                            duration = (check_time - pass_start).total_seconds() / 60
                            if duration > 1:  # At least 1 minute
                                # Calculate magnitude at max elevation
                                std_mag = get_std_magnitude(sat_name)
                                
                                # Convert max_pos from TEME to ECEF
                                jd_max, fr_max = jday(pass_max_time.year, pass_max_time.month, pass_max_time.day, pass_max_time.hour, pass_max_time.minute, pass_max_time.second)
                                gast_max = (280.46061837 + 360.98564736629 * (jd_max - 2451545.0) + fr_max * 360.98564736629) % 360
                                gast_max_rad = radians(gast_max)
                                cos_g = cos(gast_max_rad)
                                sin_g = sin(gast_max_rad)
                                sat_x = pass_max_pos[0] * cos_g - pass_max_pos[1] * sin_g
                                sat_y = pass_max_pos[0] * sin_g + pass_max_pos[1] * cos_g
                                sat_z = pass_max_pos[2]
                                
                                # Range at max elevation
                                dx = sat_x - obs_x
                                dy = sat_y - obs_y
                                dz = sat_z - obs_z
                                range_km = sqrt(dx*dx + dy*dy + dz*dz)
                                
                                # Calculate phase angle
                                # Sun position vector
                                sun_el, sun_az = calculate_sun_position(pass_max_time, obs_lat, obs_lon)
                                n_sun = pass_max_time.timestamp() / 86400 + 2440587.5 - 2451545.0
                                L_sun = radians(280.460 + 0.9856474 * n_sun)
                                g_sun = radians(357.528 + 0.9856003 * n_sun)
                                lambda_sun = L_sun + radians(1.915) * sin(g_sun) + radians(0.020) * sin(2*g_sun)
                                epsilon = radians(23.439 - 0.0000004 * n_sun)
                                ra_sun = atan2(cos(epsilon) * sin(lambda_sun), cos(lambda_sun))
                                dec_sun = asin(sin(epsilon) * sin(lambda_sun))
                                sun_x = cos(ra_sun) * cos(dec_sun)
                                sun_y = sin(ra_sun) * cos(dec_sun)
                                sun_z = sin(dec_sun)
                                
                                # Phase angle
                                sat_dist = sqrt(sat_x**2 + sat_y**2 + sat_z**2)
                                to_sun_x = sun_x * sat_dist - sat_x
                                to_sun_y = sun_y * sat_dist - sat_y
                                to_sun_z = sun_z * sat_dist - sat_z
                                to_obs_x = -dx
                                to_obs_y = -dy
                                to_obs_z = -dz
                                
                                sun_dist = sqrt(to_sun_x**2 + to_sun_y**2 + to_sun_z**2)
                                obs_dist = range_km
                                
                                if sun_dist > 0 and obs_dist > 0:
                                    to_sun_x /= sun_dist
                                    to_sun_y /= sun_dist
                                    to_sun_z /= sun_dist
                                    to_obs_x /= obs_dist
                                    to_obs_y /= obs_dist
                                    to_obs_z /= obs_dist
                                    dot = to_sun_x * to_obs_x + to_sun_y * to_obs_y + to_sun_z * to_obs_z
                                    dot = max(-1.0, min(1.0, dot))
                                    phase_angle = degrees(acos(dot))
                                else:
                                    phase_angle = 0.0
                                
                                # Calculate magnitude
                                magnitude = calculate_magnitude(std_mag, range_km, phase_angle)
                                
                                # Calculate rarity
                                rarity = get_rarity_bonus(sat_name)
                                
                                # Sun elevation at max time
                                sun_el_max, _ = calculate_sun_position(pass_max_time, obs_lat, obs_lon)
                                
                                # Quality score
                                quality = calculate_pass_quality(pass_max_el, duration, sun_el_max, magnitude, rarity)
                                
                                passes.append({
                                    "name": sat_name,
                                    "start": pass_start,
                                    "end": check_time,
                                    "max_elevation": pass_max_el,
                                    "max_time": pass_max_time,
                                    "start_azimuth": pass_start_az,
                                    "end_azimuth": pass_end_az,
                                    "duration": duration,
                                    "visible": True,
                                    "magnitude": magnitude,
                                    "quality": quality
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


# Standard magnitudes at 1000km, 90° phase (from satellite catalogs)
SAT_STD_MAGNITUDES = {
    "ISS": -1.3,
    "ZARYA": -1.3,
    "NAUKA": -1.3,
    "TIANGONG": -0.5,
    "CSS": -0.5,
    "HST": 2.0,
    "HUBBLE": 2.0,
    "STARLINK": 5.5,
    "STARLINK-": 5.5,
    "GPS": 4.0,
    "IRIDIUM": 6.5,
    "IRIDIUM-": 6.5,
    "NOAA": 5.0,
    "METEOSAT": 5.0,
    "GOES": 5.0,
    "DMSP": 5.0,
    "LANDSAT": 5.0,
    "SENTINEL": 5.0,
    "TERRA": 5.0,
    "AQUA": 5.0,
    "SUOMI": 5.0,
    "JPSS": 5.0,
    "COSMOS": 5.5,
    "SOYUZ": 3.0,
    "PROGRESS": 3.0,
    "CREW DRAGON": 2.0,
    "DRAGON": 2.0,
    "CYGNUS": 3.0,
    "FREGAT": 4.0,
    "ROCKET": 4.5,
    "DEB": 6.0,
    "DEBRIS": 6.5,
    "CZ-": 4.0,
    "CZ": 4.0,
}


def get_std_magnitude(name: str) -> float:
    """Get standard magnitude for a satellite by name pattern matching."""
    name_upper = name.upper()
    for pattern, mag in SAT_STD_MAGNITUDES.items():
        if pattern in name_upper:
            return mag
    return 5.5  # default for unknown


def calculate_magnitude(std_mag: float, range_km: float, phase_angle_deg: float) -> float:
    """Calculate apparent magnitude from standard magnitude, range, and phase angle."""
    from math import log10, cos, radians
    # Range correction: 5 * log10(range / 1000)
    range_corr = 5.0 * log10(range_km / 1000.0)
    # Phase correction: -2.5 * log10((1 + cos(phase)) / 2)
    # At 0° phase (fully lit): correction = 0
    # At 90° phase (half lit): correction = 0.75
    # At 180° phase (dark): correction -> large (satellite in shadow)
    if phase_angle_deg >= 170:
        return 99.0  # effectively invisible (in shadow)
    phase_rad = radians(phase_angle_deg)
    phase_corr = -2.5 * log10((1.0 + cos(phase_rad)) / 2.0)
    return std_mag + range_corr + phase_corr


def calculate_phase_angle(sat_pos, sun_pos, obs_pos) -> float:
    """Calculate phase angle (Sun-Satellite-Observer angle) in degrees."""
    from math import sqrt, acos, degrees
    sat_x, sat_y, sat_z = sat_pos
    sun_x, sun_y, sun_z = sun_pos
    obs_x, obs_y, obs_z = obs_pos
    
    # Vector from satellite to sun
    to_sun_x = sun_x - sat_x
    to_sun_y = sun_y - sat_y
    to_sun_z = sun_z - sat_z
    
    # Vector from satellite to observer
    to_obs_x = obs_x - sat_x
    to_obs_y = obs_y - sat_y
    to_obs_z = obs_z - sat_z
    
    # Normalize
    sun_dist = sqrt(to_sun_x**2 + to_sun_y**2 + to_sun_z**2)
    obs_dist = sqrt(to_obs_x**2 + to_obs_y**2 + to_obs_z**2)
    
    if sun_dist == 0 or obs_dist == 0:
        return 0.0
    
    to_sun_x /= sun_dist
    to_sun_y /= sun_dist
    to_sun_z /= sun_dist
    to_obs_x /= obs_dist
    to_obs_y /= obs_dist
    to_obs_z /= obs_dist
    
    # Dot product for angle
    dot = to_sun_x * to_obs_x + to_sun_y * to_obs_y + to_sun_z * to_obs_z
    dot = max(-1.0, min(1.0, dot))
    return degrees(acos(dot))


def calculate_pass_quality(elevation: float, duration: float, sun_el: float, magnitude: float, rarity: float = 1.0) -> int:
    """Calculate pass quality score 0-100."""
    # Normalize each component to 0-1
    elev_score = min(1.0, max(0.0, (elevation - 10) / 80))  # 10°->0, 90°->1
    dur_score = min(1.0, max(0.0, (duration - 1) / 9))       # 1min->0, 10min->1
    dark_score = min(1.0, max(0.0, (-sun_el - 6) / 12))      # sun -6°->0, -18°->1
    mag_score = min(1.0, max(0.0, (6.5 - magnitude) / 10))   # mag +6.5->0, -3.5->1
    
    # Weighted combination
    score = (
        0.30 * elev_score +
        0.20 * dur_score +
        0.25 * dark_score +
        0.15 * mag_score +
        0.10 * rarity
    ) * 100
    
    return int(round(score))


def get_rarity_bonus(name: str) -> float:
    """Get rarity bonus 0-1 based on satellite type."""
    name_upper = name.upper()
    if any(k in name_upper for k in ["ISS", "ZARYA", "NAUKA", "TIANGONG", "CSS", "HST", "HUBBLE"]):
        return 1.0
    if any(k in name_upper for k in ["STARLINK", "IRIDIUM", "GPS", "NOAA", "METEOSAT", "GOES", "DMSP", "LANDSAT", "SENTINEL", "TERRA", "AQUA", "SUOMI", "JPSS"]):
        return 0.3
    if any(k in name_upper for k in ["DEB", "DEBRIS", "ROCKET", "CZ-"]):
        return 0.1
    return 0.5


def show_satellite_passes():
    """Show satellite passes menu and predictions."""
    from rich.prompt import Prompt
    
    # Get or set observer location
    lat = config.get("observer_lat")
    lon = config.get("observer_lon")
    alt = config.get("observer_alt", 0)
    
    if lat is None or lon is None:
        clear_screen()
        console.print("[title]Satellite Passes - Set Your Location[/title]\n")
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
            console.print(f"\n[success]Location saved: {lat:.4f}, {lon:.4f}, {alt}m[/success]")
            time.sleep(1)
        except Exception:
            console.print("[error]Invalid coordinates[/error]")
            time.sleep(1)
            return
    
    while True:
        clear_screen()
        console.print(f"[title]Satellite Passes[/title] (Location: {lat:.4f}, {lon:.4f})\n")
        console.print("  [number]1[/number] Predict passes (3 days)")
        console.print("  [number]2[/number] Tonight's best passes (24h)")
        console.print("  [number]3[/number] Specific satellite")
        console.print("  [number]4[/number] Change location")
        console.print("\n[warning]Actions:[/warning]  [info]Enter[/info] - Back to main menu")
        choice = input("> ").strip()
        
        if not choice:
            return
        elif choice == "4":
            config.set("observer_lat", None)
            config.set("observer_lon", None)
            console.print("[yellow]Location reset[/yellow]")
            time.sleep(1)
            continue
        elif choice == "1":
            predict_passes(lat, lon, alt, days=3)
        elif choice == "2":
            predict_passes(lat, lon, alt, days=1)
        elif choice == "3":
            predict_specific_satellite(lat, lon, alt)


def predict_passes(lat: float, lon: float, alt: float, days: int = 3):
    """Predict passes for all tracked satellites."""
    from rich.prompt import Prompt
    
    while True:
        clear_screen()
        console.print("[title]Satellite Pass Predictions[/title]\n")
        console.print("  [number]1[/number] All satellites (stations + Starlink) - {} days".format(days))
        console.print("  [number]2[/number] Tonight only (24 hours)")
        console.print("  [number]3[/number] Stations only (ISS, Tiangong, Hubble, etc.)")
        console.print("  [number]4[/number] Starlink only (first 200)")
        console.print("  [number]5[/number] Change days (currently {})".format(days))
        console.print("\n[warning]Actions:[/warning]  [info]Enter[/info] - Back")
        choice = input("> ").strip()
        
        if not choice:
            return
        elif choice == "5":
            try:
                days = int(Prompt.ask("Days to predict (1-7)", default=str(days)))
                days = max(1, min(7, days))
            except ValueError:
                pass
            continue
        elif choice not in ("1", "2", "3", "4"):
            continue
        
        clear_screen()
        
        if choice == "1":
            groups = ["stations", "starlink"]
            limit = None
            title = "All Satellites ({} days)".format(days)
        elif choice == "2":
            groups = ["stations", "starlink"]
            limit = None
            title = "Tonight Only (24 hours)"
            days = 1
        elif choice == "3":
            groups = ["stations"]
            limit = None
            title = "Stations Only ({} days)".format(days)
        elif choice == "4":
            groups = ["starlink"]
            limit = 200
            title = "Starlink Quick Mode (first 200, {} days)".format(days)
        
        if len(groups) > 1:
            urls = [(CELESTRAK_TLE_URLS[g], g) for g in groups]
            results = multi_fetch_with_progress(urls, "Fetching TLE data...")
            all_satellites = []
            for label, res in results:
                if res and res.status_code == 200:
                    lines = res.text.strip().split("\n")
                    sats = []
                    for i in range(0, len(lines), 3):
                        if i + 2 < len(lines):
                            name = lines[i].strip()
                            line1 = lines[i + 1].strip()
                            line2 = lines[i + 2].strip()
                            if line1.startswith("1 ") and line2.startswith("2 "):
                                sats.append({"name": name, "line1": line1, "line2": line2})
                    if limit and len(sats) > limit:
                        sats = sats[:limit]
                    all_satellites.extend(sats)
        else:
            all_satellites = []
            for group in groups:
                sats = fetch_tle_data(group, show_progress=True)
                if limit and len(sats) > limit:
                    sats = sats[:limit]
                all_satellites.extend(sats)
        
        if not all_satellites:
            console.print("[error]Error: Could not fetch satellite data[/error]")
            input("\nPress Enter to return...")
            return
        
        console.print(f"[success]Loaded {len(all_satellites)} satellites[/success]\n")
        console.print("[muted]Calculating passes...[/muted]")
        
        passes = calculate_visible_passes(all_satellites, lat, lon, alt, days)
        
        if choice == "2":
            now = datetime.now(timezone.utc)
            cutoff = now + timedelta(hours=24)
            passes = [p for p in passes if p["start"] < cutoff]
        
        if not passes:
            console.print("[yellow]No visible passes found[/yellow]")
            input("\nPress Enter to return...")
            continue
        
        # Group by satellite
        from collections import defaultdict
        passes_by_sat = defaultdict(list)
        for p in passes:
            passes_by_sat[p["name"]].append(p)
        
        # Sort by first pass time
        sorted_sats = sorted(passes_by_sat.items(), key=lambda x: x[1][0]["start"])
        
        clear_screen()
        console.print(f"[title]{title}[/title]")
        console.print(f"Location: {lat:.4f}, {lon:.4f}, {alt}m\n")
        
        total_passes = sum(len(v) for v in passes_by_sat.values())
        console.print(f"[muted]{len(passes_by_sat)} satellites, {total_passes} total passes[/muted]\n")
        
        for name, sat_passes in sorted_sats:
            if not sat_passes:
                continue
            console.print(f"\n[highlight]{name}[/highlight]")
            for p in sat_passes[:5]:
                start_str = p["start"].strftime("%m-%d %H:%M UTC")
                end_str = p["end"].strftime("%H:%M")
                max_el = p["max_elevation"]
                dir_str = f"{p['start_azimuth']:.0f}°→{p['end_azimuth']:.0f}°"
                dur = int(p["duration"])
                mag = p.get("magnitude", 99)
                quality = p.get("quality", 0)
                mag_str = f"  mag {mag:.1f}" if mag < 99 else ""
                qual_str = f"  Q{quality}" if quality > 0 else ""
                visible = "✓" if p["visible"] else "✗"
                color = "success" if p["visible"] else "muted"
                console.print(f"  [{color}]{start_str}-{end_str}  max {max_el:.0f}°  {dir_str}  {dur}min{mag_str}{qual_str}  {visible}[/{color}]")
        
        console.print("\n[warning]Actions:[/warning]  [info]r[/info] - Recalculate  [info]Enter[/info] - Back")
        action = input("> ").strip().lower()
        if not action or action != "r":
            return
        # If 'r', loop continues and recalculates


def predict_specific_satellite(lat: float, lon: float, alt: float):
    """Predict passes for a specific satellite."""
    from rich.prompt import Prompt
    
    while True:
        clear_screen()
        console.print("[title]Specific Satellite Prediction[/title]\n")
        
        # Select satellite group
        console.print("Select satellite group:")
        groups = list(CELESTRAK_TLE_URLS.keys())
        for i, g in enumerate(groups, 1):
            console.print(f"  [number]{i}[/number] {g.capitalize()}")
        console.print("\n[warning]Actions:[/warning]  [info]Enter[/info] - Back")
        choice = input("> ").strip()
        
        if not choice:
            return
        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(groups):
                continue
        except ValueError:
            continue
        
        group = groups[idx]
        
        # Fetch TLE data for selected group
        clear_screen()
        console.print(f"[info]Fetching {group} TLE data...[/info]\n")
        satellites = fetch_tle_data(group)
        
        if not satellites:
            console.print("[error]Error: Could not fetch satellite data[/error]")
            input("\nPress Enter to return...")
            continue
        
        console.print(f"[success]Loaded {len(satellites)} satellites from {group}[/success]\n")
        
        # Search/filter
        search = Prompt.ask("Search satellite name (or press Enter to list all)", default="").strip().lower()
        
        filtered = [s for s in satellites if search in s["name"].lower()] if search else satellites
        
        if not filtered:
            console.print("[warning]No matches found[/warning]")
            time.sleep(1)
            continue
        
        # Show list with numbers
        page_size = 20
        total_pages = (len(filtered) + page_size - 1) // page_size
        page = 0
        
        while True:
            clear_screen()
            console.print(f"[title]{group.capitalize()} Satellites[/title] (Page {page+1}/{total_pages})\n")
            
            start = page * page_size
            end = min(start + page_size, len(filtered))
            
            for i in range(start, end):
                sat = filtered[i]
                console.print(f"  [number]{i+1}[/number] {sat['name']}")
            
            console.print("\n[warning]Actions:[/warning]  [info]n[/info] Next  [info]p[/info] Prev  [info]s[/info] Search  [info]Enter[/info] Back")
            action = input("> ").strip().lower()
            
            if not action:
                break  # Back to group selection
            elif action == "s":
                break  # Will re-prompt search
            elif action == "n" and page < total_pages - 1:
                page += 1
                continue
            elif action == "p" and page > 0:
                page -= 1
                continue
            else:
                # Selected a satellite
                try:
                    idx = int(action) - 1
                    if start <= idx < end:
                        selected = filtered[idx]
                        show_satellite_detail(selected, lat, lon, alt)
                except ValueError:
                    pass
        
        if action == "s":
            continue  # Re-search
        # If action is empty or "b", loop continues to group selection


def show_satellite_detail(sat: dict, lat: float, lon: float, alt: float):
    """Show detailed passes for a specific satellite."""
    clear_screen()
    console.print(f"[info]Calculating passes for {sat['name']}...[/info]\n")
    
    passes = calculate_visible_passes([sat], lat, lon, alt, days=7)
    
    clear_screen()
    console.print(f"[title]{sat['name']}[/title] - Next 7 Days\n")
    console.print(f"Location: {lat:.4f}, {lon:.4f}\n")
    
    if not passes:
        console.print("[warning]No visible passes in the next 7 days[/warning]")
    else:
        for p in passes[:10]:
            start_str = p["start"].strftime("%m-%d %H:%M UTC")
            end_str = p["end"].strftime("%H:%M")
            max_el = p["max_elevation"]
            dir_str = f"{p['start_azimuth']:.0f}°→{p['end_azimuth']:.0f}°"
            dur = int(p["duration"])
            mag = p.get("magnitude", 99)
            quality = p.get("quality", 0)
            mag_str = f"  mag {mag:.1f}" if mag < 99 else ""
            qual_str = f"  Q{quality}" if quality > 0 else ""
            visible = "✓" if p["visible"] else "✗"
            color = "success" if p["visible"] else "muted"
            console.print(f"  [{color}]{start_str}-{end_str}  max {max_el:.0f}°  {dir_str}  {dur}min{mag_str}{qual_str}  {visible}[/{color}]")
    
    console.print("\n[warning]Actions:[/warning]  [info]Enter[/info] - Back")
    input("> ")


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
    table = Table(title="Upcoming Launches", show_header=True, header_style="title", expand=True, border_style="border")
    table.add_column("#", style="number", justify="right", width=4, no_wrap=True)
    table.add_column("Mission", style="name", min_width=40, overflow="fold")
    table.add_column("Rocket / Provider", style="rocket", min_width=25, overflow="fold")
    table.add_column("Date (UTC)", style="date", width=18, no_wrap=True)
    table.add_column("Status", style="status", width=12, no_wrap=True)

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
            status_style = "success"
        elif status_id == 2:
            status_style = "warning"
        elif status_id == 3:
            status_style = "error"
        else:
            status_style = "muted"

        text = Text()
        text.append(f"{idx}. ", style="number")
        text.append(f"{mission}\n", style="name")
        text.append(f"    {rocket} / {provider}\n", style="rocket")
        text.append(f"    {window_start}  ", style="date")
        if countdown:
            countdown_text = Text.from_markup(countdown)
            text.append(" ")
            text.append_text(countdown_text)
            text.append("  ")
        text.append(f"[{status}]", style=status_style)

        panels.append(Panel(text, border_style="border", padding=(0, 1)))

    return panels


def create_launch_detail_table(launch: dict) -> Table:
    """Create detailed table for a single launch."""
    table = Table(title=f"Launch Details: {launch.get('name', 'Unknown')}", show_header=True, expand=True, border_style="border")
    table.add_column("Property", style="number", width=22, no_wrap=True)
    table.add_column("Value", style="text")

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
    console.print("[info]Fetching upcoming launches...[/info]\n")

    launches = fetch_launches()
    if not launches:
        console.print("[error]Error: Could not fetch launches data[/error]")
        input("\nPress Enter to return to menu...")
        return

    while True:
        clear_screen()
        panels = create_launches_panel_list(launches)
        for panel in panels:
            console.print(panel)
        console.print("\n[warning]Actions:[/warning]  [info]1-{n}[/info] - Details  [info]r[/info] - Refresh  [info]Enter[/info] - Back".format(n=len(launches)))
        choice = input("> ").strip().lower()

        if not choice:
            return
        if choice == "r":
            global _launches_cache
            _launches_cache = None
            console.print("[muted]Refreshing...[/muted]")
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

        console.print("\n[warning]Actions:[/warning]  [info]w[/info] - Open webcast  [info]Enter[/info] - Back")
        choice = input("> ").strip().lower()

        if choice == "w" and launch.get("webcast_live") and launch.get("streams"):
            url = launch["streams"][0].get("url", "")
            if url:
                webbrowser.open(url)
                console.print("[success]Opened webcast in browser[/success]")
                time.sleep(1)
        else:
            return


def show_dashboard():
    """Show stunning btop-like dashboard with all space data."""
    from rich.layout import Layout
    from rich.live import Live
    from rich.align import Align
    from datetime import datetime, timezone
    
    # Get observer location
    lat = config.get("observer_lat")
    lon = config.get("observer_lon")
    alt = config.get("observer_alt", 0)
    
    if lat is None or lon is None:
        clear_screen()
        console.print("[warning]Set your location first in Satellite Passes → Change location[/warning]")
        input("\nPress Enter to return...")
        return
    
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="footer", size=3),
    )
    layout["main"].split_row(
        Layout(name="left", ratio=2),
        Layout(name="right", ratio=1),
    )
    layout["left"].split_column(
        Layout(name="iss", ratio=1),
        Layout(name="tiangong", ratio=1),
        Layout(name="passes", ratio=2),
    )
    layout["right"].split_column(
        Layout(name="weather", ratio=1),
        Layout(name="people", ratio=1),
        Layout(name="launches", ratio=1),
        Layout(name="apod", ratio=1),
    )
    
    def build_dashboard():
        now = datetime.now(timezone.utc)
        
        # Header
        header_text = Text()
        header_text.append(" ╭─────────────────────────────────────────────────────────────────╮ ", style="border")
        header_text.append("\n")
        header_text.append(" │  ", style="border")
        header_text.append("SPACECREW DASHBOARD", style="highlight")
        header_text.append("  │  ", style="border")
        header_text.append(f" {now.strftime('%Y-%m-%d %H:%M:%S UTC')}  ", style="muted")
        header_text.append(" │ ", style="border")
        header_text.append("\n")
        header_text.append(" ╰─────────────────────────────────────────────────────────────────╯ ", style="border")
        layout["header"].update(Align.center(header_text))
        
        # ISS Panel
        iss_data = fetch_iss_position()
        if iss_data and iss_data.get("iss_position"):
            pos = iss_data["iss_position"]
            iss_text = Text()
            iss_text.append(" ISS (ZARYA)\n", style="title")
            iss_text.append(f"   Lat: {pos.get('latitude', 'N/A')}\n", style="text")
            iss_text.append(f"   Lon: {pos.get('longitude', 'N/A')}\n", style="text")
            iss_text.append(f"   Alt: {iss_data.get('altitude', 'N/A')} km\n", style="text")
            iss_text.append(f"   Vel: {iss_data.get('velocity', 'N/A')} km/h\n", style="text")
            iss_text.append(f"   Vis: {iss_data.get('visibility', 'N/A')}\n", style="text")
            iss_text.append(f"   Updated: {now.strftime('%H:%M:%S UTC')}", style="muted")
            layout["iss"].update(Panel(iss_text, title="[info]ISS[/info]", border_style="border", padding=(0, 1)))
        else:
            layout["iss"].update(Panel("[error]ISS data unavailable[/error]", title="[info]ISS[/info]", border_style="border"))
        
        # Tiangong Panel
        tg_data = fetch_iss_position()  # Using same API for now
        if tg_data and tg_data.get("iss_position"):
            pos = tg_data["iss_position"]
            tg_text = Text()
            tg_text.append(" TIANGONG\n", style="title")
            tg_text.append(f"   Lat: {pos.get('latitude', 'N/A')}\n", style="text")
            tg_text.append(f"   Lon: {pos.get('longitude', 'N/A')}\n", style="text")
            tg_text.append(f"   Alt: {tg_data.get('altitude', 'N/A')} km\n", style="text")
            tg_text.append(f"   Vel: {tg_data.get('velocity', 'N/A')} km/h\n", style="text")
            tg_text.append(f"   Updated: {now.strftime('%H:%M:%S UTC')}", style="muted")
            layout["tiangong"].update(Panel(tg_text, title="[info]Tiangong[/info]", border_style="border", padding=(0, 1)))
        else:
            layout["tiangong"].update(Panel("[error]Tiangong data unavailable[/error]", title="[info]Tiangong[/info]", border_style="border"))
        
        # Next passes (top 5)
        passes_text = Text()
        passes_text.append(" NEXT PASSES (24h)\n", style="title")
        try:
            stations = fetch_tle_data("stations")
            iss_sats = [s for s in stations if "ISS" in s["name"] or "ZARYA" in s["name"] or "NAUKA" in s["name"]]
            tg_sats = [s for s in stations if "TIANGONG" in s["name"] or "CSS" in s["name"]]
            key_sats = iss_sats + tg_sats
            if key_sats:
                passes = calculate_visible_passes(key_sats, lat, lon, alt, days=1)
                now_utc = datetime.now(timezone.utc)
                cutoff = now_utc + timedelta(hours=24)
                passes = [p for p in passes if p["start"] < cutoff]
                passes.sort(key=lambda x: x["start"])
                for p in passes[:5]:
                    start_str = p["start"].strftime("%m-%d %H:%M UTC")
                    mag = p.get("magnitude", 99)
                    q = p.get("quality", 0)
                    mag_str = f" mag {mag:.1f}" if mag < 99 else ""
                    passes_text.append(f"   {p['name'][:20]:20s} {start_str}  max {p['max_elevation']:.0f}°{mag_str}  Q{q}\n", style="text")
            else:
                passes_text.append("   No satellite data\n", style="muted")
        except Exception:
            passes_text.append("   Error calculating passes\n", style="error")
        layout["passes"].update(Panel(passes_text, title="[info]Passes[/info]", border_style="border", padding=(0, 1)))
        
        # Space Weather
        weather_data = fetch_space_weather()
        weather_text = Text()
        weather_text.append(" SPACE WEATHER\n", style="title")
        if weather_data:
            flares = weather_data.get("flares", [])
            if flares:
                for f in flares[:2]:
                    cls = f.get("classType", "N/A")
                    peak = f.get("peakTime", "").replace("T", " ").replace("Z", " UTC")
                    weather_text.append(f"   {cls}  {peak}\n", style="text")
            kp = weather_data.get("kp_index", [])
            if kp:
                current_kp = kp[-1].get("kp_index", 0) if kp else 0
                max_kp = max((d.get("kp_index", 0) for d in kp), default=0)
                weather_text.append(f"   Kp: {current_kp:.1f}  (max {max_kp:.1f})\n", style="text")
            weather_text.append(f"   Storm: {weather_data.get('storm_level', 'Quiet')}", style="text")
        else:
            weather_text.append("   No data", style="muted")
        layout["weather"].update(Panel(weather_text, title="[info]Weather[/info]", border_style="border", padding=(0, 1)))
        
        # People in Space
        people_data = fetch_space_data()
        people_text = Text()
        people_text.append(" PEOPLE IN SPACE\n", style="title")
        if people_data:
            iss_groups, tg_groups = group_people_by_station(people_data)
            people_text.append(f"   ISS: {sum(len(g) for g in iss_groups.values())}  ", style="text")
            people_text.append(f"Tiangong: {sum(len(g) for g in tg_groups.values())}\n", style="text")
            total = len(people_data)
            people_text.append(f"   Total: {total}", style="highlight")
        else:
            people_text.append("   No data", style="muted")
        layout["people"].update(Panel(people_text, title="[info]People[/info]", border_style="border", padding=(0, 1)))
        
        # Upcoming Launches
        launches_data = fetch_launches()
        launches_text = Text()
        launches_text.append(" NEXT LAUNCHES\n", style="title")
        if launches_data:
            for i, launch in enumerate(launches_data[:3]):
                name = launch.get("name", "Unknown")[:25]
                window = format_launch_datetime(launch.get("window_start", ""))
                status = launch.get("status", {}).get("name", "Unknown")
                countdown = get_launch_countdown(launch.get("window_start", ""))
                launches_text.append(f"   {name}\n", style="text")
                launches_text.append(f"   {window}  {countdown}\n", style="muted")
                launches_text.append(f"   {status}\n\n", style="text")
        else:
            launches_text.append("   No data", style="muted")
        layout["launches"].update(Panel(launches_text, title="[info]Launches[/info]", border_style="border", padding=(0, 1)))
        
        # APOD
        apod_data = fetch_apod_date(None)
        apod_text = Text()
        apod_text.append(" APOD TODAY\n", style="title")
        if apod_data:
            title = apod_data.get("title", "Unknown")[:40]
            date = apod_data.get("date", "Unknown")
            apod_text.append(f"   {title}\n", style="text")
            apod_text.append(f"   {date}", style="muted")
        else:
            apod_text.append("   No data", style="muted")
        layout["apod"].update(Panel(apod_text, title="[info]APOD[/info]", border_style="border", padding=(0, 1)))
        
        # Footer
        footer_text = Text()
        footer_text.append("  [info]r[/info] Refresh  [info]q[/info] Quit  [info]Enter[/info] Back  •  Auto-refresh: 2 min  •  ", style="info")
        footer_text.append(f"Location: {lat:.2f}, {lon:.2f}", style="muted")
        layout["footer"].update(Align.center(footer_text))
        
        return layout
    
    # Initial build
    layout = build_dashboard()
    
    # Live display with 2-minute auto-refresh
    with Live(layout, console=console, refresh_per_second=1/120, screen=True) as live:
        last_refresh = time.time()
        while True:
            try:
                if time.time() - last_refresh > 120:  # 2 minutes
                    layout = build_dashboard()
                    live.update(layout)
                    last_refresh = time.time()
                time.sleep(1)
            except KeyboardInterrupt:
                break
    
    clear_screen()


def show_main_menu():
    """Show main menu with 8 options."""
    from rich.align import Align
    from rich.panel import Panel
    from rich.text import Text
    
    current_theme = config.get("theme", "catppuccin-mocha")
    menu_text = Text()
    menu_text.append("         SPACECREW", style="highlight")
    menu_text.append("\n\n")
    menu_text.append("  1 ", style="number")
    menu_text.append("People in Space", style="info")
    menu_text.append("\n")
    menu_text.append("  2 ", style="number")
    menu_text.append("NASA APOD", style="info")
    menu_text.append("\n")
    menu_text.append("  3 ", style="number")
    menu_text.append("Upcoming Launches", style="info")
    menu_text.append("\n")
    menu_text.append("  4 ", style="number")
    menu_text.append("ISS Position", style="info")
    menu_text.append("\n")
    menu_text.append("  5 ", style="number")
    menu_text.append("Space Weather", style="info")
    menu_text.append("\n")
    menu_text.append("  6 ", style="number")
    menu_text.append("Satellite Passes", style="info")
    menu_text.append("\n")
    menu_text.append("  7 ", style="number")
    menu_text.append(f"Theme ({current_theme})", style="info")
    menu_text.append("\n")
    menu_text.append("  8 ", style="number")
    menu_text.append("Dashboard", style="info")
    menu_text.append("\n")
    menu_text.append("  9 ", style="number")
    menu_text.append("Exit", style="info")
    
    panel = Panel(
        Align.center(menu_text),
        border_style="border",
        title_align="center",
    )
    console.print(panel)


def show_theme_menu():
    """Show theme selection menu."""
    from rich.prompt import Prompt
    
    themes = list(THEMES.keys())
    current = config.get("theme", "catppuccin-mocha")
    if current not in themes:
        current = "catppuccin-mocha"
    
    while True:
        clear_screen()
        console.print("[title]Select Theme[/title]\n")
        for i, t in enumerate(themes, 1):
            marker = " ← current" if t == current else ""
            console.print(f"  [number]{i}[/number] {t.replace('-', ' ').title()}{marker}")
        console.print(f"  [number]{len(themes)+1}[/number] Back\n")
        
        default_idx = themes.index(current) + 1
        choice = Prompt.ask("Select theme", choices=[str(i) for i in range(1, len(themes)+2)], default=str(default_idx))
        
        if int(choice) == len(themes) + 1:
            return
        
        new_theme = themes[int(choice) - 1]
        config.set("theme", new_theme)
        console.print(f"[success]Theme changed to {new_theme}[/success]")
        time.sleep(0.5)
        return


def handle_people_in_space():
    """Handle the people in space workflow."""
    clear_screen()
    people = fetch_space_data()

    if people is None:
        console.print("[error]Error: No internet connection. Please check your network and try again.[/error]")
        input("\nPress Enter to return to menu...")
        return

    iss_groups, tiangong_groups = group_people_by_station(people)
    tree, missions = build_tree_menu(len(people), iss_groups, tiangong_groups)

    console.print(tree)
    console.print("\n[warning]Commands:[/warning] [info]menu[/info] - Back  [info]quit[/info] - Exit")
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
        choices=["dashboard", "people", "apod", "launches", "iss", "weather", "passes"],
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
        if args.mode == "dashboard":
            show_dashboard()
        elif args.mode == "people":
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
        choice = console.input("[bold cyan]Select option [1-9]: [/bold cyan]").strip().lower()
        
        if choice in ("9", "quit", "exit", "q"):
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
        elif choice == "7":
            show_theme_menu()
        elif choice == "8":
            show_dashboard()
        else:
            console.print("[error]Invalid option[/error]")
            time.sleep(1)


if __name__ == "__main__":
    main()