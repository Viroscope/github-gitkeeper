@echo off
REM GitKeeper - GitHub Repository Management Tool (Windows)
REM This script activates the virtual environment and starts the TUI application

echo 🛡️  Starting GitKeeper...

REM Check if virtual environment exists
if not exist ".venv" (
    echo ❌ Virtual environment not found. Please run 'python -m venv .venv' first.
    pause
    exit /b 1
)

REM Check if requirements are installed
if not exist ".venv\Lib\site-packages\textual" (
    echo 📦 Installing requirements...
    .venv\Scripts\pip install -r requirements.txt
)

REM Activate virtual environment and start the application
echo 🎯 Launching TUI application...
echo.

REM Run the TUI application
.venv\Scripts\python tui_app.py

echo.
echo 👋 GitKeeper closed.
pause