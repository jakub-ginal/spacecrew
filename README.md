# spacecrew
Spacecrew is a lightweight Python terminal program that shows who is in space right now.

<img width="792" height="582" alt="obraz" src="https://github.com/user-attachments/assets/f0595d9e-2cfc-40c7-ae9d-1a4ae780412d" />


## Tested Systems

* **CachyOS**
* **Ubuntu**
* **Debian**

## Installation

Clone the repository and run the setup script to automatically install dependencies and configure the command:

```
git clone [https://github.com/xxx/spacecrew.git](https://github.com/xxx/spacecrew.git)
cd spacecrew
chmod +x setup.sh
./setup.sh
```
Or run it via this single command:
```
git clone [https://github.com/xxx/spacecrew.git](https://github.com/xxx/spacecrew.git) && cd spacecrew && bash setup.sh && hash -r && cd ~ && rm -rf ~/spacecrew
```
## Usage

Simply type `spacecrew` anywhere in your terminal.
Follow the interactive menu to select a mission or view specific astronaut details and photos.

## Uninstall

To completely remove the program and its configuration from your system, run:
```
cd ~ && rm -rf ~/spacecrew && rm -f ~/.local/bin/spacecrew && hash -r
```
