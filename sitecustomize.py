"""
Auto-load browser session stability patch when Python starts from this repo.
"""

try:
    import browser_session_patch  # noqa: F401
except Exception as exc:
    print(f"Warning: browser session patch did not load: {exc}")
