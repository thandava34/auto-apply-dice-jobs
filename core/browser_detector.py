"""Locate a supported Chromium browser without scanning unrelated user data."""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

from dotenv import find_dotenv, load_dotenv, set_key


_CACHED_BROWSER_PATH: str | None = None


def _candidate_paths() -> list[tuple[str, str]]:
    """Return deterministic candidates in preference order."""
    system = platform.system()
    if system == "Windows":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        roots = [program_files, program_files_x86, local_app_data]
        candidates: list[tuple[str, str]] = []
        for name, relative in (
            ("Brave", r"BraveSoftware\Brave-Browser\Application\brave.exe"),
            ("Chrome", r"Google\Chrome\Application\chrome.exe"),
            ("Chromium", r"Chromium\Application\chrome.exe"),
        ):
            for root in roots:
                if root:
                    candidates.append((name, os.path.join(root, relative)))
        return candidates

    if system == "Darwin":
        return [
            ("Brave", "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
            ("Chrome", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            ("Chromium", "/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]

    return [
        ("Brave", path) for path in ("/usr/bin/brave-browser", "/usr/bin/brave")
    ] + [
        ("Chrome", path) for path in ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable")
    ] + [
        ("Chromium", path) for path in ("/usr/bin/chromium", "/usr/bin/chromium-browser")
    ]


def detect_browser_paths() -> str | None:
    """Find Brave, Chrome, or Chromium and remember the selected executable."""
    global _CACHED_BROWSER_PATH
    if _CACHED_BROWSER_PATH and os.path.isfile(_CACHED_BROWSER_PATH):
        return _CACHED_BROWSER_PATH

    for name, candidate in _candidate_paths():
        if os.path.isfile(candidate):
            print(f"Selected {name} browser")
            _CACHED_BROWSER_PATH = os.path.abspath(candidate)
            update_env_file(_CACHED_BROWSER_PATH)
            return _CACHED_BROWSER_PATH

    for name, command_names in (
        ("Brave", ("brave-browser", "brave")),
        ("Chrome", ("google-chrome", "google-chrome-stable", "chrome")),
        ("Chromium", ("chromium", "chromium-browser")),
    ):
        for command in command_names:
            candidate = shutil.which(command)
            if candidate and os.path.isfile(candidate):
                print(f"Selected {name} browser")
                _CACHED_BROWSER_PATH = os.path.abspath(candidate)
                update_env_file(_CACHED_BROWSER_PATH)
                return _CACHED_BROWSER_PATH

    print("No compatible Chromium browser found.")
    return None


def update_env_file(browser_path: str) -> str:
    """Persist a validated browser path while preserving every other .env key."""
    if not browser_path or not os.path.isfile(browser_path):
        raise ValueError("browser_path must point to an existing executable file")

    dotenv_path = find_dotenv(usecwd=True)
    if not dotenv_path:
        dotenv_path = os.path.join(os.getcwd(), ".env")
        Path(dotenv_path).touch(exist_ok=True)
    set_key(dotenv_path, "WEB_BROWSER_PATH", os.path.abspath(browser_path))
    return os.path.abspath(browser_path)


def get_browser_path() -> str:
    """Return a configured browser path or detect a supported browser."""
    load_dotenv()
    configured = os.getenv("WEB_BROWSER_PATH", "").strip().strip('"').strip("'")
    if configured and os.path.isfile(configured):
        return os.path.abspath(configured)

    detected = detect_browser_paths()
    if not detected:
        raise RuntimeError(
            "No compatible Chromium browser found. Install Google Chrome, Brave, or Chromium, "
            "or set WEB_BROWSER_PATH in .env."
        )
    return detected


if __name__ == "__main__":
    try:
        print(f"Browser path successfully set: {get_browser_path()}")
    except Exception as exc:
        print(f"Error: {exc}")
