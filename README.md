# FocusGuard AI

**AI-Powered Digital Attention Management System — Distraction Detection & Focus Enhancement**
Infosys Springboard Internship 2026 · Aishee Mukherjee

FocusGuard watches which apps and browser tabs you use, classifies each one as **productive**, **distracting** or **neutral**, and helps you build focus habits with Focus Mode, streaks, badges, a group leaderboard and AI-written weekly insights. Everything runs locally on your own computer.

---

## How it works

```
  Desktop apps                     Browser tabs
       │                                │
 window_tracker.py              Chrome extension
 (system tracker)               (extension-patch/)
       │                                │
       └──────────────┬─────────────────┘
                      ▼
         Backend — FastAPI + SQLite (backend/)
         stores activity, classifies, serves the dashboard
                      │
                      ▼
         Web dashboard — http://127.0.0.1:8000
         (installable as a desktop app)
```

| Part | Folder / file | Role |
|---|---|---|
| System tracker | `window_tracker.py` | Tracks the active desktop app or window |
| Browser extension | `extension-patch/` | Tracks the active browser tab |
| Backend | `backend/` | API, database, classification, AI insights; serves the website |
| Dashboard | `frontend/` (main dashboard) · `frontend-react/` (landing, sign-in, profile) | What you see in the browser |

**One sign-in for everything.** Signing in on the dashboard also connects the tracker and the extension to that account, with no separate logins. It also starts the tracker in the background if it isn't running.

---

## Quick start

**Requirements:** Python 3.11+, Node.js 20.19+, Google Chrome.

```bash
# 1. Install dependencies
python -m pip install -r requirements.txt -r backend/requirements.txt
#    plus, for your OS:  pip install pywin32 psutil plyer          (Windows)
#                        pip install pyobjc-framework-Cocoa psutil plyer   (macOS)

# 2. (Optional) AI keys for insights - create a .env file in this folder
#    GEMINI_API_KEY=...        (free at aistudio.google.com)
#    ANTHROPIC_API_KEY=...     CHEAPER_INFERENCE_API_KEY=...

# 3. Run everything
python launch_focusguard.py
```

This builds the dashboard on first run, starts the backend and the system tracker, and opens **http://127.0.0.1:8000**. Create an account and you're tracking.

**Browser extension:** open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and select the `extension-patch/` folder. It connects to your dashboard account automatically.

Launcher options: `--no-tracker` (website only), `--no-build` (skip the build check).

---

## Features

**Tracking & classification**
- Desktop apps and browser tabs, tracked live and stored in one place.
- Classification order: curated lists in `app_categories.json`, then title keywords ("lecture", "official music video"...), then AI.
- Mixed sites and apps like YouTube or VLC are judged by the video or file title.
- Browser time is never counted twice: where the extension runs, the tracker leaves that browser to it.

**Focus Mode**
- A timed session with a live countdown ring and an optional full-screen view.
- Up to 60 seconds of total time on distractions is allowed before the session breaks.
- Breaks pause the timer. Taking one before your break interval is up adds penalty time.

**Motivation**
- **Streaks:** consecutive days with few distracting switches.
- **Badges:** 15 achievements across Common, Rare and Epic tiers, each with a progress bar (for example *First Spark*, *Deep Diver*, *Zen Master*, *Centurion*, *Top of the Pack*).
- **Activity grid:** a GitHub-style view of the last 6 months on Overview.
- **Leaderboard:** create, join, leave or switch study groups; ranked by focus score.

**Insights & history**
- A weekly AI summary that names your top distraction and suggests a fix. If no AI provider is reachable, it's written locally from your stats, so it always appears.
- History page: a 7-day chart, top apps and tabs, your biggest distraction and your best day.

**Alerts** — desktop and browser notifications for distractions, Focus Mode warnings and break reminders.

**Experience**
- Dark and light themes, a collapsible sidebar.
- Five languages: English, Hindi, Bengali, Tamil, Marathi.
- Installable as a desktop app (PWA).

---

## Project structure

```
├── launch_focusguard.py     one command to run everything
├── window_tracker.py        system tracker
├── backend_client.py        tracker ↔ backend connection
├── notifier.py              desktop notifications
├── llm_classifier.py        tracker's direct AI fallback (when the backend is unreachable)
├── app_categories.json      productive / distraction / neutral app & site lists
├── reset_password.py        local password reset utility
├── backend/                 FastAPI app (main.py), models, schemas, auth, tests/
├── extension-patch/         Chrome extension (background.js, popup, manifest)
├── frontend/                main dashboard: app.html, js/, css/, locales/
└── frontend-react/          React landing / sign-in / profile + production build
```

`frontend/` is copied into `frontend-react/public/` so a single `npm run build` (inside `frontend-react/`) bundles the whole website.

---

## Tests

```bash
python -m pytest backend/tests -q
```

The 50 automated tests cover accounts, tracking data, classification, streaks, badges, groups and leaderboard, Focus Mode, insights, history and account linking.

---

## Notes

- **Local by design.** Data stays in `app.db` on your machine. Only the optional AI insights and classification contact an AI provider.
- **Backend must be running.** The tracker and extension need it to sync; without it, the tracker keeps a local log.
- **Translations** were machine-assisted and haven't been reviewed by native speakers.
