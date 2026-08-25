# spacecrew
Spacecrew is a lightweight Python terminal program that shows who is in space right now.

<img width="800" height="600" alt="92_1x_shots_so" src="https://github.com/user-attachments/assets/dfd95ad7-904d-4495-9c98-b8e1751ea5f3" />


## Tested Systems

* **CachyOS**
* **Ubuntu**
* **Debian**

## Installation

Clone the repository and run the setup script to automatically install dependencies and configure the command:

```bash
git clone https://github.com/jakub-ginal/spacecrew
cd spacecrew
chmod +x setup.sh
./setup.sh
```
Or run it via this single command:
```bash
git clone https://github.com/jakub-ginal/spacecrew && cd spacecrew && bash setup.sh && hash -r && cd ~ && rm -rf ~/spacecrew
```
## Usage

Simply type `spacecrew` anywhere in your terminal.
Follow the interactive menu to select a mission or view specific astronaut details and photos.

### Time in Space

* **p (previous)**: Days from past missions.
* **c (current)**: Days from the current mission (tracked live).
<img width="800" height="600" alt="356_1x_shots_so" src="https://github.com/user-attachments/assets/a87a2e9d-3c5a-443c-b62f-ec19f2922f0d" />

 
## Uninstall

To completely remove the program and its configuration from your system, run:
```bash
cd ~ && rm -rf ~/spacecrew && rm -f ~/.local/bin/spacecrew && hash -r
```
## Data Source

Data provided by [International Space Station APIs](https://github.com/corquaid/international-space-station-APIs) by **Cormac Quaid**.
