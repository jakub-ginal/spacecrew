#!/bin/bash

if command -v chafa &> /dev/null; then
    echo "chafa is already installed. Skipping dependency installation."
else
    echo "Installing missing dependency: chafa..."
    if command -v pacman &> /dev/null; then
        sudo pacman -S --needed --noconfirm chafa
    elif command -v apt &> /dev/null; then
        sudo apt update && sudo apt install -y chafa
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y chafa
    else
        echo "Warning: Could not detect package manager. Please install 'chafa' manually."
    fi
fi

cp spacecrew "$HOME/.local/bin/spacecrew"

chmod +x "$HOME/.local/bin/spacecrew"

echo "spacecrew installed successfully! You can now use it anywhere."
