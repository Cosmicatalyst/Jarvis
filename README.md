# ⚡ Personal J.A.R.V.I.S. (Arch Linux / Hyprland & Windows 10/11)

A lightweight, fast desktop AI assistant inspired by Tony Stark's **J.A.R.V.I.S.** with a floating Siri-style command bar, a top-center **live token-streaming HUD card**, neural British voice synthesis (`edge-tts`), AI screen vision, live web search, Gmail integration, and local OS controls.

Works natively on **both**:
- 🐧 **Arch Linux (Hyprland + Rofi + Quickshell)**
- 🪟 **Windows 10 / 11** (Built-in dark Tkinter HUD overlay + global `Alt + A` hotkey)

---

## ✨ Features

- **⚡ Top-Center Live Streaming HUD**: Streams words live as Jarvis thinks, with one-click buttons right on the card:
  - `🔊 Replay` — Replay the last spoken response anytime without re-asking
  - `🎙️ Voice ON / 💬 Text Only` — Switch between voice + subtitles and silent text-box mode
  - `📋 Copy` — Copy Jarvis's answer to your clipboard
  - `📌 Pin` — Pin the HUD card to the top of your screen
  - `✕` — Stop speech and dismiss
- **🎙️ OG British Jarvis Voice + 8 Neural Presets**: Powered by `edge-tts` (`en-GB-RyanNeural` with Iron Man HUD acoustic tuning) plus instant switching between British, American, and Indian neural voices.
- **👁️ AI Screen Vision**: Ask *"What's on my screen?"* or *"Explain this error on my screen"*—Jarvis captures your screen and analyzes it with AI vision.
- **🌐 Live Web Search & Instant Weather**: Searches DuckDuckGo (`ddgs`) and `wttr.in` for real-time news, facts, and weather.
- **🔧 Smart Clipboard Fixer**: Copy broken code or messy text, tell Jarvis *"Fix my clipboard"*, and press `Ctrl + V` to paste the fixed version.
- **📧 Gmail Integration**: Check unread primary emails or send emails hands-free.

---

## 🪟 Windows 10 / 11 Setup (2-Minute Install)

1. **Install Python 3.11+** from [python.org/downloads](https://www.python.org/downloads/) *(check **"Add python.exe to PATH"** during install)*.
2. **Clone or download this repository**:
   ```powershell
   git clone https://github.com/Cosmicatalyst/Jarvis.git
   cd Jarvis
   ```
3. **Double-click `setup_windows.bat`**:
   - Automatically creates the Python virtual environment (`venv`), installs all Windows packages, creates `.env` from `.env.example`, and opens `.env` in Notepad so you can paste your API key.
4. **Double-click `run_windows.bat`**:
   - Starts Jarvis in the background.
   - Press **`Alt + A`** anywhere on Windows to pop up the Jarvis command bar!

---

## 🐧 Arch Linux + Hyprland Setup

1. **Clone the repository and run the setup script**:
   ```bash
   git clone https://github.com/Cosmicatalyst/Jarvis.git ~/jarvis
   cd ~/jarvis
   ./setup_linux.sh
   ```
2. **Add your API key**:
   Edit `~/jarvis/.env` and add your API key (see below).
3. **(Optional) Quickshell Top-Center HUD**:
   Copy `quickshell/JarvisSubtitles.qml` into `~/.config/quickshell/` and add `JarvisSubtitles {}` to your `shell.qml`.
4. **Add Hyprland Keybinds**:
   - **Standard `hyprland.conf`**:
     ```ini
     bind = $mainMod, A, exec, ~/jarvis/rofi_jarvis.sh
     bind = $mainMod SHIFT, A, exec, kitty --class jarvis-hud --title '⚡ Jarvis HUD' -e ~/jarvis/venv/bin/python ~/jarvis/jarvis.py
     bind = $mainMod ALT, A, exec, ~/jarvis/venv/bin/python ~/jarvis/jarvis.py --voice-menu
     ```
   - **Lua Config (`keybinds.lua`)**:
     ```lua
     hl.bind(mainMod .. " + A",         hl.dsp.exec_cmd(home .. "/jarvis/rofi_jarvis.sh"))
     hl.bind(mainMod .. " + SHIFT + A", hl.dsp.exec_cmd("kitty --class jarvis-hud --title '⚡ Jarvis HUD' -e " .. home .. "/jarvis/venv/bin/python " .. home .. "/jarvis/jarvis.py"))
     hl.bind(mainMod .. " + ALT + A",   hl.dsp.exec_cmd(home .. "/jarvis/venv/bin/python " .. home .. "/jarvis/jarvis.py --voice-menu"))
     ```

---

## 🔑 Getting Your Own API Key (`.env`)

Your private keys live in `.env` (which is ignored by Git so your keys stay private). You can use **any** of these providers in `.env`:

1. **Google Gemini (Free)**: Generate a free key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and paste it into `GEMINI_API_KEY="..."`.
2. **Groq (Free & Ultra-Fast)**: Generate a free key at [console.groq.com/keys](https://console.groq.com/keys) and paste it into `GROQ_API_KEY="..."`.
3. **TNSA AI**: Paste your key from [platform.tnsaai.com](https://platform.tnsaai.com) into `TNSA_API_KEY="..."`.
4. **Zero-Key Free Fallback**: Even if you leave all API keys blank, Jarvis automatically falls back to a free OpenAI-compatible endpoint so you can test it immediately!

### Optional: Gmail Integration
1. Turn on 2-Step Verification on your Google Account.
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), create an App Password named `Jarvis`, and paste the 16-letter code into `GMAIL_APP_PASS` alongside your `GMAIL_USER` email in `.env`.
