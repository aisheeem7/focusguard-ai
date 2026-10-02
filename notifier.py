"""
notifier.py

Feature 1: Real-Time Distraction Notifications.

Wraps `plyer` to show a native OS notification (Windows toast / macOS
notification center / Linux notify-send) the moment a distraction alert
fires - instead of only printing to the terminal, which is easy to miss
if the terminal isn't in focus (and it usually isn't, if you're
distracted).

Setup:
    pip install plyer

If plyer isn't installed, or the OS notification backend isn't
available (e.g. running headless, or on an unsupported platform), this
silently falls back to a console print - it never crashes the tracker.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from plyer import notification as _plyer_notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False


# The app's logo on Windows toasts (plyer needs an .ico there); other
# platforms keep their default notification icon.
_APP_ICON = Path(__file__).with_name("logo.ico")
APP_ICON = str(_APP_ICON) if sys.platform == "win32" and _APP_ICON.is_file() else ""


class DesktopNotifier:
    def __init__(self, app_name: str = "Focus Tracker", enabled: bool = True):
        self.app_name = app_name
        self.enabled = enabled and PLYER_AVAILABLE
        self._warned = False

        if enabled and not PLYER_AVAILABLE:
            print("[info] 'plyer' not installed (pip install plyer) - "
                  "desktop notifications disabled, alerts still print to console.",
                  file=sys.stderr)

    def notify(self, title: str, message: str, timeout: int = 8) -> None:
        """Show a native OS notification. Never raises - falls back to a
        console print if the notification backend fails for any reason
        (missing OS service, headless environment, unsupported platform)."""
        if not self.enabled:
            return
        try:
            _plyer_notification.notify(
                title=title,
                message=message,
                app_name=self.app_name,
                app_icon=APP_ICON,
                timeout=timeout,
            )
        except Exception as exc:
            if not self._warned:
                print(f"[warn] Desktop notification failed ({exc}); "
                      f"falling back to console output only.", file=sys.stderr)
                self._warned = True
