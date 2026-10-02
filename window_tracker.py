"""
window_tracker.py

Detects the currently active (foreground) window/tab, tracks switches
between apps, categorizes each app as productive / distraction / neutral
(resolving ambiguous apps like Gallery or YouTube via a quick terminal
prompt), and shows a live-updating terminal UI (via `rich`) with a
"you are distracted" alert when the DISTRACTION-specific switch count
passes a threshold - switching a lot between productive apps never
triggers it.

Session records (unchanged shape, now with a "category" field):
{
  "source": "agent",
  "name": "Notepad",
  "category": "productive",
  "start_time": "09:00",
  "end_time": "09:02",
  "duration": 120
}

Switch records:
{"from": "VS Code", "to": "Instagram"}
{"total_switch_count": 11, "distraction_switch_count": 11}

Python 3.11+

------------------------------------------------------------------------
Install dependencies:

    pip install rich                     # terminal UI (required)
    pip install anthropic                # optional: LLM auto-classification

Windows:  pip install pywin32 psutil
macOS:    pip install pyobjc-framework-Cocoa psutil
Linux:    sudo apt-get install xdotool wmctrl   &&   pip install psutil

To enable Claude Haiku auto-classification of unrecognized apps, set:
    ANTHROPIC_API_KEY  (see llm_classifier.py for setup details)

------------------------------------------------------------------------
Usage:
    python window_tracker.py
    python window_tracker.py --interval 0.5
    python window_tracker.py --out activity.jsonl --switch-out switch_log.jsonl
    python window_tracker.py --distraction-threshold 10
    python window_tracker.py --alert-after 15          # "stayed too long" alert
    python window_tracker.py --config app_categories.json
    python window_tracker.py --no-ui                    # plain text, no rich table
    python window_tracker.py --no-llm                   # skip Haiku fallback
    python window_tracker.py --idle-minutes 5           # stop counting after 5 min without input
    python window_tracker.py --background               # no window; logs to ~/.focusguard/tracker.log
    python window_tracker.py --install-startup          # Windows: start with Windows, in the background
    python window_tracker.py --remove-startup
    python window_tracker.py --stop                     # stop a tracker running in the background
    python window_tracker.py --sign-out                 # forget the saved online sign-in

Category logic
--------------
- Desktop apps are recognised by their program (WINWORD.EXE, explorer.exe...)
  through the "processes" table in app_categories.json, so a session is
  "Microsoft Word" whichever document is open, and opening another folder
  in File Explorer isn't counted as switching apps. Other programs are
  named from their own file description and classified once (backend AI,
  cached).
- "productive": never triggers the distraction alert, no matter how high
  total_switch_count gets.
- "distraction": every switch INTO one of these increments
  distraction_switch_count. Once that count exceeds the threshold
  (default 10), a "YOU ARE DISTRACTED" alert flashes - and keeps
  re-flashing on every further distraction switch, since the counter is
  cumulative and never resets during a run.
- "ambiguous" (Gallery, YouTube, VLC, etc.): classified from what's
  actually open - the video/file/page title - via the backend's keyword,
  curated-list and LLM chain. Only if that can't decide, and you're at
  an interactive terminal, are you asked how you're using it (your
  answer is remembered for the rest of the run); otherwise it's neutral.
- Browser windows: left to the browser extension when it's running in
  that browser (so time isn't counted twice); otherwise the page title
  is classified the same way as above.
- "neutral": doesn't count toward distraction_switch_count.
- Anything not covered by any list in app_categories.json is sent to
  Claude Haiku for one-time classification (cached in
  learned_categories.json), unless --no-llm is passed or no API key is
  configured, in which case it defaults to "neutral".

To analyze switching behavior after the fact, run:
    python analyze_activity.py activity_log.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from llm_classifier import LLMClassifier
from backend_client import DEFAULT_BACKEND_URL, BackendClient, forget_saved_session
from notifier import DesktopNotifier

try:
    from rich.console import Console, Group
    from rich.live import Live
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


SOURCE_LABEL = "system"
DEFAULT_CONFIG_PATH = Path(__file__).with_name("app_categories.json")
MAX_TABLE_ROWS = 12  # keep the live table to a manageable size
BACKEND_SYNC_SECONDS = 15
# Bound for as long as a tracker runs, so a second copy (e.g. one started
# by the launcher and one by the backend at the same moment) exits
# instead of double-counting every minute.
SINGLE_INSTANCE_PORT = 47821
# Where a background tracker writes its output, and remembers that the
# "start with Windows?" question was already answered.
STATE_DIR = Path.home() / ".focusguard"
BACKGROUND_LOG = STATE_DIR / "tracker.log"
PREFS_FILE = STATE_DIR / "tracker_prefs.json"
STARTUP_VALUE_NAME = "FocusGuard Tracker"
# Returned while an online classification is still on its way, so the
# polling loop never waits seconds on the server.
PENDING = "pending"


def _whole_word_in(entry: str, text: str) -> bool:
    # "word" must not fire inside "password", "git" inside "digital",
    # "steam" inside "livestream".
    return re.search(r"(?<![\w])" + re.escape(entry) + r"(?![\w])", text) is not None


# --------------------------------------------------------------------------
# App categorization (productive / distraction / ambiguous / neutral / ignore)
# --------------------------------------------------------------------------

class AppCategorizer:
    """Classifies an app/window name using app_categories.json first, then
    (Feature 6 extended to system apps) the backend's crowdsourced
    classifier - the same group/global cache the browser extension's
    domain lookups already share, so "what is WINWORD.EXE" gets answered
    once per group instead of once per user, and works via whichever LLM
    provider the backend has configured rather than requiring this
    machine's own ANTHROPIC_API_KEY. Falls back to a local LLMClassifier
    (direct Anthropic call) only if the backend is unreachable/disabled,
    so a fully offline run still classifies unrecognized apps if that
    key happens to be set locally."""

    def __init__(
        self,
        config_path: Path = DEFAULT_CONFIG_PATH,
        llm_classifier: Optional[LLMClassifier] = None,
        backend: Optional[BackendClient] = None,
    ):
        self.productive: list[str] = []
        self.distraction: list[str] = []
        self.ambiguous: list[str] = []
        self.neutral: list[str] = []
        self.ignore: list[str] = []
        self.processes: dict[str, tuple[str, str]] = {}  # "winword" -> ("Microsoft Word", "productive")
        self.llm_classifier = llm_classifier
        self.backend = backend
        self._backend_cache: dict[str, str] = {}  # avoids an HTTP round-trip on every repeat switch to an already-known app
        self._title_cache: dict[str, str] = {}
        # Online lookups run here, off the polling loop - a cold one can
        # take the server many seconds (LLM providers, a sleeping host).
        self._executor: Optional[ThreadPoolExecutor] = None
        self._pending: dict[tuple[str, str], Future] = {}
        self._load(config_path)

    def _load(self, config_path: Path) -> None:
        if not config_path.exists():
            print(f"[warn] Category config not found at {config_path}; "
                  f"relying entirely on LLM fallback / 'neutral'.", file=sys.stderr)
            return
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"[warn] Could not parse {config_path}: {exc}", file=sys.stderr)
            return
        self.productive = [s.lower() for s in data.get("productive", [])]
        self.distraction = [s.lower() for s in data.get("distraction", [])]
        self.ambiguous = [s.lower() for s in data.get("ambiguous", [])]
        self.neutral = [s.lower() for s in data.get("neutral", [])]
        self.ignore = [s.lower() for s in data.get("ignore", [])]
        self.processes = {
            proc.lower(): (entry[0], entry[1].lower())
            for proc, entry in data.get("processes", {}).items()
            if isinstance(entry, list) and len(entry) == 2
        }

    def known_app(self, process: str) -> Optional[tuple[str, str]]:
        """(display name, category) for a program in the "processes"
        table, by executable name - "WINWORD" -> ("Microsoft Word",
        "productive") - or None."""
        return self.processes.get((process or "").strip().lower())

    def should_ignore(self, app_name: str, process: str = "") -> bool:
        if (process or "").strip().lower() in self.ignore:
            return True
        name = app_name.lower()
        return any(_whole_word_in(k, name) for k in self.ignore)

    def _static_category(self, name: str) -> Optional[str]:
        for category, entries in (("distraction", self.distraction), ("productive", self.productive),
                                  ("ambiguous", self.ambiguous), ("neutral", self.neutral)):
            if any(_whole_word_in(k, name) for k in entries):
                return category
        return None

    def _backend_answer(self, kind: str, key: str, ask: Callable[[str], Optional[str]], text: str) -> Optional[str]:
        """A cached answer; else asks the backend - inline when it's on
        this machine (milliseconds), in the background when it's online,
        returning PENDING until the answer lands. None when there's no
        backend to ask or it couldn't answer."""
        cache = self._title_cache if kind == "title" else self._backend_cache
        if key in cache:
            return cache[key]
        if self.backend is None or not self.backend.enabled:
            return None
        if not self.backend.online:
            result = ask(text)
            if result is not None:
                cache[key] = result
            return result
        future = self._pending.get((kind, key))
        if future is None:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="focusguard-classify")
            self._pending[(kind, key)] = self._executor.submit(ask, text)
            return PENDING
        if not future.done():
            return PENDING
        del self._pending[(kind, key)]
        result = future.result()
        if result is not None:
            cache[key] = result
        return result

    def raw_categorize(self, app_name: str) -> str:
        """Returns 'productive' | 'distraction' | 'ambiguous' | 'neutral'
        (or PENDING while an online lookup is in flight), consulting the
        shared backend classifier (then a local LLM fallback) only for
        names not in any config list. 'ambiguous' stays purely
        local/static - it's a "judge what's open, then ask the user"
        concept the backend's three-way classifier has no equivalent for."""
        name = app_name.lower()
        static = self._static_category(name)
        if static is not None:
            return static

        result = self._backend_answer("app", name.strip(), self.backend.classify if self.backend else None, app_name)
        if result is not None:
            return result
        if self.llm_classifier is not None:
            return self.llm_classifier.classify(app_name)
        return "neutral"

    def classify_title(self, title: str) -> Optional[str]:
        """Classifies what's actually on screen from a window title - a
        browser page the extension isn't covering, a YouTube video, a
        file open in VLC - via the backend's keyword/curated-list/LLM
        chain. None when the backend can't answer, so callers can fall
        back to the static lists or the interactive prompt; PENDING while
        an online lookup is in flight."""
        key = title.strip().lower()
        if not key:
            return None
        return self._backend_answer("title", key, self.backend.classify_title if self.backend else None, title)


