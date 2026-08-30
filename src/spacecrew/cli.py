import os
import re
import time
from collections import defaultdict
from datetime import datetime
from io import BytesIO

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


def clear_screen():
    os.system("clear")


def to_thumb_url(original_url: str, width: int) -> str:
    m = re.match(r"(.*/commons)/(\w/\w\w)/([^/]+)$", original_url)
    if not m:
        raise ValueError(f"unexpected commons URL format {original_url}")
    base, hashpath, filename = m.groups()
    return f"{base}/thumb/{hashpath}/{filename}/{width}px-{filename}"


def fetch_with_retry(url, headers=None, timeout=5, max_retries=3, backoff_factor=1):
    """Fetch URL with retry on 429 (rate limit) responses."""
    if headers is None:
        headers = {"User-Agent": "Mozilla/5.0"}
    
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
    url = "https://corquaid.github.io/international-space-station-APIs/JSON/people-in-space.json"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = fetch_with_retry(url, headers=headers, timeout=5)
        if res and res.status_code == 200:
            return res.json()["people"]
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
        res = fetch_with_retry(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
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


def main():
    while True:
        clear_screen()
        people = fetch_space_data()

        if people is None:
            console.print("[bold red]Error: No internet connection. Please check your network and try again.[/bold red]")
            input("\nPress Enter to retry...")
            continue

        iss_groups, tiangong_groups = group_people_by_station(people)
        tree, missions = build_tree_menu(len(people), iss_groups, tiangong_groups)

        console.print(tree)
        choice = input("\n> ").strip().lower()

        if choice == "quit":
            break
        elif choice == "menu":
            continue

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(missions):
                craft, members = missions[idx]
                result = handle_mission_view(craft, members)
                if result == "quit":
                    break


if __name__ == "__main__":
    main()
