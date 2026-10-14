# spacecrew
Spacecrew is a lightweight Python terminal program that shows who is in space right now.

<img width="800" height="600" alt="92_1x_shots_so" src="https://github.com/user-attachments/assets/dfd95ad7-904d-4495-9c98-b8e1751ea5f3" />


## Tested Systems

* **CachyOS**
* **Ubuntu**
* **Debian**

## Installation

Install from PyPI:

```bash
pip install spacecrew
```

Or install from source with [pipx](https://pipx.pypa.io/):

```bash
git clone https://github.com/jakub-ginal/spacecrew
cd spacecrew
pipx install .
```
## Usage

Simply type `spacecrew` anywhere in your terminal.
Follow the interactive menu:

1. People in Space
2. NASA APOD
3. Upcoming Launches
4. ISS Position
5. Space Weather
6. Satellite Passes
7. Theme
8. Dashboard

Start directly in a mode:

```bash
spacecrew --mode passes
spacecrew --mode apod --offline
spacecrew --mode iss --no-image
spacecrew --mode people --json
spacecrew --mode launches --json
spacecrew --mode passes --json
```

### Time in Space

* **p (previous)**: Days from past missions.
* **c (current)**: Days from the current mission (tracked live).
<img width="800" height="600" alt="356_1x_shots_so" src="https://github.com/user-attachments/assets/a87a2e9d-3c5a-443c-b62f-ec19f2922f0d" />


## Uninstall

To completely remove the program, run:
```bash
pip uninstall spacecrew
```

## Configuration

`~/.config/spacecrew/config.toml` stores your NASA API key, theme,
observer location, and favorites. Cache lives in `~/.config/spacecrew/cache.db`.

```bash
export NASA_API_KEY="your-key-here"  # optional, DEMO_KEY is used otherwise
spacecrew --offline      # cached data only, no network
spacecrew --no-cache     # disable persistent cache for this run
spacecrew --clear-cache  # clear expired cache entries
spacecrew --no-image     # skip photo rendering
spacecrew --json --mode people  # JSON output (passes|people|launches)
spacecrew --config /tmp/spacecrew-test  # isolated config/cache dir for testing
SPACE_CREW_CONFIG_DIR=/tmp/spacecrew-test spacecrew  # same via env
spacecrew --timezone Europe/Warsaw  # local times (auto-detected on first run)
spacecrew --generate-completion bash  # bash|zsh|fish
man spacecrew            # manual page
```
## Data Source

Data provided by [International Space Station APIs](https://github.com/corquaid/international-space-station-APIs) by **Cormac Quaid**