# --------------------------------------------------------------------------
# Ambiguous-app resolution (asks the user once per run, per app)
# --------------------------------------------------------------------------

class AmbiguousResolver:
    """For apps like Gallery or YouTube where intent matters, asks the
    user in the terminal how they're using it right now, and remembers
    the answer for the rest of this run."""

    PROMPTS: dict[str, tuple[str, list[tuple[str, str, str]]]] = {
        "gallery": (
            "Gallery detected - what are you using it for?",
            [("n", "Notes/reference", "productive"), ("i", "Images/casual browsing", "distraction")],
        ),
        "photos": (
            "Photos detected - what are you using it for?",
            [("n", "Notes/reference", "productive"), ("i", "Images/casual browsing", "distraction")],
        ),
        "youtube": (
            "YouTube detected - what are you watching?",
            [("t", "Tutorial/study content", "productive"), ("e", "Entertainment", "distraction")],
        ),
        "vlc": (
            "Media player detected - what are you watching/listening to?",
            [("s", "Study/work material", "productive"), ("e", "Entertainment", "distraction")],
        ),
        "media player": (
            "Media player detected - what are you watching/listening to?",
            [("s", "Study/work material", "productive"), ("e", "Entertainment", "distraction")],
        ),
    }
    DEFAULT_PROMPT = (
        "This app is ambiguous - how are you using it right now?",
        [("p", "Productive/work-related", "productive"), ("d", "Distracting/leisure", "distraction")],
    )

    def __init__(self):
        self._resolved: dict[str, str] = {}

    def resolve(self, app_name: str) -> str:
        key = app_name.lower()
        if key in self._resolved:
            return self._resolved[key]

        prompt_key = next((k for k in self.PROMPTS if k in key), None)
        question, options = self.PROMPTS.get(prompt_key, self.DEFAULT_PROMPT)

        print(f"\n{question}")
        for shortcut, label, _ in options:
            print(f"  [{shortcut}] {label}")
        try:
            choice = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            choice = ""
        chosen = next((label for shortcut, _, label in options if shortcut == choice), None)
        if chosen is None:
            chosen = options[0][2]  # default to the first (productive) option on blank/invalid input
        self._resolved[key] = chosen
        return chosen


# --------------------------------------------------------------------------
# Platform-specific "get the active window's app/process name" backends
# --------------------------------------------------------------------------

class WindowBackendError(RuntimeError):
    pass


@dataclass
class ActiveWindow:
    name: str          # "WINWORD - Report.docx - Word": process + title, as always logged
    process: str = ""  # executable without .exe ("WINWORD"), or the app name on macOS/Linux
    title: str = ""    # the window's own title
    app: str = ""      # the program's own name from its file description ("Microsoft Word"), if any


# The desktop wallpaper and the taskbar belong to explorer.exe too, but
# they aren't File Explorer - clicking them means no app is in use.
_SHELL_WINDOW_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                         "NotifyIconOverflowWindow", "TopLevelWindowForOverflowXamlIsland"}
_app_name_cache: dict[str, str] = {}


def _file_description(exe_path: str) -> str:
    """The name a program gives itself ("Microsoft Word" for WINWORD.EXE,
    "Visual Studio Code" for Code.exe) - stable whatever's open in it."""
    if exe_path in _app_name_cache:
        return _app_name_cache[exe_path]
    description = ""
    try:
        import win32api
        lang, codepage = win32api.GetFileVersionInfo(exe_path, "\\VarFileInfo\\Translation")[0]
        description = win32api.GetFileVersionInfo(
            exe_path, f"\\StringFileInfo\\{lang:04X}{codepage:04X}\\FileDescription") or ""
    except Exception:
        pass
    _app_name_cache[exe_path] = description.strip()
    return _app_name_cache[exe_path]


def _process_details(pid: int) -> tuple[str, str]:
    """(executable name without .exe, file description) for a process."""
    import psutil
    proc = psutil.Process(pid)
    process = Path(proc.name()).stem
    try:
        exe = proc.exe()  # can be refused for elevated apps like Task Manager
    except Exception:
        exe = ""
    return process, (_file_description(exe) if exe else "")


def _uwp_app_pid(hwnd: int, frame_pid: int) -> Optional[int]:
    """Store apps (Calculator, Settings, Photos, Media Player) all show up
    as ApplicationFrameHost.exe; the real app owns a child window."""
    import win32gui
    import win32process
    found: list[int] = []

    def visit(child, _):
        _, pid = win32process.GetWindowThreadProcessId(child)
        if pid != frame_pid:
            found.append(pid)
            return False
        return True

    try:
        win32gui.EnumChildWindows(hwnd, visit, None)
    except Exception:
        pass  # returning False from the callback stops enumeration and raises on some pywin32 builds
    return found[0] if found else None


