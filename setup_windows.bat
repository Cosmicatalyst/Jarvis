@echo off
title J.A.R.V.I.S. Windows Setup
echo ========================================================
echo   Setting up J.A.R.V.I.S. for Windows 10/11...
echo ========================================================

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.11+ from https://www.python.org/downloads/
    echo (Make sure to check "Add python.exe to PATH" during installation)
    pause
    exit /b 1
)

if not exist venv (
    echo [1/3] Creating Python virtual environment...
    python -m venv venv
)

echo [2/3] Installing Python packages...
call venv\Scripts\pip.exe install --upgrade pip
call venv\Scripts\pip.exe install -r requirements-windows.txt

if not exist .env (
    echo [3/3] Creating .env configuration file...
    if exist .env.example (
        copy .env.example .env >nul
    ) else if exist env.example.txt (
        copy env.example.txt .env >nul
    ) else (
        (
            echo TNSA_API_KEY="put_your_tnsa_api_key_here"
            echo TNSA_MODEL="NGen-4.5-Vayu"
            echo GEMINI_API_KEY=""
            echo GROQ_API_KEY=""
            echo GMAIL_USER="your_email@gmail.com"
            echo GMAIL_APP_PASS="xxxx xxxx xxxx xxxx"
            echo JARVIS_VOICE="en-GB-RyanNeural"
            echo JARVIS_VOICE_RATE="+6%%"
            echo JARVIS_VOICE_PITCH="-2Hz"
            echo JARVIS_VOICE_ENABLED="1"
        ) > .env
    )
    echo.
    echo Created .env! Opening .env in Notepad so you can paste your API key...
    notepad .env
)

echo.
echo ========================================================
echo   Setup Complete! Double-click run_windows.bat to start!
echo   Shortcut: Press Alt + A anywhere to summon Jarvis!
echo ========================================================
pause
