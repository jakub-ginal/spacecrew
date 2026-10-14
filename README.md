# spacecrew
See who is in space right now, catch the ISS over your house, and track launches - all from your terminal.

<img width="800" height="600" alt="753_1x_shots_so" src="https://github.com/user-attachments/assets/64100112-107a-423d-afda-15fcd280c939" />


## Install

From PyPI:

```bash
pip install spacecrew
```

Or install from source with [pipx](https://pipx.pypa.io/):

```bash
git clone https://github.com/jakub-ginal/spacecrew
cd spacecrew
pipx install .
```

Requires Python 3.10+

> **Recommended:** CachyOS, Ubuntu, Debian. Should work on most Linux distros, macOS, and Windows (terminal photos unavailable on Windows).

## Usage

### Quickstart

Simply type `spacecrew` anywhere in your terminal. Follow the interactive menu:

Menu: 1 People · 2 APOD · 3 Launches · 4 ISS · 5 Weather · 6 Passes · 7 Theme · 8 Dashboard · 9 Quit

### Commands
```bash
spacecrew                  # interactive menu
spacecrew --mode passes    # jump straight to satellite passes
spacecrew --mode apod --offline   # cached APOD, no network
spacecrew --mode iss --no-image   # skip photo rendering
```

## Features

<details>
<summary><b>People in Space</b> - who is up there right now</summary>


Live crew split by ISS / Tiangong, per-mission trees, astronaut profiles with photo, agency, and time in space (previous + current mission tracked live).

<img width="800" height="600" alt="92_1x_shots_so" src="https://github.com/user-attachments/assets/dfd95ad7-904d-4495-9c98-b8e1751ea5f3" />

### Time in Space

* **p (previous)**: Days from past missions.
* **c (current)**: Days from the current mission (tracked live).
<img width="800" height="600" alt="356_1x_shots_so" src="https://github.com/user-attachments/assets/a87a2e9d-3c5a-443c-b62f-ec19f2922f0d" />

### Commands

```bash
spacecrew --mode people
spacecrew --mode people --json
```
</details>

<details>
<summary><b>NASA APOD</b> - astronomy picture of the day in your terminal</summary>

Image rendered right in the terminal, full explanation, `o` opens HD in browser, `p` goes a day back. Needs a NASA key for heavy use - otherwise DEMO_KEY limits apply.

<img width="800" height="600" alt="82_1x_shots_so" src="https://github.com/user-attachments/assets/c6f4088c-59cd-450e-b31e-1faa59e5db66" />


### Commands

```bash
spacecrew --mode apod
export NASA_API_KEY="your-key-here"
```
</details>

<details>
<summary><b>Launches</b> - upcoming liftoffs with rocket photos</summary>

Compact cards with countdowns (`T-2d 04h 12m`), detail view per mission, `p` opens a big rocket photo, `w` opens the webcast.

<img width="800" height="600" alt="36_1x_shots_so" src="https://github.com/user-attachments/assets/5222e849-5c39-4c79-b674-6d258808f94b" />

### Detailed view

<img width="800" height="600" alt="722_1x_shots_so" src="https://github.com/user-attachments/assets/471f7ceb-5e76-4251-870f-0ec9c972b387" />

### Rocket photo

<img width="800" height="600" alt="894_1x_shots_so" src="https://github.com/user-attachments/assets/a42adcab-8800-45a2-8785-f04a48fed201" />


### Commands
```bash
spacecrew --mode launches
spacecrew --mode launches --json
```
</details>

<details>
<summary><b>ISS Position</b> - live tracker</summary>

Real-time latitude/longitude, altitude, velocity, over-what-country, plus a Google Maps link.

<img width="800" height="600" alt="364_1x_shots_so" src="https://github.com/user-attachments/assets/b23a14fe-49d2-47c4-80e2-81f8e5ada852" />

### Commands

```bash
spacecrew --mode iss
```
</details>

<details>
<summary><b>Space Weather</b> - flares, CMEs, Kp, aurora verdict</summary>

Recent solar flares and Earth-directed CMEs, live Kp index with storm level, and an aurora verdict for your latitude (set your location in Passes first).

<img width="800" height="600" alt="830_1x_shots_so" src="https://github.com/user-attachments/assets/175989b1-523a-4826-b89e-44c008f858ef" />


### Commands

```bash
spacecrew --mode weather
```
</details>

<details>
<summary><b>Satellite Passes</b> - predictions for your sky</summary>

Set your location once, then get Tonight's Best (smart quality filter), All Passes, Specific Satellite search, or just Favorites. Every pass shows brightness, quality score, cloud cover, and moon state.

<img width="800" height="600" alt="592_1x_shots_so" src="https://github.com/user-attachments/assets/0ad21629-a819-4c7d-844f-8bd7d3ab0641" />

### Detailed view

<img width="800" height="600" alt="837_1x_shots_so" src="https://github.com/user-attachments/assets/cadb4e5b-ff06-4e13-b7db-0cd731541da4" />

### Commands

```bash
spacecrew --mode passes
spacecrew --mode passes --json
```
</details>

<details>
<summary><b>Dashboard</b> - everything live on one screen</summary>

ISS, next passes, weather, people, launches, APOD - refreshing every 60s. Enter goes back.

<img width="800" height="600" alt="795_1x_shots_so" src="https://github.com/user-attachments/assets/3f97efe4-595e-47dc-84c7-1db096d88669" />

### Commands

```bash
spacecrew --mode dashboard
```
</details>

<details>
<summary><b>Timezones</b> - your time, not just UTC</summary>

Times display in your local zone with UTC kept in detail views. Auto-detected on first run, overridable any time.

### Commands

```bash
spacecrew --timezone Europe/Warsaw
```
</details>

<details>
<summary><b>JSON mode</b> - script it</summary>

Machine-readable output for people, launches, and passes. Status messages stay off stdout so pipes never break.

### Commands

```bash
spacecrew --json --mode people | jq length
spacecrew --no-cache --json --mode passes | jq '.[0]'
```
</details>

<details>
<summary><b>Config & safe testing</b></summary>

Settings live in `~/.config/spacecrew/config.toml`, cache in `cache.db` next to it. Test without touching real data using an isolated dir.

```bash
spacecrew --offline      # cached data only
spacecrew --no-cache     # skip cache for this run
spacecrew --clear-cache  # drop expired entries
spacecrew --config /tmp/spacecrew-test   # isolated playground
```
</details>

<details>
<summary><b>Themes, completions, man page</b></summary>

10 themes from menu option 7, shell completions, and a real man page.

<img width="800" height="600" alt="848_1x_shots_so" src="https://github.com/user-attachments/assets/0dcc94df-23d2-4941-9726-0edb1212fabd" />

### Man page

<img width="800" height="600" alt="414_1x_shots_so" src="https://github.com/user-attachments/assets/8d04c587-fda5-41d8-a2d6-be1c513ee756" />

### Commands

```bash
spacecrew --generate-completion bash   # bash|zsh|fish
man spacecrew
```
</details>

## Uninstall

```bash
pip uninstall spacecrew
```

## Data sources

People data by [corquaid](https://github.com/corquaid/international-space-station-APIs) · launches by [The Space Devs](https://thespacedevs.com) · orbits by [CelesTrak](https://celestrak.org) · satellite metadata by [SatNOGS](https://db.satnogs.org) · imagery by [NASA APOD](https://apod.nasa.gov) · weather by [NOAA SWPC](https://www.swpc.noaa.gov) · clouds by [Open-Meteo](https://open-meteo.com)