def _get_active_window_windows() -> Optional[ActiveWindow]:
    import win32gui
    import win32process

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None
    try:
        if win32gui.GetClassName(hwnd) in _SHELL_WINDOW_CLASSES:
            return None  # desktop or taskbar: no app in use
    except Exception:
        pass
    title = win32gui.GetWindowText(hwnd)
    if not title:
        return None
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process, app = _process_details(pid)
        if process.lower() == "applicationframehost":
            child_pid = _uwp_app_pid(hwnd, pid)
            if child_pid:
                process, app = _process_details(child_pid)
            else:
                process, app = "", title  # minimised/suspended Store app: its title is its name
        # Combine process name + title so browser tab titles (which carry
        # the actual site name) are still visible to the categorizer.
        name = f"{process} - {title}" if process and process.lower() not in title.lower() else title
        return ActiveWindow(name=name, process=process, title=title, app=app)
    except Exception:
        return ActiveWindow(name=title, title=title)


def _get_active_window_macos() -> Optional[ActiveWindow]:
    from AppKit import NSWorkspace
    active_app = NSWorkspace.sharedWorkspace().activeApplication()
    if not active_app:
        return None
    name = active_app.get("NSApplicationName")
    return ActiveWindow(name=name, process=name, title=name, app=name) if name else None


def _get_active_window_linux() -> Optional[ActiveWindow]:
    try:
        win_id = subprocess.check_output(["xdotool", "getactivewindow"], stderr=subprocess.DEVNULL).decode().strip()
        if not win_id:
            return None
        wm_class = subprocess.check_output(["xdotool", "getwindowclassname", win_id], stderr=subprocess.DEVNULL).decode().strip()
        title = subprocess.check_output(["xdotool", "getwindowname", win_id], stderr=subprocess.DEVNULL).decode().strip()
        if wm_class and title:
            return ActiveWindow(name=f"{wm_class} - {title}", process=wm_class, title=title)
        name = wm_class or title
        return ActiveWindow(name=name, process=wm_class, title=title) if name else None
    except FileNotFoundError as exc:
        raise WindowBackendError("xdotool is not installed. Install it with: sudo apt-get install xdotool wmctrl") from exc
    except subprocess.CalledProcessError:
        return None


def get_active_window() -> Optional[ActiveWindow]:
    """The foreground window, or None when no app is in use."""
    system = platform.system()
    if system == "Windows":
        return _get_active_window_windows()
    elif system == "Darwin":
        return _get_active_window_macos()
    elif system == "Linux":
        return _get_active_window_linux()
    else:
        raise WindowBackendError(f"Unsupported platform: {system}")


def get_active_window_info() -> Optional[tuple[str, str]]:
    """(display name, process/app name) of the foreground window, or None.
    The process name is what tells a browser window apart from an app
    whose title merely mentions a browser."""
    window = get_active_window()
    return (window.name, window.process) if window else None


