@echo off
echo Creating virtual environment...
py -m venv venv

if errorlevel 1 (
    echo Failed to create virtual environment. Please install Python 3.8+ and try again.
    pause
    exit /b 1
)

echo Activating virtual environment...
call venv\Scripts\activate

echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing base requirements...
pip install -r requirements.txt

if errorlevel 1 (
    echo Installation failed. Please check the error above.
    pause
    exit /b 1
)

echo.
echo Installation complete.
echo To run the app, double-click run_windows.bat
pause
