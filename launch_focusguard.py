"""
launch_focusguard.py

Single entry point that runs FocusGuard AI entirely on your own machine:
starts the backend (which now also serves the React dashboard's build
and the legacy app.html dashboard as static files, so there's one
server instead of three dev servers), starts window_tracker.py wired
to that same local backend, and opens the dashboard in your browser.
The tracker and the browser extension both sync under whichever account
you sign in with on the dashboard - no separate logins.
Nothing here talks to the internet - the only feature that ever does
is the optional weekly AI insight, which already degrades gracefully
when no LLM provider is reachable.

Usage:
    python launch_focusguard.py
    python launch_focusguard.py --no-tracker   # web app only, skip the system tracker
    python launch_focusguard.py --no-build      # skip the one-time frontend build check
"""

import argparse
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
REACT_DIR = ROOT / "frontend-react"
REACT_DIST = REACT_DIR / "dist"


def build_frontend_if_needed():
    if (REACT_DIST / "index.html").is_file():
        return
    print("[launch] No dashboard build found - building it now (first run only)...")
    npm = "npm.cmd" if os.name == "nt" else "npm"
    subprocess.run([npm, "install"], cwd=REACT_DIR, check=True)
    subprocess.run([npm, "run", "build"], cwd=REACT_DIR, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-tracker", action="store_true", help="Don't launch window_tracker.py")
    parser.add_argument("--no-build", action="store_true", help="Don't check/build the React dashboard")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if not args.no_build:
        build_frontend_if_needed()

    backend_url = f"http://127.0.0.1:{args.port}"
    procs = []

    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--app-dir", str(BACKEND_DIR), "--port", str(args.port)],
        cwd=ROOT,
    )
    procs.append(backend_proc)

    if not args.no_tracker:
        # No login prompt: the tracker follows whichever account is signed
        # in on the dashboard (or the extension popup), picking it up from
        # the backend as soon as you sign in. TRACKER_USERNAME/PASSWORD in
        # the environment still pin it to a specific account if set.
        tracker_env = dict(os.environ)
        tracker_env["TRACKER_BACKEND_URL"] = backend_url
        tracker_env["TRACKER_AUTO_LINK"] = "1"
        # Opens its own console window on Windows so the tracker's live
        # rich UI has a terminal to draw in, separate from this launcher's.
        creationflags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
        tracker_proc = subprocess.Popen(
            [sys.executable, str(ROOT / "window_tracker.py")],
            cwd=ROOT, env=tracker_env, creationflags=creationflags,
        )
        procs.append(tracker_proc)

    time.sleep(2)
    webbrowser.open(backend_url)

    print(f"[launch] FocusGuard AI is running locally at {backend_url}")
    print("[launch] Press Ctrl+C here to stop everything.")
    try:
        backend_proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()


if __name__ == "__main__":
    main()