def seconds_since_last_input() -> Optional[float]:
    """How long the keyboard and mouse have been untouched (Windows), or
    None where that can't be read."""
    if platform.system() != "Windows":
        return None
    try:
        import ctypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        millis = (ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF
        return millis / 1000.0
    except Exception:
        return None


def get_active_window_name() -> Optional[str]:
    info = get_active_window_info()
    return info[0] if info else None


# Process/app names of browsers, mapped to the id the extension reports
# for itself (see detectBrowserClient in extension-patch/background.js).
BROWSER_CLIENTS = {
    "chrome": "chrome", "google chrome": "chrome", "chromium": "chrome", "google-chrome": "chrome",
    "msedge": "msedge", "microsoft edge": "msedge", "microsoft-edge": "msedge",
    "brave": "brave", "brave browser": "brave", "brave-browser": "brave",
    "opera": "opera", "vivaldi": "vivaldi", "firefox": "firefox",
}
# " - Google Chrome", " - Personal - Microsoft Edge", " — Mozilla Firefox"...
_BROWSER_TITLE_SUFFIX = re.compile(
    # Edge alone inserts the profile name: "... - Personal - Microsoft Edge".
    r"\s+[-\u2014\u2013]\s+(?:[^-\u2014\u2013]+?\s+[-\u2014\u2013]\s+(?=Microsoft))?"
    r"(?:Google Chrome|Chromium|Microsoft\u200b?\s?Edge|Brave|Opera|Vivaldi|Mozilla Firefox|Firefox)\s*$",
    re.IGNORECASE,
)
_BROWSER_NAME_PREFIX = re.compile(r"^(?:chrome|msedge|brave|opera|vivaldi|firefox)\s+-\s+", re.IGNORECASE)


def browser_client(process_name: str) -> Optional[str]:
    return BROWSER_CLIENTS.get((process_name or "").strip().lower())


def page_title_from_window(window_title: str) -> str:
    """'Lecture 4 - YouTube - Google Chrome' -> 'Lecture 4 - YouTube'."""
    title = _BROWSER_TITLE_SUFFIX.sub("", window_title).strip()
    # Drop a leading "chrome - " that _get_active_window_windows adds
    # when the title doesn't already name the browser.
    return _BROWSER_NAME_PREFIX.sub("", title)


# Programs that only host someone else's app (a Java or Python program,
# a script) - their own name says nothing, so the window title is used.
_HOST_PROCESSES = {"java", "javaw", "python", "pythonw", "py", "electron", "msedgewebview2",
                   "rundll32", "dllhost", "wscript", "cscript", "mshta", "conhost"}


# --------------------------------------------------------------------------
# Session tracking
# --------------------------------------------------------------------------

@dataclass
class Session:
    name: str
    start_dt: datetime
    category: str = "neutral"  # final resolved category: productive / distraction / neutral
    end_dt: Optional[datetime] = None
    alerted: bool = False  # "stayed too long" alert, separate from the switch-count alert

    def to_record(self) -> dict:
        end_dt = self.end_dt or datetime.now()
        duration = int((end_dt - self.start_dt).total_seconds())
        return {
            "source": SOURCE_LABEL,
            "name": self.name,
            "category": self.category,
            "start_time": self.start_dt.strftime("%H:%M"),
            "end_time": end_dt.strftime("%H:%M"),
            "duration": duration,
        }


class WindowTracker:
    def __init__(
        self,
        out_path: Path,
        switch_out_path: Path,
        interval: float = 1.0,
        min_duration: float = 0.0,
        categorizer: Optional[AppCategorizer] = None,
        alert_after: float = 10.0,
        distraction_threshold: int = 10,
        use_ui: bool = True,
        backend: Optional[BackendClient] = None,
        notifier: Optional[DesktopNotifier] = None,
        focus_minutes: Optional[int] = None,
        break_reminder_minutes: int = 50,
        idle_minutes: float = 5.0,
        interactive: Optional[bool] = None,
        stop_event: Optional[threading.Event] = None,
    ):
        self.out_path = out_path
        self.switch_out_path = switch_out_path
        self.interval = interval
        self.min_duration = min_duration
        self.categorizer = categorizer or AppCategorizer()
        self.alert_after = alert_after
        self.distraction_threshold = distraction_threshold
        self.use_ui = use_ui and RICH_AVAILABLE
        self.backend = backend or BackendClient()  # reads TRACKER_BACKEND_URL/USERNAME/PASSWORD env vars; no-ops if unset
        self.notifier = notifier or DesktopNotifier()  # Feature 1: native OS notifications
        self.focus_minutes = focus_minutes  # Feature 4: Focus Mode duration, if requested
        self.break_reminder_minutes = break_reminder_minutes  # Feature 6: 0 disables
        # No keyboard/mouse input for this long ends the current session
        # (backdated to the last input) - a PC left on Word over lunch
        # isn't an hour of work. Media and browser windows are exempt,
        # since watching something needs no input. 0 disables.
        self.idle_seconds = max(0.0, idle_minutes) * 60
        # Whether someone is at a terminal to answer "how are you using
        # this?" - never true for a background tracker.
        self.interactive = stdin_is_console() if interactive is None else interactive
        self.stop_event = stop_event or threading.Event()  # set by `--stop` from another process

        self.resolver = AmbiguousResolver()
        self._current: Optional[Session] = None
        self._previous_name: Optional[str] = None
        # While the current app's category is still being looked up online:
        # the arguments to look it up again, and the switch into it, which
        # is logged once the category is known.
        self._pending_lookup: Optional[tuple] = None
        self._switch_from: Optional[str] = None
        self.total_switch_count: int = 0
        self.distraction_switch_count: int = 0
        self._rows: list[dict] = []  # recent switch rows for the live table
        self._last_alert_flash: Optional[str] = None
        self._focus_session: Optional[dict] = None  # Feature 4: active/finalized session info
        self._focus_start_local: Optional[datetime] = None
        self._focus_finalized: bool = False
        self._streak_info: Optional[dict] = None  # Feature 2: fetched once at startup
        self._leaderboard_info: Optional[dict] = None  # Feature 3: fetched once at startup
        self._productive_streak_start: Optional[datetime] = None  # Feature 6
        self._break_reminder_shown: bool = False
        self._break_reminder_flash: Optional[str] = None  # separate from the (red) distraction alert
        self._last_live_status_push: Optional[datetime] = None  # Feature 7
        # Shared-account sync, refreshed every BACKEND_SYNC_SECONDS: browsers
        # the extension already covers, and the dashboard's Focus Mode state.
        self._extension_browsers: set[str] = set()
        self._last_backend_sync: Optional[datetime] = None
        self._watched_focus_id: Optional[int] = None
        self._watched_focus_status: Optional[str] = None

        self._console = Console() if RICH_AVAILABLE else None
        self._live: Optional["Live"] = None

    # -- categorization -----------------------------------------------

    def _identify(self, window: ActiveWindow, client: Optional[str]) -> tuple[str, Optional[str], Optional[str]]:
        """(session name, page title to judge, category if already known)
        for a foreground window. Desktop apps are named after the program,
        not the window title, so opening another document in Word or
        another folder in File Explorer isn't a switch."""
        if client is not None:
            return window.name, page_title_from_window(window.name), None
        known = self.categorizer.known_app(window.process)
        if known is not None:
            app, category = known
            if category == "ambiguous":
                # VLC, Photos: what's open decides, so it stays in the name.
                title = window.title or window.name
                return (title if app.lower() in title.lower() else f"{app} - {title}"), None, "ambiguous"
            return app, None, category
        if window.process and window.process.lower() not in _HOST_PROCESSES:
            return (window.app or window.process), None, None
        return window.name, None, None

    def _resolve_category(self, app_name: str, page_title: Optional[str] = None,
                          known: Optional[str] = None) -> str:
        """productive / distraction / neutral - or PENDING while an online
        lookup is still on its way (call again later with the same
        arguments; the answer is cached by then)."""
        if known is not None and known != "ambiguous":
            return known
        if page_title is not None:
            # A browser window the extension isn't covering: judge the page
            # itself (whole-word curated lists + LLM on the backend) rather
            # than substring-matching the raw window name.
            by_title = self.categorizer.classify_title(page_title)
            if by_title is not None:
                return by_title
            app_name = page_title
        raw = "ambiguous" if known == "ambiguous" else self.categorizer.raw_categorize(app_name)
        if raw == "ambiguous":
            # YouTube, VLC, Photos...: decide from what's actually open
            # (the video/file title) instead of stopping to ask - only an
            # unresolvable title falls back to asking, and only when
            # someone is at an interactive terminal to answer.
            by_title = self.categorizer.classify_title(app_name)
            if by_title in ("productive", "distraction", PENDING):
                return by_title
            if not self.interactive:
                return "neutral"
            if self.use_ui and self._live is not None:
                self._live.stop()
            resolved = self.resolver.resolve(app_name)
            if self.use_ui and self._live is not None:
                self._live.start()
            return resolved
        return raw

    # -- logging ---------------------------------------------------------

    def _emit_session(self, session: Session) -> None:
        record = session.to_record()
        if record["duration"] < self.min_duration:
            return
        with self.out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        if not self.use_ui:
            print(json.dumps(record), flush=True)
        self.backend.post_session(record)  # no-op if backend isn't configured/reachable

    def _emit_switch(self, from_name: str, to_name: str, category: str) -> None:
        self.total_switch_count += 1
        if category == "distraction":
            self.distraction_switch_count += 1

        switch_record = {"from": from_name, "to": to_name}
        count_record = {
            "total_switch_count": self.total_switch_count,
            "distraction_switch_count": self.distraction_switch_count,
        }
        with self.switch_out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(switch_record) + "\n")
            f.write(json.dumps(count_record) + "\n")

        if not self.use_ui:
            print(json.dumps(switch_record), flush=True)
            print(json.dumps(count_record), flush=True)

        # Backend's schema uses from_app/to_app since "from" is a reserved
        # word in Python - local file format stays {"from":..., "to":...}.
        self.backend.post_switch({
            "source": SOURCE_LABEL,
            "from_app": from_name,
            "to_app": to_name,
            "category": category,
            "total_switch_count": self.total_switch_count,
            "distraction_switch_count": self.distraction_switch_count,
        })

        self._rows.append({
            "from": from_name,
            "to": to_name,
            "category": category,
            "total": self.total_switch_count,
            "distraction": self.distraction_switch_count,
        })
        if len(self._rows) > MAX_TABLE_ROWS:
            self._rows.pop(0)

        if category == "distraction" and self.distraction_switch_count > self.distraction_threshold:
            self._flash_distraction_alert()

        # Feature 4: a distraction switch immediately breaks an active
        # focus session - check and finalize right away rather than
        # waiting for the next timer tick.
        if category == "distraction" and self._focus_session is not None and not self._focus_finalized:
            self._break_focus_session(to_name)

    def _break_focus_session(self, distracting_app: str) -> None:
        result = self.backend.end_focus_session(self._focus_session["id"])
        self._focus_finalized = True
        if result:
            self._focus_session = result
        msg = f"FOCUS SESSION BROKEN - switched to '{distracting_app}'"
        self._last_alert_flash = msg
        if not self.use_ui:
            print(f"\n*** {msg} ***\n", flush=True)
        self.notifier.notify(title="Focus session broken", message=f"You switched to '{distracting_app}'.")

    def _check_focus_mode(self) -> None:
        """Called every loop tick: detects when a focus session's planned
        duration has naturally elapsed with no distractions, and finalizes
        it as completed. Breaking on a distraction is handled immediately
        in _emit_switch instead, not here."""
        if self._focus_session is None or self._focus_finalized or self._focus_start_local is None:
            return
        elapsed = (datetime.now() - self._focus_start_local).total_seconds()
        planned = self._focus_session.get("planned_duration_seconds", 0)
        if elapsed >= planned:
            result = self.backend.end_focus_session(self._focus_session["id"])
            self._focus_finalized = True
            if result:
                self._focus_session = result
            if result and result.get("status") == "completed":
                minutes = planned // 60
                msg = f"FOCUS SESSION COMPLETE - {minutes} min with zero distractions!"
                self._last_alert_flash = msg
                if not self.use_ui:
                    print(f"\n*** {msg} ***\n", flush=True)
                self.notifier.notify(title="Focus session complete!",
                                      message=f"You stayed focused for {minutes} minutes.")
            else:
                # Edge case: a distraction slipped in right at the boundary
                # before this check ran - already handled by _emit_switch,
                # nothing further to do here.
                pass

    def _flash_distraction_alert(self) -> None:
        msg = (f"YOU ARE DISTRACTED - {self.distraction_switch_count} switches "
               f"between distracting apps (threshold: {self.distraction_threshold})")
        self._last_alert_flash = msg
        alert_record = {"alert": "distracted", "distraction_switch_count": self.distraction_switch_count}
        with self.switch_out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(alert_record) + "\n")
        if not self.use_ui:
            print(f"\n*** {msg} ***\n", flush=True)
        self.notifier.notify(
            title="You're distracted!",
            message=f"{self.distraction_switch_count} switches between distracting apps.",
        )

    # -- switching logic ---------------------------------------------------

    def _switch(self, new_name: Optional[str], page_title: Optional[str] = None,
                known_category: Optional[str] = None, process: str = "",
                ended_at: Optional[datetime] = None) -> None:
        """Moves tracking to new_name (None: no app in use). ended_at
        backdates the end of the session being left - to the last
        keyboard/mouse input when the user walked away."""
        now = datetime.now()

        if new_name is not None and self.categorizer.should_ignore(new_name, process):
            return

        if self._current is not None and self._current.name != new_name:
            self._previous_name = self._current.name
            self._current.end_dt = now if ended_at is None else min(now, max(self._current.start_dt, ended_at))
            if self._pending_lookup is not None:
                # Left before its category came back: log the switch into
                # it as neutral rather than lose it.
                self._pending_lookup = None
                self._log_switch_into_current()
            self._emit_session(self._current)
            self._current = None

        if new_name is not None and self._current is None:
            category = self._resolve_category(new_name, page_title, known_category)
            self._current = Session(name=new_name, start_dt=now,
                                    category="neutral" if category == PENDING else category)
            # Back on the same app after being away isn't a switch.
            self._switch_from = self._previous_name if self._previous_name != new_name else None
            if category == PENDING:
                self._pending_lookup = (new_name, page_title, known_category)
                self._push_live_status(now, force=True)
            else:
                self._category_known(now)

    def _log_switch_into_current(self) -> None:
        if self._switch_from is not None and self._current is not None:
            self._emit_switch(self._switch_from, self._current.name, self._current.category)
        self._switch_from = None

    def _category_known(self, now: datetime) -> None:
        """Runs once the current app's category is settled - straight away
        for known apps, a moment later for an online lookup."""
        self._log_switch_into_current()
        self._push_live_status(now, force=True)

        # Feature 6: track a continuous "productive" stretch across
        # multiple app switches (VS Code -> Notion -> VS Code all
        # count as one unbroken stretch); anything else resets it.
        if self._current.category == "productive":
            if self._productive_streak_start is None:
                self._productive_streak_start = now
        else:
            self._productive_streak_start = None
            self._break_reminder_shown = False

    def _check_pending_category(self) -> None:
        """Every tick: picks up an online classification once it lands."""
        if self._current is None or self._pending_lookup is None:
            return
        category = self._resolve_category(*self._pending_lookup)
        if category == PENDING:
            return
        self._pending_lookup = None
        self._current.category = category
        self._category_known(datetime.now())

    def _push_live_status(self, now: datetime, force: bool = False) -> None:
        """Feature 7 (novelty): keeps the backend's "what am I looking at
        right now" reading fresh so the web dashboard's Focus Mode page
        can show it live, alongside whatever the browser extension is
        pushing for tabs. Throttled to roughly every 10s during the main
        loop (which can poll every 1s by default) - force=True bypasses
        the throttle for an instant update right when the app changes."""
        if self._current is None:
            return
        if not force and self._last_live_status_push is not None:
            if (now - self._last_live_status_push).total_seconds() < 10:
                return
        self.backend.post_live_status(self._current.name, self._current.category)
        self._last_live_status_push = now

    def _sync_with_backend(self) -> None:
        """Every BACKEND_SYNC_SECONDS: follow the dashboard's signed-in
        account, learn which browsers the extension is covering, and react
        to Focus Mode sessions started from the dashboard or extension -
        not only ones this tracker started with --focus."""
        now = datetime.now()
        if self._last_backend_sync is not None and (now - self._last_backend_sync).total_seconds() < BACKEND_SYNC_SECONDS:
            return
        self._last_backend_sync = now
        was_enabled = self.backend.enabled
        self.backend.refresh_link()
        if self.backend.enabled and not was_enabled:
            self._streak_info = self.backend.get_streaks(threshold=self.distraction_threshold)
            self._leaderboard_info = self.backend.get_leaderboard(days=7)
        browsers = self.backend.get_extension_browsers()
        if browsers is not None:
            self._extension_browsers = browsers
        self._check_shared_focus_session()

    def _check_shared_focus_session(self) -> None:
        """Mirrors the extension's focus nag for desktop apps: while a
        Focus Mode session is running and you're on a distracting app,
        warn before its grace period runs out, and say when it ends."""
        if self._focus_session is not None and not self._focus_finalized:
            return  # this tracker's own --focus session handles itself
        session = self.backend.get_active_focus_session()
        if session is None:
            self._watched_focus_id = self._watched_focus_status = None
            return
        ended = (session["id"] == self._watched_focus_id and self._watched_focus_status == "active"
                 and session["status"] != "active")
        self._watched_focus_id, self._watched_focus_status = session["id"], session["status"]
        if ended and not self._extension_browsers:  # the extension announces it otherwise
            if session["status"] == "broken":
                self.notifier.notify(title="Focus session ended",
                                      message="Too much time on a distraction - the session broke.")
            else:
                self.notifier.notify(title="Focus session complete!", message="Nice work - you stayed focused.")
            return
        if session["status"] != "active" or session.get("on_break"):
            return
        if self._current is not None and self._current.category == "distraction":
            remaining = int(session.get("grace_seconds_remaining") or 0)
            if remaining > 0:
                self.notifier.notify(
                    title="Get back to focus!",
                    message=f"'{self._current.name}' is a distraction during your focus session. "
                            f"Switch back or it ends in {remaining}s.",
                )

    def _check_break_reminder(self) -> None:
        """Feature 6: suggests a short break after a long unbroken
        productive stretch. Framed around sustaining focus / avoiding
        burnout, not as a punishment - deliberately a different tone
        and color from the distraction alert."""
        if self.break_reminder_minutes <= 0:
            return
        if self._productive_streak_start is None or self._break_reminder_shown:
            return
        elapsed = (datetime.now() - self._productive_streak_start).total_seconds()
        if elapsed >= self.break_reminder_minutes * 60:
            minutes = int(elapsed // 60)
            msg = f"You've been focused for {minutes} min - a short break helps you sustain this."
            self._break_reminder_flash = msg
            if not self.use_ui:
                print(f"\n{msg}\n", flush=True)
            self.notifier.notify(title="Time for a quick break?", message=msg)
            self._break_reminder_shown = True

    def _check_stay_alert(self) -> None:
        """Separate from the switch-count alert: fires once if you stay
        on a single switched-to app for alert_after seconds or more."""
        if self._current is None or self._current.alerted:
            return
        elapsed = (datetime.now() - self._current.start_dt).total_seconds()
        if elapsed >= self.alert_after:
            self._last_alert_flash = (
                f"Stayed on '{self._current.name}' for {int(elapsed)}s"
            )
            if not self.use_ui:
                print(f"Distracted! You've been on '{self._current.name}' for {int(elapsed)}s.", flush=True)
            if self._current.category == "distraction":
                self.notifier.notify(
                    title="Still distracted?",
                    message=f"You've been on '{self._current.name}' for {int(elapsed)}s.",
                )
            self._current.alerted = True

    # -- rich UI -----------------------------------------------------------

    def _render(self):
        header_bits = []
        if self._current is not None:
            elapsed = int((datetime.now() - self._current.start_dt).total_seconds())
            header_bits.append(f"Active: [bold]{self._current.name}[/bold] "
                                f"({self._current.category}) - {elapsed}s")
        header_bits.append(f"Total switches: {self.total_switch_count}")
        header_bits.append(f"Distraction switches: {self.distraction_switch_count} "
                            f"(threshold: {self.distraction_threshold})")
        if self._streak_info is not None:
            streak = self._streak_info.get("current_streak", 0)
            longest = self._streak_info.get("longest_streak", 0)
            badges = self._streak_info.get("badges", [])
            streak_bit = f"Streak: {streak}d (best: {longest}d)"
            if badges:
                streak_bit += f" | Badges: {', '.join(badges)}"
            header_bits.append(streak_bit)
        if self._focus_session is not None:
            status = self._focus_session.get("status", "active")
            if status == "active" and self._focus_start_local is not None:
                remaining = max(0, self._focus_session.get("planned_duration_seconds", 0)
                                 - (datetime.now() - self._focus_start_local).total_seconds())
                header_bits.append(f"Focus Mode: {int(remaining // 60)}:{int(remaining % 60):02d} remaining")
            elif status == "completed":
                header_bits.append("Focus Mode: [bold green]COMPLETE[/bold green]")
            elif status == "broken":
                header_bits.append("Focus Mode: [bold red]BROKEN[/bold red]")
        header = Panel(" | ".join(header_bits), title="Window Tracker", border_style="cyan")

        table = Table(expand=True)
        table.add_column("From")
        table.add_column("To")
        table.add_column("Category")
        table.add_column("Total")
        table.add_column("Distraction")
        for row in self._rows:
            style = {
                "productive": "green",
                "distraction": "red",
                "neutral": "white",
            }.get(row["category"], "white")
            table.add_row(row["from"], row["to"], f"[{style}]{row['category']}[/{style}]",
                          str(row["total"]), str(row["distraction"]))

        pieces = [header, table]
        if self._leaderboard_info is not None:
            lb_table = Table(title=f"Leaderboard - {self._leaderboard_info['group_name']} "
                                    f"(last {self._leaderboard_info['days']}d)", expand=True)
            lb_table.add_column("Rank")
            lb_table.add_column("User")
            lb_table.add_column("Focus %")
            for entry in self._leaderboard_info["entries"][:5]:
                style = "bold green" if entry["rank"] == 1 else "white"
                lb_table.add_row(f"[{style}]#{entry['rank']}[/{style}]", entry["username"],
                                  f"{entry['focus_score']}%")
            pieces.append(lb_table)
        if self._break_reminder_flash:
            pieces.append(Panel(Text(self._break_reminder_flash, style="bold white on blue"),
                                 border_style="blue", title="Break suggestion"))
        if self._last_alert_flash:
            pieces.append(Panel(Text(self._last_alert_flash, style="bold white on red"),
                                 border_style="red"))
        return Group(*pieces)

    # -- main loop -----------------------------------------------------

    def _poll_window(self) -> None:
        try:
            window = get_active_window()
        except WindowBackendError as exc:
            print(f"[error] {exc}", file=sys.stderr)
            window = None
        except Exception as exc:  # a window closing mid-read must never stop the tracker
            print(f"[warn] Could not read the active window: {exc}", file=sys.stderr)
            window = None
        if window is None:
            self._switch(None)
            return
        client = browser_client(window.process)
        if client is not None and client in self._extension_browsers:
            # The extension is tracking this browser tab-by-tab
            # already - stepping aside keeps the minutes from being
            # counted twice (and its live status from being
            # overwritten with a vaguer window title).
            self._switch(None)
            return
        name, page_title, known = self._identify(window, client)
        idle = seconds_since_last_input() if self.idle_seconds > 0 else None
        watching = page_title is not None or known == "ambiguous"
        if idle is not None and idle >= self.idle_seconds and not watching:
            self._switch(None, ended_at=datetime.now() - timedelta(seconds=idle))
            return
        self._switch(name, page_title=page_title, known_category=known, process=window.process)

    def run(self) -> None:
        if not self.backend.enabled:
            print(
                "[info] Not connected to the backend - tracking locally only "
                "(this terminal + activity_log.jsonl/switch_log.jsonl). Nothing "
                "will show up on the web dashboard or in the extension's shared "
                "account/leaderboard/'Right now' card. To connect, set "
                "TRACKER_BACKEND_URL, TRACKER_USERNAME and TRACKER_PASSWORD to "
                "the SAME account you use on the web app before running this, "
                "or just use `python launch_focusguard.py` which prompts for "
                "them automatically.",
                file=sys.stderr,
            )

        # Feature 2: fetch streak/badge info once at startup (no-op if backend unavailable)
        self._streak_info = self.backend.get_streaks(threshold=self.distraction_threshold)
        if self._streak_info is not None:
            streak = self._streak_info.get("current_streak", 0)
            longest = self._streak_info.get("longest_streak", 0)
            badges = self._streak_info.get("badges", [])
            if not self.use_ui:
                print(f"Current streak: {streak} day(s) | Best: {longest} day(s)", flush=True)
                if badges:
                    print(f"Badges earned: {', '.join(badges)}", flush=True)

        # Feature 3: fetch this week's leaderboard once at startup, if the
        # user has joined a group (no-op otherwise).
        leaderboard = self.backend.get_leaderboard(days=7)
        self._leaderboard_info = leaderboard
        if leaderboard is not None and not self.use_ui:
            print(f"\nLeaderboard - {leaderboard['group_name']} (last {leaderboard['days']} days):")
            for entry in leaderboard["entries"][:5]:
                print(f"  #{entry['rank']} {entry['username']}: {entry['focus_score']}% focus")
            print()

        # Feature 4: start a focus session if requested, before entering the loop.
        if self.focus_minutes is not None:
            session = self.backend.start_focus_session(self.focus_minutes)
            if session is not None:
                self._focus_session = session
                self._focus_start_local = datetime.now()
                print(f"Focus Mode started - {self.focus_minutes} minute(s). "
                      f"Any distraction switch will break it.")
            else:
                print("[warn] Could not start focus session (backend unavailable or one's "
                      "already active) - tracking will continue without Focus Mode.", flush=True)

        if self.use_ui:
            self._live = Live(self._render(), console=self._console, refresh_per_second=4)
            self._live.start()
        else:
            print(f"Tracking active window every {self.interval}s")
            print(f"  session log -> {self.out_path}")
            print(f"  switch log  -> {self.switch_out_path}")
            print("Press Ctrl+C to stop.\n")

        try:
            while not self.stop_event.is_set():
                self._sync_with_backend()
                self._poll_window()
                self._check_pending_category()
                self._check_stay_alert()
                self._check_focus_mode()
                self._check_break_reminder()
                self._push_live_status(datetime.now())
                if self.use_ui and self._live is not None:
                    self._live.update(self._render())
                self.stop_event.wait(self.interval)
        except KeyboardInterrupt:
            pass
        finally:
            if self._current is not None:
                self._current.end_dt = datetime.now()
                self._emit_session(self._current)
            # Feature 4: exiting early while a focus session is still
            # active counts as quitting - finalize it as broken rather
            # than leaving it dangling as "active" forever.
            if self._focus_session is not None and not self._focus_finalized:
                self.backend.end_focus_session(self._focus_session["id"])
            if self.use_ui and self._live is not None:
                self._live.update(self._render())
                self._live.stop()
            self.backend.flush()  # online: deliver anything still queued before exiting
            print(f"\nStopped. Total switches: {self.total_switch_count}, "
                  f"distraction switches: {self.distraction_switch_count}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Track active window/tab sessions with productivity categorization.")
    parser.add_argument("--interval", type=float, default=1.0, help="Polling interval in seconds (default: 1.0)")
    parser.add_argument("--out", type=str, default="activity_log.jsonl", help="Session log file")
    parser.add_argument("--switch-out", type=str, default="switch_log.jsonl", help="Switch-event log file")
    parser.add_argument("--min-duration", type=float, default=0.0, help="Skip sessions shorter than this many seconds")
    parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG_PATH), help="Path to app_categories.json")
    parser.add_argument("--alert-after", type=float, default=10.0, help="Seconds on one app before the 'stayed too long' alert (default: 10)")
    parser.add_argument("--distraction-threshold", type=int, default=10, help="Distraction switch count above which the alert fires (default: 10)")
    parser.add_argument("--no-ui", action="store_true", help="Disable the rich live table; use plain text output")
    parser.add_argument("--no-llm", action="store_true", help="Disable Claude Haiku auto-classification for unrecognized apps")
    parser.add_argument("--create-group", type=str, default=None, metavar="NAME",
                         help="Create a new leaderboard group with this name, print the join code, and exit")
    parser.add_argument("--join-group", type=str, default=None, metavar="CODE",
                         help="Join an existing leaderboard group using a join code, then exit")
    parser.add_argument("--focus", type=int, default=None, metavar="MINUTES",
                         help="Start a Focus Mode commitment session for this many minutes - "
                              "any distraction-app switch during it breaks the session")
    parser.add_argument("--insights", action="store_true",
                         help="Print your AI-generated weekly insight report and exit")
    parser.add_argument("--force-insights", action="store_true",
                         help="Like --insights, but forces a fresh AI-generated report instead of using the cache")
    parser.add_argument("--break-reminder-minutes", type=int, default=None, metavar="MINUTES",
                         help="Suggest a break after this many minutes of unbroken productive time "
                              "(default: whatever's configured on your account profile, or 50 if "
                              "not connected to the backend; 0 disables this feature)")
    parser.add_argument("--idle-minutes", type=float, default=5.0, metavar="MINUTES",
                         help="Stop counting the current app after this many minutes without keyboard "
                              "or mouse input (default: 5; 0 disables; video/browser windows are exempt)")
    parser.add_argument("--background", action="store_true",
                         help="Run without a window (output goes to ~/.focusguard/tracker.log)")
    parser.add_argument("--install-startup", action="store_true",
                         help="Windows: start the tracker in the background whenever you sign in to Windows")
    parser.add_argument("--remove-startup", action="store_true",
                         help="Windows: stop starting the tracker with Windows")
    parser.add_argument("--stop", action="store_true", help="Stop a tracker that's running in the background")
    parser.add_argument("--sign-out", action="store_true",
                         help="Forget this computer's saved sign-in for the online FocusGuard")
    return parser.parse_args(argv)


