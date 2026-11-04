@echo off
cd /d "%~dp0"
if not exist venv\Scripts\pythonw.exe (
    echo Virtual environment not found! Running setup_windows.bat first...
    call setup_windows.bat
)
echo Starting J.A.R.V.I.S. in the background (Press Alt + A anywhere to summon)...
start "" venv\Scripts\pythonw.exe jarvis_windows.py
