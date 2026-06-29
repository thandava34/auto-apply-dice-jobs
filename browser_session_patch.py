"""
Browser session stability patch.

This module keeps Selenium browser sessions persistent by using a local
browser_profile/ folder and by preventing incognito mode from being applied.
It is imported before the Tkinter app starts, so the existing Selenium setup
can keep Dice cookies between runs without changing the main automation flow.
"""

import os

_PATCHED = False


def patch_selenium_chrome_options():
    """Patch Selenium Chrome Options to keep cookies/session data between runs."""
    global _PATCHED
    if _PATCHED:
        return

    try:
        from selenium.webdriver.chrome.options import Options
    except Exception as exc:
        print(f"Warning: Could not patch browser session options: {exc}")
        return

    original_init = Options.__init__
    original_add_argument = Options.add_argument

    def patched_add_argument(self, argument):
        # Incognito deletes cookies every run and causes Dice to ask for login again.
        if str(argument).strip().lower() == "--incognito":
            return None
        return original_add_argument(self, argument)

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)

        disable_persistent_profile = os.getenv("DICE_DISABLE_PERSISTENT_PROFILE", "").lower() in {
            "1", "true", "yes", "on"
        }
        if disable_persistent_profile:
            return

        profile_dir = os.getenv("DICE_BROWSER_PROFILE_DIR") or os.path.join(os.getcwd(), "browser_profile")
        existing_args = list(getattr(self, "arguments", []) or [])
        has_user_data_dir = any(str(arg).startswith("--user-data-dir=") for arg in existing_args)

        if not has_user_data_dir:
            os.makedirs(profile_dir, exist_ok=True)
            original_add_argument(self, f"--user-data-dir={profile_dir}")
            original_add_argument(self, "--profile-directory=Default")

    Options.add_argument = patched_add_argument
    Options.__init__ = patched_init
    _PATCHED = True


patch_selenium_chrome_options()