def _acquire_single_instance_lock() -> Optional[socket.socket]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name == "nt":
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))
        sock.listen(4)
    except OSError:
        sock.close()
        return None
    return sock


def _serve_stop_requests(sock: socket.socket, stop_event: threading.Event) -> None:
    """The single-instance socket doubles as a stop button: `--stop` from
    another process connects and says "stop", and the tracker shuts down
    cleanly (saving its last session) instead of being killed."""
    while not stop_event.is_set():
        try:
            conn, _ = sock.accept()
        except OSError:
            return  # socket closed on exit
        with conn:
            try:
                conn.settimeout(2)
                if conn.recv(16).strip() == b"stop":
                    stop_event.set()
                    conn.sendall(b"ok")
            except OSError:
                pass


def _request_stop() -> Optional[bool]:
    """Asks a running tracker to stop. True if it agreed, False if one is
    running but didn't answer (an older version), None if none is running."""
    free = _acquire_single_instance_lock()
    if free is not None:
        # Checked first: Windows takes seconds to refuse a connection to
        # a closed local port, which would look like a tracker not answering.
        free.close()
        return None
    try:
        with socket.create_connection(("127.0.0.1", SINGLE_INSTANCE_PORT), timeout=3) as conn:
            conn.sendall(b"stop")
            return conn.recv(16).strip() == b"ok"
    except ConnectionRefusedError:
        return None
    except OSError:
        return False


