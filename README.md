#  Jarvis

A lightweight personal AI desktop assistant with a popup command bar, top-center live streaming HUD, neural British voice, screen reading, web search, and system controls. Works on **Windows** and **Arch Linux (Hyprland)**.

## Features
- **Live Streaming HUD** — Top-center overlay that streams answers live with Replay, Voice/Text toggle, Copy, and Pin buttons.
- **Neural British Voice** — OG Jarvis voice (`edge-tts`) + 8 switchable voices.
- **Screen Vision** — Ask *"What's on my screen?"* to read or debug anything visible.
- **Web Search & Weather** — Live internet search and instant weather lookups.
- **System & Gmail Tools** — Fix clipboard text/code, control media, check battery/updates, and read/send Gmail.

## How to Get

### Windows
1. Install [Python 3.11+](https://www.python.org/downloads/) (check **"Add python.exe to PATH"**).
2. Download or clone this repo:
   ```powershell
   git clone https://github.com/Cosmicatalyst/Jarvis.git
   cd Jarvis
   ```
3. Double-click **`setup_windows.bat`** (sets up everything and opens `.env` to paste an optional API key).
4. Double-click **`run_windows.bat`**, then press **`Alt + A`** anywhere to summon Jarvis.

### Arch Linux (Hyprland)
```bash
git clone https://github.com/Cosmicatalyst/Jarvis.git ~/jarvis
cd ~/jarvis
./setup_linux.sh
```
Add your API key in `~/jarvis/.env` and bind `~/jarvis/rofi_jarvis.sh` to a shortcut (e.g. `Super + A`).
