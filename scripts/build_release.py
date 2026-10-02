"""
build_release.py

Builds the two downloads people need to use a deployed (online) FocusGuard:

  release/FocusGuard-extension.zip   Chrome extension, pointed at your server
  release/FocusGuard-Tracker.exe     Windows system tracker, pointed at your server

Usage (from the repo root, after deploying - see DEPLOY.md):
    python -m pip install pyinstaller
    python scripts/build_release.py --server https://your-app.onrender.com

Nothing in the repo itself changes: the extension and tracker in the source
tree keep talking to http://127.0.0.1:8000 for local use. The server address
is written only into the copies built here.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"
BUILD = ROOT / "build" / "release"
LOCAL_URL = "http://127.0.0.1:8000"


def build_extension(server: str) -> Path:
    src = ROOT / "extension-patch"
    out = BUILD / "extension"
    # Rebuilds overwrite in place, so a file still held open elsewhere
    # (e.g. a browser that loaded the last build) can't block a new build.
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(src, out, dirs_exist_ok=True)

    for name in ("background.js", "popup.js"):
        path = out / name
        path.write_text(path.read_text(encoding="utf-8").replace(LOCAL_URL, server), encoding="utf-8")

    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["host_permissions"] = [f"{server}/*"]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    leftover = [p.name for p in out.glob("*.js") if LOCAL_URL in p.read_text(encoding="utf-8")]
    if leftover:
        sys.exit(f"Local server address still present in: {leftover}")

    RELEASE.mkdir(exist_ok=True)
    zip_path = RELEASE / "FocusGuard-extension.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(out.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(out))
    return zip_path


def build_tracker(server: str) -> Path:
    BUILD.mkdir(parents=True, exist_ok=True)
    config = BUILD / "focusguard_server.json"
    config.write_text(json.dumps({"backend_url": server}), encoding="utf-8")

    sep = ";" if sys.platform == "win32" else ":"
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--console",
        "--name", "FocusGuard-Tracker",
        "--icon", str(ROOT / "logo.ico"),
        "--distpath", str(RELEASE),
        # Outside the repo: a synced folder (OneDrive, Dropbox) locks
        # PyInstaller's scratch files, and --clean then fails to delete them.
        "--workpath", str(Path(tempfile.gettempdir()) / "focusguard-pyinstaller"),
        "--specpath", str(BUILD),
        "--add-data", f"{ROOT / 'app_categories.json'}{sep}.",
        "--add-data", f"{ROOT / 'logo.ico'}{sep}.",
        "--add-data", f"{config}{sep}.",
        "--hidden-import", "plyer.platforms.win.notification",
        str(ROOT / "window_tracker.py"),
    ]
    subprocess.run(cmd, check=True, cwd=ROOT)
    return RELEASE / ("FocusGuard-Tracker.exe" if sys.platform == "win32" else "FocusGuard-Tracker")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", required=True, help="Your deployed site, e.g. https://your-app.onrender.com")
    parser.add_argument("--skip-tracker", action="store_true", help="Only build the extension zip")
    args = parser.parse_args()

    server = args.server.rstrip("/")
    if not re.match(r"^https://[^/\s]+$", server):
        sys.exit("--server must be an https:// address with no path, e.g. https://your-app.onrender.com")

    print("Building extension...")
    print(f"  -> {build_extension(server)}")
    if not args.skip_tracker:
        print("Building tracker (PyInstaller)...")
        print(f"  -> {build_tracker(server)}")
    print("Done. Attach the files in release/ to a GitHub Release (see DEPLOY.md).")


if __name__ == "__main__":
    main()