def _wait_for_lock(seconds: float = 8.0) -> Optional[socket.socket]:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        lock = _acquire_single_instance_lock()
        if lock is not None:
            return lock
        time.sleep(0.3)
    return None


# -- Background mode & starting with Windows ---------------------------------

def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def stdin_is_console() -> bool:
    """Someone at a keyboard can answer questions. isatty() alone isn't
    enough on Windows: it's also true when input comes from NUL (as for
    a tracker the backend starts), where every question would get an
    instant empty answer."""
    try:
        if sys.stdin is None or not sys.stdin.isatty():
            return False
        if os.name != "nt":
            return True
        import ctypes
        import msvcrt
        mode = ctypes.c_uint()
        return bool(ctypes.windll.kernel32.GetConsoleMode(msvcrt.get_osfhandle(sys.stdin.fileno()),
                                                          ctypes.byref(mode)))
    except Exception:
        return False


def _load_prefs() -> dict:
    try:
        return json.loads(PREFS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_prefs(prefs: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        PREFS_FILE.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    except OSError:
        pass


def _go_background() -> None:
    """Hides this tracker's console window and sends its output to a log
    file, so it can run all day without a window to close by accident."""
    if os.name == "nt":
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
        except Exception:
            pass
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if BACKGROUND_LOG.exists() and BACKGROUND_LOG.stat().st_size > 2_000_000:
            BACKGROUND_LOG.unlink()  # keep the log from growing forever
        log = open(BACKGROUND_LOG, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
        print(f"\n--- FocusGuard tracker started {datetime.now():%Y-%m-%d %H:%M} ---")
    except OSError:
        if sys.stdout is None:  # pythonw has no console to print to
            sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _installed_exe() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return base / "Programs" / "FocusGuard" / "FocusGuard-Tracker.exe"


def _background_command() -> list[str]:
    """How to start this tracker in the background. The downloaded .exe
    is first copied to a fixed place, so moving or deleting the download
    doesn't break starting with Windows."""
    if _frozen():
        target = _installed_exe()
        if Path(sys.executable).resolve() != target.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(sys.executable, target)
        return [str(target), "--background"]
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return [str(pythonw if pythonw.is_file() else Path(sys.executable)), str(Path(__file__).resolve()), "--background"]


def startup_enabled() -> bool:
    if os.name != "nt":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            winreg.QueryValueEx(key, STARTUP_VALUE_NAME)
        return True
    except OSError:
        return False


def install_startup() -> list[str]:
    import winreg
    command = _background_command()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                        0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, STARTUP_VALUE_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(command))
    return command


def remove_startup() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, STARTUP_VALUE_NAME)
        return True
    except OSError:
        return False


def _start_in_background(command: list[str]) -> None:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)


