#!/usr/bin/env bash
set -e

echo "========================================================"
echo "  ⚡ Setting up J.A.R.V.I.S. for Arch Linux / Hyprland"
echo "========================================================"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[1/3] Installing required Arch Linux packages..."
sudo pacman -S --needed libnotify wl-clipboard espeak-ng rofi-wayland mpv grim slurp playerctl python

if [ ! -d "venv" ]; then
    echo "[2/3] Creating Python virtual environment..."
    python -m venv venv
fi

echo "[3/3] Installing Python libraries..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

if [ ! -f ".env" ]; then
    cp .env.example .env
    chmod 600 .env
    echo "Created .env from .env.example! Add your API key inside $SCRIPT_DIR/.env"
fi

chmod +x jarvis.py rofi_jarvis.sh
echo "========================================================"
echo "  ✅ Setup complete! Test with: ./rofi_jarvis.sh"
echo "========================================================"
