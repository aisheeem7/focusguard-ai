"""
backend_client.py

Lives alongside window_tracker.py (Module 1). Sends session/switch
records to the backend API (Module 2) over HTTP. If the backend is
unreachable (not running, network down, wrong URL), calls fail silently
after one warning - the tracker keeps working and keeps writing its
local JSONL files as before, so nothing is lost either way.

Setup:
    pip install requests
    Set these environment variables (or edit the defaults below):
        TRACKER_BACKEND_URL   e.g. http://localhost:8000
        TRACKER_USERNAME
        TRACKER_PASSWORD

On first run with a given username, this registers automatically; on
later runs it logs in. The resulting API token is kept in memory only
for the life of the process (not written to disk).
"""

from __future__ import annotations

import getpass
import json
import os
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Same default every other surface (the extension, api.js, the web app)
# already hardcodes for local dev - previously this defaulted to "" (no
# URL at all), so backend sync silently stayed off unless someone set
# TRACKER_BACKEND_URL themselves. Matching the others removes a whole
# category of "why isn't my tracker showing up anywhere" confusion.
LOCAL_BACKEND_URL = "http://127.0.0.1:8000"
SERVER_CONFIG_NAME = "focusguard_server.json"
# Where an online tracker remembers its sign-in between launches.
SESSION_FILE = Path.home() / ".focusguard" / "tracker_session.json"


def _bundled_backend_url() -> Optional[str]:
    """The server address baked into the downloadable tracker by
    scripts/build_release.py (focusguard_server.json, next to the .exe or
    inside it). Absent when running from source, which keeps the local
    default."""
    here = Path(__file__).resolve().parent
    folders = [Path(getattr(sys, "_MEIPASS", here)), here]
    if getattr(sys, "frozen", False):
        folders.insert(0, Path(sys.executable).resolve().parent)
    for folder in folders:
        try:
            url = json.loads((folder / SERVER_CONFIG_NAME).read_text(encoding="utf-8")).get("backend_url")
        except (OSError, ValueError):
            continue
        if url:
            return url
    return None


DEFAULT_BACKEND_URL = _bundled_backend_url() or LOCAL_BACKEND_URL


def _is_local_url(url: str) -> bool:
    return (urlparse(url).hostname or "") in ("127.0.0.1", "localhost", "::1")


class BackendClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = 2.0,
        prompt_if_missing: bool = True,
    ):
        self.base_url = (base_url or os.environ.get("TRACKER_BACKEND_URL", DEFAULT_BACKEND_URL)).rstrip("/")
        self.username = username or os.environ.get("TRACKER_USERNAME")
        self.password = password or os.environ.get("TRACKER_PASSWORD")
        self.timeout = timeout

        self.user_id: Optional[int] = None
        self._token: Optional[str] = None
        self._warned = False
        # Credentials given explicitly (env vars / prompt) pin this tracker
        # to that account; otherwise it follows whichever account is
        # signed in on the web dashboard via the backend's device link.
        self.uses_device_link = not (self.username and self.password)
        auto_link = os.environ.get("TRACKER_AUTO_LINK") == "1"

        if not REQUESTS_AVAILABLE and self.base_url:
            print("[warn] 'requests' not installed (pip install requests) - "
                  "backend sync disabled, local logging still works.", file=sys.stderr)

        if self.uses_device_link:
            self.enabled = False
            online = not _is_local_url(self.base_url)
            if REQUESTS_AVAILABLE and self.base_url and not online and self.link_from_backend():
                return
            # Online there's no dashboard on this machine to follow - reuse
            # the sign-in saved the last time you logged in here instead.
            if REQUESTS_AVAILABLE and online and self._load_saved_session():
                self.uses_device_link = False
                return
            # Previously, running window_tracker.py directly (not through
            # launch_focusguard.py) meant tracking stayed local-only with a
            # one-line warning easy to miss. With no dashboard sign-in to
            # follow yet, a real terminal still gets asked; a background or
            # launcher-started tracker never blocks on a prompt - it just
            # keeps checking for a sign-in (see refresh_link).
            if prompt_if_missing and not auto_link and sys.stdin.isatty():
                self._prompt_for_credentials()
                self.uses_device_link = not (self.username and self.password)
            if self.uses_device_link and online:
                # Signing in on a website can't reach this machine - only
                # the tracker's own login can.
                print("[info] Not signed in - tracking locally only. Restart the tracker to sign in "
                      "with your FocusGuard account.", file=sys.stderr)
                return
            if self.uses_device_link:
                print("[info] Waiting for you to sign in on the FocusGuard dashboard - tracking "
                      "locally until then, and syncing automatically once you do.", file=sys.stderr)
                return

        self.enabled = bool(self.base_url and self.username and self.password and REQUESTS_AVAILABLE)
        if self.enabled:
            self._authenticate()

    def link_from_backend(self) -> bool:
        """Adopts the account signed in on this machine's dashboard (GET
        /device-link, which only answers local processes). Returns True
        if linked. Also how the backend knows a tracker is already
        running, so it doesn't start a second one."""
        try:
            r = requests.get(f"{self.base_url}/device-link",
                             headers={"X-FocusGuard-Client": "tracker"}, timeout=self.timeout)
        except Exception:
            return False  # backend offline - keep whatever we had
        if r.status_code != 200:
            if self._token is not None:
                print("[info] Signed out on the dashboard - tracking locally until you sign in again.",
                      file=sys.stderr)
            self._token = None
            self.user_id = None
            self.enabled = False
            return False
        data = r.json()
        if data["api_token"] != self._token or not self.enabled:
            switched = self._token is not None and data["user_id"] != self.user_id
            self._token = data["api_token"]
            self.user_id = data["user_id"]
            self.username = data["username"]
            self.enabled = True
            self._warned = False
            print(f"[info] {'Switched to' if switched else 'Connected as'} '{self.username}' "
                  f"(signed in on the dashboard) - activity syncs to {self.base_url}.", file=sys.stderr)
        return True

    def refresh_link(self) -> None:
        """Called periodically by the tracker: follows dashboard sign-ins,
        sign-outs and account switches, and reconnects after the backend
        restarts (a failed post disables syncing until then)."""
        if not REQUESTS_AVAILABLE or not self.base_url:
            return
        if self.uses_device_link:
            if _is_local_url(self.base_url):
                self.link_from_backend()
        elif not self.enabled and self.username and self.password:
            self._warned = True  # don't repeat the "disabled" warning on every retry
            self.enabled = True
            self._authenticate()
        elif not self.enabled and self._token:
            self._warned = True  # saved sign-in: just retry once the server is back
            self.enabled = True

    def _load_saved_session(self) -> bool:
        try:
            saved = json.loads(SESSION_FILE.read_text(encoding="utf-8")).get(self.base_url)
        except (OSError, ValueError):
            return False
        if not saved:
            return False
        try:
            r = requests.get(f"{self.base_url}/users/me",
                             headers={"Authorization": f"Bearer {saved['token']}"}, timeout=max(self.timeout, 10.0))
        except Exception:
            r = None  # server asleep or offline - keep the sign-in and retry later
        if r is not None and r.status_code == 401:
            self._forget_saved_session()
            return False
        self._token, self.user_id, self.username = saved["token"], saved["user_id"], saved["username"]
        self.enabled = r is not None and r.ok
        print(f"[info] Signed in as '{self.username}' - activity syncs to {self.base_url}.", file=sys.stderr)
        return True

    def _save_session(self) -> None:
        try:
            sessions = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            sessions = {}
        sessions[self.base_url] = {"token": self._token, "user_id": self.user_id, "username": self.username}
        try:
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            SESSION_FILE.write_text(json.dumps(sessions, indent=2), encoding="utf-8")
        except OSError:
            pass  # just means logging in again next launch

    def _forget_saved_session(self) -> None:
        try:
            sessions = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            sessions.pop(self.base_url, None)
            SESSION_FILE.write_text(json.dumps(sessions, indent=2), encoding="utf-8")
        except (OSError, ValueError):
            pass

    def _prompt_for_credentials(self) -> None:
        print(f"[info] Not connected to the backend ({self.base_url}). Log in with the SAME "
              "account you use on the web app/extension so this tracker's activity shows up "
              "there too - or press Enter to skip and track locally only.", file=sys.stderr)
        try:
            username = input("Username (blank to skip): ").strip()
            if not username:
                return
            password = getpass.getpass("Password: ")
            if not password:
                return
            self.username = username
            self.password = password
        except (EOFError, KeyboardInterrupt):
            print("\n[info] Skipping backend login - tracking locally only.", file=sys.stderr)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    def _authenticate(self) -> None:
        try:
            r = requests.post(
                f"{self.base_url}/users/login",
                json={"username": self.username, "password": self.password},
                timeout=self.timeout,
            )
            if r.status_code == 401:
                # not registered yet - register, then we're logged in
                r = requests.post(
                    f"{self.base_url}/users/register",
                    json={"username": self.username, "password": self.password},
                    timeout=self.timeout,
                )
            r.raise_for_status()
            data = r.json()
            self._token = data["api_token"]
            self.user_id = data["user_id"]
            if not _is_local_url(self.base_url):
                self._save_session()  # online: no need to type the password next launch
            # Previously silent on success - the only way to tell whether
            # you were actually connected was to check the web dashboard
            # afterward. Printing this immediately means a wrong
            # password/typo'd username is obvious right away instead of
            # discovered later as "why isn't anything showing up".
            print(f"[info] Connected to the backend as '{self.username}' (user #{self.user_id}) - "
                  f"activity will sync to {self.base_url}.", file=sys.stderr)
        except Exception as exc:
            self._disable(f"could not reach backend at {self.base_url}: {exc}")

    def _disable(self, reason: str) -> None:
        self.enabled = False
        if not self._warned:
            print(f"[warn] Backend sync disabled ({reason}). "
                  f"Local JSONL logging continues normally.", file=sys.stderr)
            self._warned = True

    def post_session(self, record: dict) -> None:
        if not self.enabled:
            return
        try:
            r = requests.post(f"{self.base_url}/sessions", json=record,
                               headers=self._headers(), timeout=self.timeout)
            r.raise_for_status()
        except Exception as exc:
            self._disable(f"session post failed: {exc}")

    def post_switch(self, record: dict) -> None:
        if not self.enabled:
            return
        try:
            r = requests.post(f"{self.base_url}/switches", json=record,
                               headers=self._headers(), timeout=self.timeout)
            r.raise_for_status()
        except Exception as exc:
            self._disable(f"switch post failed: {exc}")

    def post_live_status(self, name: str, category: str) -> None:
        """Feature 7 (novelty): pushes "here's what I'm looking at right
        now" so the web dashboard's Focus Mode page can show a live
        current-app card, alongside whatever the browser extension is
        pushing for tabs. Best-effort like post_session/post_switch."""
        if not self.enabled:
            return
        try:
            r = requests.put(
                f"{self.base_url}/live-status",
                json={"source": "system", "name": name, "category": category},
                headers=self._headers(), timeout=self.timeout,
            )
            r.raise_for_status()
        except Exception as exc:
            self._disable(f"live-status post failed: {exc}")

    def classify(self, app_name: str) -> Optional[str]:
        """Feature 6 (novelty), extended to system apps: asks the backend's
        crowdsourced classifier - the SAME group/global cache the browser
        extension's domain lookups already share - what category an app
        belongs in, rather than window_tracker.py spending its own
        separate (and previously Anthropic-only, so silently disabled
        without a local ANTHROPIC_API_KEY) LLM call per app. Returns one
        of "productive"/"distraction"/"neutral" (window_tracker.py's own
        vocabulary), or None if the backend is unavailable/unreachable -
        callers should fall back to their own local classifier in that
        case, never raise."""
        if not self.enabled:
            return None
        try:
            # A cold lookup can chain through several LLM providers
            # server-side (including Gemini's retry-with-backoff on
            # transient 503s - see backend/main.py's _try_gemini), which
            # can comfortably exceed 10s combined - matches get_insights'
            # more generous timeout below for the same reason.
            r = requests.post(
                f"{self.base_url}/classify-domain", json={"domain": app_name},
                headers=self._headers(), timeout=max(self.timeout, 20.0),
            )
            r.raise_for_status()
            data = r.json()
            # Backend speaks the extension's vocabulary (educational /
            # non_educational / unknown) since that's its original use
            # case - map back to window_tracker.py's own.
            mapped = {"educational": "productive", "non_educational": "distraction", "unknown": "neutral"}
            return mapped.get(data.get("category"), "neutral")
        except Exception as exc:
            print(f"[warn] classify failed for '{app_name}': {exc}", file=sys.stderr)
            return None

    def get_streaks(self, threshold: int = 10) -> Optional[dict]:
        """Feature 2: fetch current/longest streak and earned badges.
        Returns None if the backend is unavailable - never raises."""
        if not self.enabled or self.user_id is None:
            return None
        try:
            r = requests.get(
                f"{self.base_url}/streaks/{self.user_id}",
                params={"threshold": threshold},
                headers=self._headers(), timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            self._disable(f"streaks fetch failed: {exc}")
            return None

    def get_leaderboard(self, days: int = 7) -> Optional[dict]:
        """Feature 3: fetch the leaderboard for the user's current group.
        Returns None if unavailable, the user hasn't joined a group yet,
        or the backend is unreachable - never raises."""
        if not self.enabled:
            return None
        try:
            r = requests.get(
                f"{self.base_url}/leaderboard", params={"days": days},
                headers=self._headers(), timeout=self.timeout,
            )
            if r.status_code == 400:
                return None  # no group joined yet - not an error worth disabling over
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            self._disable(f"leaderboard fetch failed: {exc}")
            return None

    def create_group(self, name: str) -> Optional[dict]:
        if not self.enabled:
            return None
        try:
            r = requests.post(f"{self.base_url}/groups", json={"name": name},
                               headers=self._headers(), timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            print(f"[warn] create_group failed: {exc}", file=sys.stderr)
            return None

    def join_group(self, join_code: str) -> Optional[dict]:
        if not self.enabled:
            return None
        try:
            r = requests.post(f"{self.base_url}/groups/join", json={"join_code": join_code},
                               headers=self._headers(), timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            print(f"[warn] join_group failed: {exc}", file=sys.stderr)
            return None

    def start_focus_session(self, duration_minutes: int) -> Optional[dict]:
        """Feature 4: start a timed commitment session."""
        if not self.enabled:
            return None
        try:
            r = requests.post(f"{self.base_url}/focus-sessions/start",
                               json={"duration_minutes": duration_minutes},
                               headers=self._headers(), timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            print(f"[warn] start_focus_session failed: {exc}", file=sys.stderr)
            return None

    def end_focus_session(self, session_id: int) -> Optional[dict]:
        """Feature 4: end a focus session (naturally completed, broken by
        a distraction, or manually quit early - the backend decides which)."""
        if not self.enabled:
            return None
        try:
            r = requests.post(f"{self.base_url}/focus-sessions/{session_id}/end",
                               headers=self._headers(), timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            print(f"[warn] end_focus_session failed: {exc}", file=sys.stderr)
            return None

    def get_profile(self) -> Optional[dict]:
        """Feature 8: fetches this user's saved preferences (currently
        just break_interval_minutes) so window_tracker.py can use the
        SAME break-reminder interval configured on the web dashboard,
        instead of its own separate hardcoded default. Best-effort like
        classify()/get_insights() - never raises, just returns None."""
        if not self.enabled:
            return None
        try:
            r = requests.get(f"{self.base_url}/users/me", headers=self._headers(), timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            print(f"[warn] get_profile failed: {exc}", file=sys.stderr)
            return None

    def get_insights(self, days: int = 7, force: bool = False) -> Optional[dict]:
        """Feature 5: fetch the AI-generated weekly insight, plus the raw
        stats it's based on. Uses a longer timeout since the first call
        of the day may involve a real LLM API call server-side."""
        if not self.enabled or self.user_id is None:
            return None
        try:
            r = requests.get(
                f"{self.base_url}/insights/{self.user_id}",
                params={"days": days, "force": force},
                headers=self._headers(), timeout=max(self.timeout, 15.0),
            )
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            print(f"[warn] get_insights failed: {exc}", file=sys.stderr)
            return None

    def get_extension_browsers(self) -> Optional[set]:
        """Browsers the extension is currently tracking for this account
        (chrome, msedge, ...) - the tracker leaves those browsers' windows
        to the extension so the same minutes aren't counted twice. None if
        the backend is unavailable."""
        if not self.enabled:
            return None
        try:
            r = requests.get(f"{self.base_url}/tracker/status", headers=self._headers(), timeout=self.timeout)
            r.raise_for_status()
            return set(r.json().get("extension_browsers", []))
        except Exception:
            return None

    def get_active_focus_session(self) -> Optional[dict]:
        """The account's running Focus Mode session (started from the
        dashboard, extension or tracker), or None. Never raises."""
        if not self.enabled:
            return None
        try:
            r = requests.get(f"{self.base_url}/focus-sessions/active", headers=self._headers(), timeout=self.timeout)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    def classify_title(self, title: str) -> Optional[str]:
        """Classifies a page/video/file title (a browser tab the extension
        isn't covering, a VLC file, a YouTube video) via the backend's
        keyword -> curated list -> LLM chain. Returns productive /
        distraction / neutral, or None if the backend is unavailable."""
        if not self.enabled or not title.strip():
            return None
        try:
            r = requests.post(
                f"{self.base_url}/classify-domain", json={"domain": "window", "title": title},
                headers=self._headers(), timeout=max(self.timeout, 20.0),
            )
            r.raise_for_status()
            mapped = {"educational": "productive", "non_educational": "distraction", "unknown": "neutral"}
            return mapped.get(r.json().get("category"), "neutral")
        except Exception as exc:
            print(f"[warn] classify_title failed for '{title}': {exc}", file=sys.stderr)
            return None
