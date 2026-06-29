@echo off
if not exist venv\Scripts\activate (
    echo Virtual environment not found. Please run install_windows.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate
python run.py
pause
