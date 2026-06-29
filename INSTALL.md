# Installation Guide

This project now keeps the base install lightweight. The AI semantic matcher is optional.

## Windows

1. Double-click `install_windows.bat`.
2. After installation finishes, double-click `run_windows.bat`.

Or run manually:

```bat
py -m venv venv
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python run.py
```

## macOS / Linux

```bash
chmod +x install_mac.sh run_mac.sh
./install_mac.sh
./run_mac.sh
```

Or run manually:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python3 run.py
```

## Optional AI semantic matching

The base install does not install heavy AI packages like PyTorch and SentenceTransformers. The app will still run and will fall back to keyword/profile matching.

To enable AI semantic resume matching:

```bash
pip install -r requirements-ai.txt
```

## Login/session stability

The app now uses a local `browser_profile/` folder for Selenium. This keeps Dice cookies and login session data between runs, so users should not get sent back to login as often.

If login starts acting strange, close the app and delete the `browser_profile/` folder. The app will create a fresh profile on the next run.
