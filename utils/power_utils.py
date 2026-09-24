"""
power_utils.py
==============
Provides OS-level power management functions to prevent screen display timeout
and system sleep during long-running automation processes (e.g. Dice Job Application).
"""

import sys
import ctypes
import logging

logger = logging.getLogger(__name__)

# Windows API constants for SetThreadExecutionState
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

_keep_awake_active = False


def prevent_sleep() -> bool:
    """
    Prevents Windows from turning off the display or entering system sleep.
    Safe no-op on non-Windows platforms.
    """
    global _keep_awake_active
    if sys.platform == "win32":
        try:
            # Set continuous execution state requiring both system and display
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            )
            _keep_awake_active = True
            logger.info("🔒 Keep-Awake Enabled: Screen and System will remain active during execution.")
            return True
        except Exception as e:
            logger.error(f"Failed to enable keep-awake state: {e}")
            return False
    return False


def allow_sleep() -> bool:
    """
    Restores normal Windows power management (display turn-off / sleep).
    Safe no-op on non-Windows platforms.
    """
    global _keep_awake_active
    if sys.platform == "win32":
        try:
            # Reset thread execution state back to continuous normal behavior
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            _keep_awake_active = False
            logger.info("🔓 Keep-Awake Disabled: Standard system power/sleep settings restored.")
            return True
        except Exception as e:
            logger.error(f"Failed to restore sleep state: {e}")
            return False
    return False


def is_keep_awake_active() -> bool:
    """Returns True if keep-awake mode is currently engaged."""
    return _keep_awake_active