def _ask_yes_no(question: str, default: bool) -> bool:
    try:
        answer = input(f"{question} [{'Y/n' if default else 'y/N'}] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False  # nobody answered: change nothing
    return default if not answer else answer.startswith("y")


def _pause_before_closing() -> None:
    """A double-clicked .exe's window closes the moment it exits - give
    people time to read what it said."""
    if _frozen() and stdin_is_console():
        try:
            input("\nPress Enter to close this window.")
        except (EOFError, KeyboardInterrupt):
            pass


def _offer_background_startup(backend: BackendClient) -> Optional[list[str]]:
    """First run of the downloaded tracker, once signed in: offer to keep
    tracking from now on without this window. Returns the command that
    starts the background copy if accepted (this one should then hand
    over and exit), else None."""
    if os.name != "nt" or not _frozen() or not backend.has_sign_in or startup_enabled():
        return None
    prefs = _load_prefs()
    if prefs.get("startup_asked"):
        return None
    print("\nFocusGuard can run quietly in the background and start with Windows, so your apps "
          "(Word, File Explorer, VS Code...) are always tracked - no window to keep open.")
    yes = _ask_yes_no("Start FocusGuard automatically with Windows?", default=True)
    prefs["startup_asked"] = True
    _save_prefs(prefs)
    if not yes:
        print("OK - tracking only while this window stays open. "
              "(Run with --install-startup to change your mind.)\n")
        return None
    try:
        command = install_startup()
    except OSError as exc:
        print(f"[warn] Couldn't set that up ({exc}) - tracking in this window instead.\n")
        return None
    print("Done - FocusGuard will start with Windows from now on.")
    return command


def main(argv=None) -> None:
    args = parse_args(argv)

    if args.stop:
        result = _request_stop()
        if result is None:
            print("No FocusGuard tracker is running.")
        elif result:
            print("Stopped the FocusGuard tracker.")
        else:
            print("A FocusGuard tracker is running but didn't respond - end 'FocusGuard-Tracker' "
                  "(or python) in Task Manager.")
        return

    if args.remove_startup or args.install_startup:
        if os.name != "nt":
            print("[error] Starting with the system is only set up automatically on Windows.", file=sys.stderr)
            sys.exit(1)
        if args.remove_startup:
            print("FocusGuard will no longer start with Windows." if remove_startup()
                  else "FocusGuard wasn't set to start with Windows.")
            return
        print(f"FocusGuard will start in the background with Windows: {subprocess.list2cmdline(install_startup())}")
        return

    if args.sign_out:
        forget_saved_session(DEFAULT_BACKEND_URL if not os.environ.get("TRACKER_BACKEND_URL")
                             else os.environ["TRACKER_BACKEND_URL"])
        print("Signed out - the tracker will ask you to sign in next time.")
        return

    if args.background:
        _go_background()
        args.no_ui = True
    if args.background or _frozen():
        # Started by Windows or from a download folder: keep the local
        # logs in one known place rather than wherever it was launched.
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if not Path(args.out).is_absolute():
            args.out = str(STATE_DIR / args.out)
        if not Path(args.switch_out).is_absolute():
            args.switch_out = str(STATE_DIR / args.switch_out)

    if not RICH_AVAILABLE and not args.no_ui:
        print("[info] 'rich' is not installed (pip install rich) - falling back to plain text output.", file=sys.stderr)

    # Group management is a one-off action, not a tracking session - handle
    # it and exit before starting the tracker loop.
    if args.create_group or args.join_group:
        backend = BackendClient()
        if not backend.enabled:
            print("[error] Backend not configured/reachable - set TRACKER_BACKEND_URL, "
                  "TRACKER_USERNAME, TRACKER_PASSWORD first.", file=sys.stderr)
            sys.exit(1)
        if args.create_group:
            group = backend.create_group(args.create_group)
            if group:
                print(f"Created group '{group['name']}' - join code: {group['join_code']}")
                print("Share this code with friends so they can join with --join-group")
            else:
                print("[error] Could not create group.", file=sys.stderr)
                sys.exit(1)
        if args.join_group:
            group = backend.join_group(args.join_group)
            if group:
                print(f"Joined group '{group['name']}'")
            else:
                print("[error] Could not join group - check the code is correct.", file=sys.stderr)
                sys.exit(1)
        return

    if args.insights or args.force_insights:
        backend = BackendClient()
        if not backend.enabled:
            print("[error] Backend not configured/reachable - set TRACKER_BACKEND_URL, "
                  "TRACKER_USERNAME, TRACKER_PASSWORD first.", file=sys.stderr)
            sys.exit(1)
        print("Generating your weekly insight report..." if args.force_insights else "Fetching your weekly insight report...")
        report = backend.get_insights(days=7, force=args.force_insights)
        if report is None:
            print("[error] Could not fetch insights.", file=sys.stderr)
            sys.exit(1)
        totals = report["category_totals_seconds"]
        print(f"\n=== Weekly Insight Report (last {report['days']} days"
              f"{' - cached' if report['cached'] else ''}) ===\n")
        print(f"Productive:   {totals['productive'] // 60} min")
        print(f"Distraction:  {totals['distraction'] // 60} min")
        print(f"Neutral:      {totals['neutral'] // 60} min")
        print(f"Sessions tracked: {report['session_count']}")
        print(f"Switches: {report['total_switch_count']} total, "
              f"{report['distraction_switch_count']} into distracting apps\n")
        print(report["insight_text"])
        print()
        return

    interactive = not args.background and stdin_is_console()
    instance_lock = _acquire_single_instance_lock()
    if instance_lock is None:
        if not (_frozen() and interactive):
            print("[info] A FocusGuard system tracker is already running - nothing to do.", file=sys.stderr)
            return
        print("FocusGuard is already running in the background and tracking your apps.")
        if not _ask_yes_no("Restart it with this copy (e.g. after downloading an update)?", default=False):
            _pause_before_closing()
            return
        stopped = _request_stop()
        instance_lock = _wait_for_lock() if stopped is not False else None
        if instance_lock is None:
            print("Couldn't stop the running tracker - end 'FocusGuard-Tracker' in Task Manager, then try again.")
            _pause_before_closing()
            return

    # One shared BackendClient for both the categorizer (crowdsourced
    # classification) and the tracker (session/switch/live-status sync) -
    # a single login, and app_name -> category lookups land in the same
    # backend the browser extension already reads/writes.
    backend = BackendClient(prompt_if_missing=interactive)
    if args.background and backend.online and not backend.has_sign_in:
        # Nobody can type a password into a hidden window.
        DesktopNotifier().notify(title="FocusGuard isn't signed in",
                                 message="Open FocusGuard Tracker and sign in to track your apps.")
        print("[info] Not signed in - exiting. Open the tracker normally once to sign in.", file=sys.stderr)
        return
    background_command = _offer_background_startup(backend) if interactive else None
    if background_command:
        instance_lock.close()  # hand the single-instance lock to the background copy
        _start_in_background(background_command)
        print("FocusGuard is now tracking in the background - you can close this window.\n"
              "To stop it: FocusGuard-Tracker.exe --stop   (--remove-startup: don't start with Windows)")
        _pause_before_closing()
        return
    stop_event = threading.Event()
    threading.Thread(target=_serve_stop_requests, args=(instance_lock, stop_event), daemon=True).start()
    llm = None if args.no_llm else LLMClassifier()
    categorizer = AppCategorizer(Path(args.config), llm_classifier=llm, backend=backend)

    # Feature 8: one shared break-interval preference across the tracker,
    # extension, and Focus Mode. Resolution order: explicit CLI flag >
    # the value saved on the account profile > hardcoded 50 (offline or
    # not logged in). Only fetched when the flag wasn't explicitly
    # passed, so an explicit --break-reminder-minutes always wins.
    break_reminder_minutes = args.break_reminder_minutes
    if break_reminder_minutes is None:
        profile = backend.get_profile()
        break_reminder_minutes = profile["break_interval_minutes"] if profile else 50
        print(f"[info] Break reminder set to {break_reminder_minutes} min "
              f"({'from your account profile' if profile else 'default - not connected to the backend'}).",
              file=sys.stderr)

    tracker = WindowTracker(
        out_path=Path(args.out),
        switch_out_path=Path(args.switch_out),
        interval=args.interval,
        min_duration=args.min_duration,
        categorizer=categorizer,
        alert_after=args.alert_after,
        distraction_threshold=args.distraction_threshold,
        use_ui=not args.no_ui,
        backend=backend,
        focus_minutes=args.focus,
        break_reminder_minutes=break_reminder_minutes,
        idle_minutes=args.idle_minutes,
        interactive=interactive,
        stop_event=stop_event,
    )
    tracker.run()


if __name__ == "__main__":
    main()
