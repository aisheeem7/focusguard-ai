"""
main.py

Backend API (Module 2). Run with:
    uvicorn main:app --reload --port 8000

Interactive docs at http://localhost:8000/docs once running - this is
the contract the tracker and the browser extension both build against.
"""

from collections import defaultdict
from datetime import datetime, date as date_cls, timedelta
from pathlib import Path
from typing import Optional
import json
import os
import re
import subprocess
import sys
import secrets
import string
import time

from dotenv import load_dotenv

# Loads variables from a .env file (searched upward from this file's
# directory, so the repo-root .env is found regardless of the cwd
# uvicorn is launched from) into os.environ. Never overrides a variable
# that's already set in the real environment, so existing setups that
# export these vars manually (or via CI/deploy config) are unaffected.
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, Request, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import func, case
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database import Base, engine, get_db, DATABASE_URL
from models import User, SessionRecord, SwitchRecord, Group, FocusSession, WeeklyInsight, LearnedCategory, LiveStatus, DeviceLink
from schemas import (
    UserRegister, UserLogin, TokenResponse,
    UserProfileOut, UserProfileUpdate,
    SessionCreate, SessionOut,
    SwitchCreate, SwitchOut,
    AnalyticsResponse, CategoryTotals,
    DayStat, StreaksResponse,
    GroupCreate, GroupJoin, GroupOut, LeaderboardEntry, LeaderboardResponse,
    DomainClassifyRequest, DomainClassifyResponse,
    FocusSessionStart, FocusSessionOut, FocusBreakEndOut,
    LiveStatusUpdate, LiveStatusResponse,
    InsightsResponse,
    AppTimeEntry, DayCategoryTotal, HistoryResponse,
    DeviceLinkOut, ExtensionPing, TrackerStatusResponse,
    BadgeProgress, BadgesResponse,
)
from auth import hash_password, verify_password, generate_token, get_current_user

Base.metadata.create_all(bind=engine)

# create_all only creates missing tables, it never alters an existing one -
# so a pre-existing users table (from before avatar_url existed) needs a
# one-time ALTER TABLE, or every query touching that column 500s. Safe to
# run on every startup: it's a no-op once the column is there. SQLite-only
# (PRAGMA isn't portable) - fine since that's this project's only backend
# today; a future Postgres migration would use Alembic instead.
if DATABASE_URL.startswith("sqlite"):
    with engine.connect() as _conn:
        _existing_cols = {row[1] for row in _conn.exec_driver_sql("PRAGMA table_info(users)")}
        if "avatar_url" not in _existing_cols:
            _conn.exec_driver_sql("ALTER TABLE users ADD COLUMN avatar_url VARCHAR")
            _conn.commit()
        if "break_interval_minutes" not in _existing_cols:
            _conn.exec_driver_sql("ALTER TABLE users ADD COLUMN break_interval_minutes INTEGER NOT NULL DEFAULT 50")
            _conn.commit()
        _focus_cols = {row[1] for row in _conn.exec_driver_sql("PRAGMA table_info(focus_sessions)")}
        if "distraction_seconds_accumulated" not in _focus_cols:
            _conn.exec_driver_sql("ALTER TABLE focus_sessions ADD COLUMN distraction_seconds_accumulated INTEGER NOT NULL DEFAULT 0")
            _conn.exec_driver_sql("ALTER TABLE focus_sessions ADD COLUMN distraction_started_at DATETIME")
            _conn.commit()
        if "break_started_at" not in _focus_cols:
            _conn.exec_driver_sql("ALTER TABLE focus_sessions ADD COLUMN break_started_at DATETIME")
            _conn.exec_driver_sql("ALTER TABLE focus_sessions ADD COLUMN paused_seconds_accumulated INTEGER NOT NULL DEFAULT 0")
            _conn.exec_driver_sql("ALTER TABLE focus_sessions ADD COLUMN last_break_ended_at DATETIME")
            _conn.exec_driver_sql("ALTER TABLE focus_sessions ADD COLUMN break_is_penalized BOOLEAN")
            _conn.commit()
        _insight_cols = {row[1] for row in _conn.exec_driver_sql("PRAGMA table_info(weekly_insights)")}
        if "language" not in _insight_cols:
            _conn.exec_driver_sql("ALTER TABLE weekly_insights ADD COLUMN language VARCHAR NOT NULL DEFAULT 'en'")
            _conn.commit()
        if "is_fallback" not in _insight_cols:
            _conn.exec_driver_sql("ALTER TABLE weekly_insights ADD COLUMN is_fallback BOOLEAN NOT NULL DEFAULT 0")
            _conn.commit()

app = FastAPI(title="Distraction Tracker Backend", version="0.1.0")

# Where uploaded avatar images live on disk; served back out at /uploads/*.
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
AVATAR_DIR = os.path.join(UPLOAD_DIR, "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Lets one `uvicorn main:app` process serve the whole product - API plus
# both UI surfaces - so FocusGuard AI runs fully offline as a single
# local app instead of three separately-launched dev servers. Both dirs
# are optional (only present after `npm run build`), so nothing here
# breaks the API-only workflow tests and extension development rely on.
REPO_ROOT = Path(__file__).resolve().parent.parent
REACT_DIST_DIR = REPO_ROOT / "frontend-react" / "dist"
LEGACY_DASHBOARD_DIR = REPO_ROOT / "frontend"

if REACT_DIST_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=REACT_DIST_DIR / "assets"), name="react-assets")

if LEGACY_DASHBOARD_DIR.is_dir():
    app.mount("/css", StaticFiles(directory=LEGACY_DASHBOARD_DIR / "css"), name="dashboard-css")
    app.mount("/js", StaticFiles(directory=LEGACY_DASHBOARD_DIR / "js"), name="dashboard-js")
    # frontend/locales/ is the one shared translation source for both the
    # React app and the legacy dashboard - both fetch /locales/{lang}/... from
    # this same origin/mount rather than each keeping its own copy.
    if (LEGACY_DASHBOARD_DIR / "locales").is_dir():
        app.mount("/locales", StaticFiles(directory=LEGACY_DASHBOARD_DIR / "locales"), name="locales")

    @app.get("/app.html", include_in_schema=False)
    def serve_dashboard():
        return FileResponse(LEGACY_DASHBOARD_DIR / "app.html")

# Allows the frontend (served from a different local origin, e.g. a
# python -m http.server on a different port, or a file:// page) to call
# this API. Wildcard origin is safe here since auth uses a Bearer token
# in the Authorization header, not cookies (allow_credentials=False -
# browsers reject wildcard-origin + credentials together anyway).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# StaticFiles doesn't set Cache-Control, so browsers fall back to
# heuristic caching and can keep serving an old app.html/dashboard.css
# for a while after a real change - which looked exactly like "the
# dashboard doesn't match the new design" during dev, when the fix was
# actually already live server-side. /assets is exempt - those are
# Vite's content-hashed build filenames, so they're safe to cache hard.
@app.middleware("http")
async def no_cache_for_dev_static(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path in ("/", "/auth", "/profile", "/app.html") or path.startswith("/css/") or path.startswith("/js/"):
        response.headers["Cache-Control"] = "no-cache"
    # The service worker script and manifest must always be revalidated -
    # a browser-cached stale sw.js would delay update detection (workbox's
    # own update check relies on actually re-fetching this exact byte
    # content to notice a new build).
    if path in ("/sw.js", "/manifest.webmanifest"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# ---- Auth endpoints ----

@app.post("/users/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")
    user = User(
        username=payload.username,
        hashed_password=hash_password(payload.password),
        api_token=generate_token(),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two concurrent requests can both pass the "existing" check above
        # before either commits (e.g. the system tracker and the browser
        # extension both auto-registering the same username at once).
        # Rather than 500 on the loser of that race, treat it as if this
        # request had logged in instead - return the account that won.
        db.rollback()
        winner = db.query(User).filter(User.username == payload.username).first()
        if winner is None:
            raise  # genuinely unexpected - re-raise the original error
        return TokenResponse(user_id=winner.id, username=winner.username, api_token=winner.api_token)
    db.refresh(user)
    return TokenResponse(user_id=user.id, username=user.username, api_token=user.api_token)


@app.post("/users/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return TokenResponse(user_id=user.id, username=user.username, api_token=user.api_token)


# ---- Profile (Feature 7: username + avatar, used by the profile page) ----

@app.get("/users/me", response_model=UserProfileOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@app.patch("/users/me", response_model=UserProfileOut)
def update_me(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.username and payload.username != current_user.username:
        existing = db.query(User).filter(User.username == payload.username).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already taken")
        current_user.username = payload.username
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=400, detail="Username already taken")
        db.refresh(current_user)

    if payload.break_interval_minutes is not None:
        if not (5 <= payload.break_interval_minutes <= 240):
            raise HTTPException(status_code=400, detail="break_interval_minutes must be between 5 and 240")
        current_user.break_interval_minutes = payload.break_interval_minutes
        db.commit()
        db.refresh(current_user)

    return current_user


ALLOWED_AVATAR_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}
MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5MB


@app.post("/users/me/avatar", response_model=UserProfileOut)
async def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ext = ALLOWED_AVATAR_TYPES.get(file.content_type)
    if not ext:
        raise HTTPException(status_code=400, detail="Unsupported image type - use PNG, JPEG, WEBP, or GIF")
    contents = await file.read()
    if len(contents) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="Image too large - max 5MB")

    # Clear out any previous avatar file(s) for this user before writing the
    # new one - the filename includes a timestamp so browsers don't serve a
    # stale cached image after a re-upload.
    for existing_name in os.listdir(AVATAR_DIR):
        if existing_name.startswith(f"{current_user.id}_"):
            os.remove(os.path.join(AVATAR_DIR, existing_name))

    filename = f"{current_user.id}_{int(datetime.utcnow().timestamp())}.{ext}"
    with open(os.path.join(AVATAR_DIR, filename), "wb") as out_file:
        out_file.write(contents)

    current_user.avatar_url = f"/uploads/avatars/{filename}"
    db.commit()
    db.refresh(current_user)
    return current_user


# ---- Session records (Module 1 -> Module 2) ----

@app.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = SessionRecord(user_id=current_user.id, **payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# ---- Switch records ----

@app.post("/switches", response_model=SwitchOut, status_code=status.HTTP_201_CREATED)
def create_switch(
    payload: SwitchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = SwitchRecord(user_id=current_user.id, **payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# ---- Analytics (Module 3 reads from here) ----

@app.get("/analytics/{user_id}", response_model=AnalyticsResponse)
def get_analytics(
    user_id: int,
    date: Optional[str] = None,  # "YYYY-MM-DD"; omit for all-time
    source: Optional[str] = None,  # "system" | "extension"; omit to combine both
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot view another user's analytics")

    query = db.query(SessionRecord).filter(SessionRecord.user_id == user_id)
    if source:
        query = query.filter(SessionRecord.source == source)
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
        query = query.filter(
            SessionRecord.created_at >= datetime.combine(target_date, datetime.min.time()),
            SessionRecord.created_at < datetime.combine(target_date, datetime.max.time()),
        )
    sessions = query.all()

    totals = defaultdict(int)
    for s in sessions:
        totals[s.category] += s.duration

    switch_query = db.query(SwitchRecord).filter(SwitchRecord.user_id == user_id)
    if source:
        switch_query = switch_query.filter(SwitchRecord.source == source)
    # Computed server-side from actual rows, not trusted from the client's
    # self-reported counter - a client-reported "latest switch" value breaks
    # as soon as there's more than one counting source (system + extension)
    # or the tracker process simply restarts and its local counter resets.
    total_switch_count = switch_query.count()
    distraction_switch_count = switch_query.filter(SwitchRecord.category == "distraction").count()

    return AnalyticsResponse(
        user_id=user_id,
        date=date,
        category_totals_seconds=CategoryTotals(
            productive=totals.get("productive", 0),
            distraction=totals.get("distraction", 0),
            neutral=totals.get("neutral", 0),
        ),
        total_switch_count=total_switch_count,
        distraction_switch_count=distraction_switch_count,
        session_count=len(sessions),
    )


BADGE_THRESHOLDS = [
    (3, "3-Day Streak"),
    (7, "Week Warrior"),
    (14, "Two-Week Titan"),
    (30, "Month Master"),
]


def _compute_streaks(success_days: list[str]) -> tuple[int, int]:
    """success_days: sorted list of 'YYYY-MM-DD' strings that count as a
    success day. Returns (current_streak, longest_streak), both counted
    in consecutive CALENDAR days, not just consecutive tracked days -
    a gap in tracking breaks the streak."""
    if not success_days:
        return 0, 0

    longest = 1
    run = 1
    prev = date_cls.fromisoformat(success_days[0])
    for d_str in success_days[1:]:
        d = date_cls.fromisoformat(d_str)
        if (d - prev).days == 1:
            run += 1
        else:
            run = 1
        longest = max(longest, run)
        prev = d

    # Current streak: walk backward from the most recent success day,
    # counting consecutive calendar days.
    current = 1
    idx = len(success_days) - 1
    while idx > 0:
        d1 = date_cls.fromisoformat(success_days[idx])
        d0 = date_cls.fromisoformat(success_days[idx - 1])
        if (d1 - d0).days == 1:
            current += 1
            idx -= 1
        else:
            break

    # If the most recent success day isn't today or yesterday, the streak
    # has lapsed - it's history, not "current".
    last_day = date_cls.fromisoformat(success_days[-1])
    if (date_cls.today() - last_day).days > 1:
        current = 0

    return current, longest


@app.get("/streaks/{user_id}", response_model=StreaksResponse)
def get_streaks(
    user_id: int,
    threshold: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot view another user's streaks")

    switch_rows = (
        db.query(
            func.date(SwitchRecord.created_at).label("day"),
            func.count(SwitchRecord.id).label("total"),
            func.sum(case((SwitchRecord.category == "distraction", 1), else_=0)).label("distraction"),
        )
        .filter(SwitchRecord.user_id == user_id)
        .group_by(func.date(SwitchRecord.created_at))
        .all()
    )
    switch_map = {row.day: {"total": row.total, "distraction": row.distraction or 0} for row in switch_rows}

    session_rows = (
        db.query(
            func.date(SessionRecord.created_at).label("day"),
            SessionRecord.category,
            func.sum(SessionRecord.duration).label("seconds"),
        )
        .filter(SessionRecord.user_id == user_id)
        .group_by(func.date(SessionRecord.created_at), SessionRecord.category)
        .all()
    )
    session_map: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in session_rows:
        session_map[row.day][row.category] += row.seconds or 0

    all_days = sorted(set(switch_map.keys()) | set(session_map.keys()))

    days: list[DayStat] = []
    success_days: list[str] = []
    for d in all_days:
        sw = switch_map.get(d, {"total": 0, "distraction": 0})
        sess = session_map.get(d, {})
        is_success = sw["distraction"] <= threshold
        if is_success:
            success_days.append(d)
        days.append(DayStat(
            date=d,
            productive_seconds=sess.get("productive", 0),
            distraction_seconds=sess.get("distraction", 0),
            neutral_seconds=sess.get("neutral", 0),
            total_switches=sw["total"],
            distraction_switches=sw["distraction"],
            is_success=is_success,
        ))

    current_streak, longest_streak = _compute_streaks(success_days)
    badges = [name for days_needed, name in BADGE_THRESHOLDS if longest_streak >= days_needed]

    return StreaksResponse(
        user_id=user_id,
        current_streak=current_streak,
        longest_streak=longest_streak,
        threshold=threshold,
        badges=badges,
        days=days[-30:],  # cap payload size - last 30 tracked days
    )


# ---- Badges: achievement catalog ----
# A wider set of achievements than the four streak badges above (which
# stay as they are - the Streaks page and the tracker show them). Each
# entry: (id, tier, target, metric). Tier is 1 common / 2 rare / 3 epic,
# used only for the badge's colour. The frontend owns the display names
# and descriptions (translated), keyed by id.
BADGE_CATALOG = [
    ("first_spark", 1, 1, "focus_completed"),
    ("ember_keeper", 1, 3, "longest_streak"),
    ("flow_weaver", 2, 7, "longest_streak"),
    ("unbreakable", 3, 30, "longest_streak"),
    ("deep_diver", 2, 50, "longest_focus_minutes"),
    ("iron_will", 2, 1, "clean_focus_sessions"),
    ("pomodoro_pro", 2, 10, "focus_completed"),
    ("focus_titan", 3, 50, "focus_completed"),
    ("ten_hour_club", 1, 10, "productive_hours"),
    ("centurion", 3, 100, "productive_hours"),
    ("zen_master", 2, 1, "zen_days"),
    ("early_bird", 1, 1, "early_sessions"),
    ("night_owl", 1, 1, "night_sessions"),
    ("squad_up", 1, 1, "in_group"),
    ("top_of_pack", 3, 1, "group_leader"),
]
ZEN_DAY_MIN_PRODUCTIVE_SECONDS = 3600


def _badge_metrics(user: User, db: Session) -> dict:
    uid = user.id
    streaks = get_streaks(uid, threshold=10, db=db, current_user=user)

    focus_done = (
        db.query(FocusSession)
        .filter(FocusSession.user_id == uid, FocusSession.status == "completed")
        .all()
    )
    productive_seconds = (
        db.query(func.sum(SessionRecord.duration))
        .filter(SessionRecord.user_id == uid, SessionRecord.category == "productive")
        .scalar() or 0
    )

    # A "zen" day: an hour or more of productive time with not a single
    # switch into a distraction that day.
    productive_by_day = dict(
        db.query(func.date(SessionRecord.created_at), func.sum(SessionRecord.duration))
        .filter(SessionRecord.user_id == uid, SessionRecord.category == "productive")
        .group_by(func.date(SessionRecord.created_at))
        .all()
    )
    distraction_switches_by_day = dict(
        db.query(func.date(SwitchRecord.created_at), func.count(SwitchRecord.id))
        .filter(SwitchRecord.user_id == uid, SwitchRecord.category == "distraction")
        .group_by(func.date(SwitchRecord.created_at))
        .all()
    )
    zen_days = sum(
        1 for day, secs in productive_by_day.items()
        if (secs or 0) >= ZEN_DAY_MIN_PRODUCTIVE_SECONDS and not distraction_switches_by_day.get(day)
    )

    # start_time is the tracker's/extension's local "HH:MM", so these are
    # the user's own clock: early = 04:00-06:59, night = 22:00-02:59.
    productive_q = db.query(func.count(SessionRecord.id)).filter(
        SessionRecord.user_id == uid, SessionRecord.category == "productive")
    early = productive_q.filter(SessionRecord.start_time >= "04:00", SessionRecord.start_time < "07:00").scalar() or 0
    night = productive_q.filter(
        (SessionRecord.start_time >= "22:00") | (SessionRecord.start_time < "03:00")).scalar() or 0

    group_leader = 0
    if user.group_id is not None:
        entries = _compute_group_leaderboard(user.group_id, 7, db)
        if len(entries) >= 2 and entries[0]["user_id"] == uid and entries[0]["productive_seconds"] > 0:
            group_leader = 1

    return {
        "focus_completed": len(focus_done),
        "longest_focus_minutes": max((f.planned_duration_seconds // 60 for f in focus_done), default=0),
        "clean_focus_sessions": sum(1 for f in focus_done if not f.distraction_seconds_accumulated),
        "longest_streak": streaks.longest_streak,
        "productive_hours": int(productive_seconds // 3600),
        "zen_days": zen_days,
        "early_sessions": early,
        "night_sessions": night,
        "in_group": 1 if user.group_id is not None else 0,
        "group_leader": group_leader,
    }


@app.get("/badges/{user_id}", response_model=BadgesResponse)
def get_badges(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot view another user's badges")
    metrics = _badge_metrics(current_user, db)
    badges = [
        BadgeProgress(id=badge_id, tier=tier, target=target,
                      progress=min(metrics[metric], target), earned=metrics[metric] >= target)
        for badge_id, tier, target, metric in BADGE_CATALOG
    ]
    return BadgesResponse(user_id=user_id, earned_count=sum(b.earned for b in badges),
                          total=len(badges), badges=badges)


# ---- History (Feature 8) ----

def _compute_history_data(user_id: int, days: int, db: Session, top_apps_limit: int = 15) -> dict:
    """Real SQL GROUP BY over SessionRecord - not an approximation over a
    capped row window - so the numbers on the History page (and the AI
    insight prompt, which reuses this same function) are trustworthy."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    app_rows = (
        db.query(
            SessionRecord.name,
            SessionRecord.category,
            SessionRecord.source,
            func.sum(SessionRecord.duration).label("total_seconds"),
        )
        .filter(SessionRecord.user_id == user_id, SessionRecord.created_at >= cutoff)
        .group_by(SessionRecord.name, SessionRecord.category, SessionRecord.source)
        .order_by(func.sum(SessionRecord.duration).desc())
        .all()
    )
    top_apps = [
        AppTimeEntry(name=r.name, category=r.category, source=r.source, total_seconds=int(r.total_seconds or 0))
        for r in app_rows[:top_apps_limit]
    ]

    day_rows = (
        db.query(
            func.date(SessionRecord.created_at).label("day"),
            SessionRecord.category,
            func.sum(SessionRecord.duration).label("seconds"),
        )
        .filter(SessionRecord.user_id == user_id, SessionRecord.created_at >= cutoff)
        .group_by(func.date(SessionRecord.created_at), SessionRecord.category)
        .all()
    )
    by_day: dict = defaultdict(lambda: defaultdict(int))
    for r in day_rows:
        by_day[r.day][r.category] += int(r.seconds or 0)
    daily_totals = [
        DayCategoryTotal(
            date=d,
            productive_seconds=by_day[d].get("productive", 0),
            distraction_seconds=by_day[d].get("distraction", 0),
            neutral_seconds=by_day[d].get("neutral", 0),
        )
        for d in sorted(by_day.keys())
    ]

    # Merged by name alone, across sources - "biggest time sink" doesn't
    # care whether it was visited via the extension or the system tracker,
    # unlike top_apps above which keeps them distinct for transparency.
    distraction_by_name: dict = defaultdict(int)
    for r in app_rows:
        if r.category == "distraction":
            distraction_by_name[r.name] += int(r.total_seconds or 0)
    top_distraction_app = None
    if distraction_by_name:
        name, secs = max(distraction_by_name.items(), key=lambda kv: kv[1])
        top_distraction_app = AppTimeEntry(name=name, category="distraction", source="combined", total_seconds=secs)

    most_productive_day = None
    productive_days = [d for d in daily_totals if d.productive_seconds > 0]
    if productive_days:
        most_productive_day = max(productive_days, key=lambda d: d.productive_seconds)

    return {
        "top_apps": top_apps,
        "daily_totals": daily_totals,
        "top_distraction_app": top_distraction_app,
        "most_productive_day": most_productive_day,
    }


@app.get("/history/{user_id}", response_model=HistoryResponse)
def get_history(
    user_id: int,
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot view another user's history")
    data = _compute_history_data(user_id, days, db)
    return HistoryResponse(user_id=user_id, days=days, **data)


# ---- Groups & Leaderboard (Feature 3) ----

def _generate_join_code(db: Session, length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(20):  # extremely unlikely to ever loop more than once
        code = "".join(secrets.choice(alphabet) for _ in range(length))
        if not db.query(Group).filter(Group.join_code == code).first():
            return code
    raise HTTPException(status_code=500, detail="Could not generate a unique join code, try again")


@app.post("/groups", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: GroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    join_code = _generate_join_code(db)
    group = Group(name=payload.name, join_code=join_code)
    db.add(group)
    db.commit()
    db.refresh(group)
    # Creating a group also joins it, so you're never stuck with an empty leaderboard.
    current_user.group_id = group.id
    db.commit()
    return group


@app.post("/groups/join", response_model=GroupOut)
def join_group(
    payload: GroupJoin,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.join_code == payload.join_code.upper()).first()
    if group is None:
        raise HTTPException(status_code=404, detail="No group found with that join code")
    current_user.group_id = group.id
    db.commit()
    return group


@app.post("/groups/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_group(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Leaves the current group (the group itself stays for everyone
    else), so the user can create or join another one."""
    current_user.group_id = None
    db.commit()


@app.get("/groups/me", response_model=GroupOut)
def get_my_group(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.group_id is None:
        raise HTTPException(status_code=404, detail="You haven't joined or created a group yet")
    group = db.query(Group).filter(Group.id == current_user.group_id).first()
    return group


def _sessions_since(user_id: int, cutoff: datetime, db: Session, limit: int = 5000) -> list:
    """Fetches a user's sessions and filters by cutoff in Python rather
    than in the SQL query - see the identical fix and explanation on
    _count_distraction_switches_since below for why. Bounded to a
    generous row limit so this stays cheap even for long-running users."""
    rows = (
        db.query(SessionRecord)
        .filter(SessionRecord.user_id == user_id)
        .order_by(SessionRecord.id.desc())
        .limit(limit)
        .all()
    )
    return [r for r in rows if r.created_at >= cutoff]


def _switches_since(user_id: int, cutoff: datetime, db: Session, limit: int = 5000) -> list:
    rows = (
        db.query(SwitchRecord)
        .filter(SwitchRecord.user_id == user_id)
        .order_by(SwitchRecord.id.desc())
        .limit(limit)
        .all()
    )
    return [r for r in rows if r.created_at >= cutoff]


def _compute_group_leaderboard(group_id: int, days: int, db: Session) -> list[dict]:
    """Shared by /leaderboard and the Weekly Insight's group-standing
    commentary, so both always agree on the same ranking/scoring."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    members = db.query(User).filter(User.group_id == group_id).all()

    entries = []
    for member in members:
        sessions = _sessions_since(member.id, cutoff, db)
        totals_map: dict = defaultdict(int)
        for s in sessions:
            totals_map[s.category] += s.duration
        productive = totals_map.get("productive", 0)
        distraction = totals_map.get("distraction", 0)
        denom = productive + distraction
        # No tracked productive/distraction time yet -> score of 0, not
        # divide-by-zero and not an artificially "perfect" score.
        score = round((productive / denom) * 100, 1) if denom > 0 else 0.0
        entries.append({
            "user_id": member.id, "username": member.username,
            "productive_seconds": productive, "distraction_seconds": distraction,
            "focus_score": score,
        })

    # Rank by focus score descending; ties broken by more productive seconds.
    entries.sort(key=lambda e: (-e["focus_score"], -e["productive_seconds"]))
    for i, e in enumerate(entries):
        e["rank"] = i + 1
    return entries


@app.get("/leaderboard", response_model=LeaderboardResponse)
def get_leaderboard(
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.group_id is None:
        raise HTTPException(status_code=400, detail="Join or create a group first (POST /groups or /groups/join)")
    group = db.query(Group).filter(Group.id == current_user.group_id).first()

    entries = _compute_group_leaderboard(group.id, days, db)
    ranked = [LeaderboardEntry(**e) for e in entries]

    return LeaderboardResponse(group_id=group.id, group_name=group.name, days=days, entries=ranked)


# ---- Crowdsourced classification (Feature 6: novelty) ----
# The extension's background.js already had a RESOLVER_ENDPOINT pointing
# at POST /classify-domain (built for Yashwanth's now-unused standalone
# resolver-server) - this implements that same contract, but backed by
# the shared backend's LLM chain and a crowdsourced cache: the first
# classification of a given key is reused by every groupmate afterwards
# instead of spending another LLM call, with a cross-group fallback tier
# so the whole userbase teaches the classifier over time.

EXT_CATEGORY_MAP = {"productive": "educational", "distraction": "non_educational", "neutral": "unknown"}

# A handful of sites (YouTube above all) host both productive and
# distracting content under the exact same domain - "youtube.com" alone
# can't tell a coding tutorial from a music video apart. For these, the
# caller sends the page/video TITLE too (see DomainClassifyRequest), and
# classification runs against that text instead of the bare domain.
PRODUCTIVE_TITLE_KEYWORDS = [
    "tutorial", "lesson", "lecture", "course", "crash course", "one-shot", "oneshot",
    "how to", "how-to", "walkthrough", "explained", "documentation", "guide",
    "interview prep", "coding", "programming", "study with me", "revision",
    "exam prep", "masterclass", "deep dive", "full course",
    "class 10", "class 11", "class 12", "jee", "neet", "upsc", "gate exam", "board exam",
    "dsa", "data structures", "algorithms", "system design", "leetcode", "machine learning",
    "deep learning", "python", "javascript", "typescript", "java", "c++", "sql", "react",
    "physics", "chemistry", "mathematics", "maths", "calculus", "biology", "economics",
    "solved examples", "practice problems", "mock test", "notes", "syllabus", "research paper",
]
DISTRACTION_TITLE_KEYWORDS = [
    "music video", "official video", "behind the scenes", "bloopers", "vlog",
    "prank", "compilation", "funny moments", "meme", "highlights", "trailer",
    "reaction", "unboxing", "gameplay", "let's play", "lets play", "shorts",
    "tiktok compilation", "try not to laugh",
    "official audio", "lyric video", "lyrics", "full song", "web series", "full movie",
    "episode", "stand-up", "standup comedy", "roast", "memes", "funny", "reels",
    "gaming", "speedrun", "celebrity", "gossip", "bigg boss",
]


def _keyword_in(keyword: str, lower_text: str) -> bool:
    # Whole-word match - short study keywords like "react" or "notes"
    # would otherwise fire inside "reactive" or "denotes".
    return re.search(r"(?<![\w])" + re.escape(keyword) + r"(?![\w])", lower_text) is not None


def _classify_by_keywords(text: str) -> Optional[str]:
    """Free, instant first pass before any cache lookup or LLM call -
    checked against DISTRACTION_TITLE_KEYWORDS first since a title like
    "Lofi Study Music - Official Music Video" should read as a
    distraction despite also containing a productive-sounding word."""
    lower = text.lower()
    if any(_keyword_in(kw, lower) for kw in DISTRACTION_TITLE_KEYWORDS):
        return "distraction"
    if any(_keyword_in(kw, lower) for kw in PRODUCTIVE_TITLE_KEYWORDS):
        return "productive"
    return None


# The same curated productive/distraction/ambiguous/neutral lists
# window_tracker.py uses for desktop apps (app_categories.json), applied
# server-side too, so well-known sites (instagram.com, leetcode.com...)
# get classified instantly and correctly even when no LLM is reachable,
# and the extension and the system tracker always agree on them.
APP_CATEGORIES_PATH = REPO_ROOT / "app_categories.json"
_STATIC_CATEGORY_ORDER = ("distraction", "productive", "ambiguous", "neutral")


def _load_static_categories() -> dict:
    try:
        data = json.loads(APP_CATEGORIES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {cat: [s.lower() for s in data.get(cat, [])] for cat in _STATIC_CATEGORY_ORDER}


STATIC_CATEGORIES = _load_static_categories()


def _classify_static(key: str, is_title: bool) -> Optional[str]:
    """Domains match an entry exactly by label ("instagram" -> instagram.com,
    m.instagram.com) or by suffix for dotted entries ("docs.google.com");
    titles match whole words/phrases, skipping very short entries like
    "git" or "cmd" that are too easy to hit by accident in free text.
    Returns productive | distraction | ambiguous | neutral, or None."""
    if is_title:
        for cat in _STATIC_CATEGORY_ORDER:
            if cat == "ambiguous":
                # Every YouTube tab title ends in "- YouTube", so the site
                # name says nothing about the video - leave it to the
                # keyword/LLM tiers.
                continue
            for entry in STATIC_CATEGORIES.get(cat, []):
                if len(entry) >= 5 and _keyword_in(entry, key):
                    return cat
        return None
    labels = set(re.split(r"[.\-]", key))
    for cat in _STATIC_CATEGORY_ORDER:
        for entry in STATIC_CATEGORIES.get(cat, []):
            if "." in entry:
                if key == entry or key.endswith("." + entry):
                    return cat
            elif entry.replace(" ", "") in labels:
                return cat
    return None


def _normalize_key(raw: str) -> str:
    key = raw.strip().lower()
    if key.startswith("www."):
        key = key[4:]
    return key


def _classify_category_via_llm(key: str, is_title: bool = False) -> Optional[str]:
    subject = f'the video/page titled "{key}"' if is_title else f'the website or app "{key}"'
    prompt = (
        f"Classify {subject} for a student productivity tracker into exactly "
        "one word: productive, distraction, or neutral. productive = learning, coding, work, "
        "research, documentation, tools. distraction = entertainment, social media, games, video "
        "streaming. neutral = anything else, or if you're unsure. Respond with exactly one word, "
        "nothing else."
    )
    text = _try_anthropic(prompt) or _try_gemini(prompt) or _try_cheaper_inference(prompt)
    if not text:
        return None
    normalized = text.strip().lower()
    for cat in ("productive", "distraction", "neutral"):
        if cat in normalized:
            return cat
    return None


@app.post("/classify-domain", response_model=DomainClassifyResponse)
def classify_domain(
    payload: DomainClassifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    has_title = bool(payload.title and payload.title.strip())
    key = _normalize_key(payload.title if has_title else payload.domain)
    if not key:
        return DomainClassifyResponse(category="unknown", confidence=0.0, source="invalid")

    # Tier 0: a title with an unambiguous keyword match - free, instant,
    # no cache/LLM round-trip. Only applies when a title was sent (i.e.
    # an ambiguous domain like youtube.com), not to plain domain lookups.
    if has_title:
        keyword_hit = _classify_by_keywords(key)
        if keyword_hit is not None:
            return DomainClassifyResponse(
                category=EXT_CATEGORY_MAP.get(keyword_hit, "unknown"), confidence=0.95, source="keyword",
            )

    # Tier 0b: the curated app/site lists - instant, offline, and always
    # wins over a cached LLM guess. An ambiguous site (youtube.com) with
    # no title stays "unknown" on purpose, so the caller retries with the
    # page title rather than the whole site getting one fixed label.
    static_hit = _classify_static(key, is_title=has_title)
    if static_hit == "ambiguous":
        return DomainClassifyResponse(category="unknown", confidence=0.5, source="ambiguous")
    if static_hit is not None:
        return DomainClassifyResponse(
            category=EXT_CATEGORY_MAP.get(static_hit, "unknown"), confidence=0.95, source="static_list",
        )

    # Tier 1: this user's own group - the specific "reuse a groupmate's
    # classification" case.
    if current_user.group_id is not None:
        hit = (
            db.query(LearnedCategory)
            .filter(LearnedCategory.key == key, LearnedCategory.group_id == current_user.group_id)
            .order_by(LearnedCategory.id.desc())
            .first()
        )
        if hit:
            return DomainClassifyResponse(
                category=EXT_CATEGORY_MAP.get(hit.category, "unknown"), confidence=0.9, source="group_cache",
            )

    # Tier 2: any group's (or any ungrouped user's) prior classification -
    # crowdsourced across the whole app, not just one group.
    hit = db.query(LearnedCategory).filter(LearnedCategory.key == key).order_by(LearnedCategory.id.desc()).first()
    if hit:
        return DomainClassifyResponse(
            category=EXT_CATEGORY_MAP.get(hit.category, "unknown"), confidence=0.85, source="global_cache",
        )

    # Tier 3: nobody has ever seen this key - ask the LLM once, then save
    # it so the next lookup (same group first, then anyone) is free.
    category = _classify_category_via_llm(key, is_title=has_title)
    if category is None:
        return DomainClassifyResponse(category="unknown", confidence=0.0, source="llm_unavailable")

    db.add(LearnedCategory(key=key, category=category, group_id=current_user.group_id, source="llm"))
    db.commit()

    return DomainClassifyResponse(category=EXT_CATEGORY_MAP.get(category, "unknown"), confidence=0.9, source="llm")


# ---- Device link: one account for every local tracker ----
# FocusGuard is a single-person local app, but it has three tracking
# surfaces (web dashboard, browser extension, system tracker) that each
# used to need their own login - so in practice the tracker and the
# extension often weren't signed in at all and nothing got tracked.
# Now signing in on the dashboard (or the extension popup) links that
# account to this machine, and the extension and window_tracker.py pick
# it up from here automatically - and signing in also makes sure the
# system tracker is actually running.

TRACKER_SCRIPT = REPO_ROOT / "window_tracker.py"
TRACKER_LOG = REPO_ROOT / "tracker.log"
# window_tracker.py polls GET /device-link every ~15s, so a poll within
# this window means one is already running and nothing needs spawning.
TRACKER_ALIVE_WINDOW = timedelta(seconds=45)
# How recently the extension must have checked in from a browser for the
# system tracker to treat that browser's windows as already covered.
EXTENSION_PRESENCE_WINDOW = timedelta(minutes=3)
KNOWN_BROWSER_CLIENTS = {"chrome", "msedge", "brave", "opera", "vivaldi", "firefox"}

_tracker_last_poll: Optional[datetime] = None
_tracker_proc: Optional[subprocess.Popen] = None
# {user_id: {client: last_seen}} - in memory on purpose: it's "is the
# extension running right now", which a backend restart rightly resets.
_extension_seen: dict = defaultdict(dict)


def _note_extension_presence(user_id: int, client: Optional[str]) -> None:
    if client in KNOWN_BROWSER_CLIENTS:
        _extension_seen[user_id][client] = datetime.utcnow()


def _ensure_tracker_running(base_url: str) -> None:
    """Starts window_tracker.py in the background if none is running, so
    system apps get tracked whichever way the app was opened - not only
    when launched through launch_focusguard.py. The tracker holds a
    single-instance lock, so a racing double start just exits cleanly."""
    global _tracker_proc
    if os.environ.get("FOCUSGUARD_AUTOSTART_TRACKER", "1") != "1":
        return
    if not TRACKER_SCRIPT.is_file():
        return
    now = datetime.utcnow()
    if _tracker_last_poll is not None and now - _tracker_last_poll < TRACKER_ALIVE_WINDOW:
        return
    if _tracker_proc is not None and _tracker_proc.poll() is None:
        return
    env = dict(os.environ)
    env["TRACKER_BACKEND_URL"] = base_url.rstrip("/")
    env["TRACKER_AUTO_LINK"] = "1"
    env.pop("TRACKER_USERNAME", None)
    env.pop("TRACKER_PASSWORD", None)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        log = open(TRACKER_LOG, "a", encoding="utf-8")
        _tracker_proc = subprocess.Popen(
            [sys.executable, str(TRACKER_SCRIPT), "--no-ui"],
            cwd=REPO_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, creationflags=creationflags,
        )
        print(f"[info] Started the system tracker in the background (log: {TRACKER_LOG})", file=sys.stderr)
    except Exception as exc:
        print(f"[warn] Could not start the system tracker: {exc}", file=sys.stderr)


def _is_local_tracker_request(request: Request) -> bool:
    """GET /device-link hands out an API token, so only the local
    tracker (a plain HTTP client: no Origin header) and the browser
    extension (Origin chrome-extension://...) may read it - never a web
    page, which always sends its own Origin cross-origin and can't fake
    an extension one. The CORS wildcard above would otherwise let any
    site you visit read it."""
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        return False
    origin = request.headers.get("origin")
    if origin:
        return origin.startswith(("chrome-extension://", "moz-extension://", "extension://"))
    fetch_site = request.headers.get("sec-fetch-site")
    return fetch_site in (None, "none")


@app.post("/device-link", status_code=status.HTTP_204_NO_CONTENT)
def link_device(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    link = db.query(DeviceLink).first()
    if link is None:
        db.add(DeviceLink(user_id=current_user.id))
    elif link.user_id != current_user.id:
        link.user_id = current_user.id
        link.updated_at = datetime.utcnow()
    db.commit()
    _ensure_tracker_running(str(request.base_url))


@app.delete("/device-link", status_code=status.HTTP_204_NO_CONTENT)
def unlink_device(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db.query(DeviceLink).filter(DeviceLink.user_id == current_user.id).delete()
    db.commit()


@app.get("/device-link", response_model=DeviceLinkOut)
def get_device_link(request: Request, db: Session = Depends(get_db)):
    global _tracker_last_poll
    if not _is_local_tracker_request(request):
        raise HTTPException(status_code=403, detail="Only local trackers can read the device link")
    if request.headers.get("x-focusguard-client") == "tracker":
        _tracker_last_poll = datetime.utcnow()
    link = db.query(DeviceLink).first()
    user = db.query(User).filter(User.id == link.user_id).first() if link else None
    if user is None:
        raise HTTPException(status_code=404, detail="No account linked - sign in on the dashboard")
    return DeviceLinkOut(user_id=user.id, username=user.username, api_token=user.api_token)


@app.post("/extension/ping", status_code=status.HTTP_204_NO_CONTENT)
def extension_ping(payload: ExtensionPing, current_user: User = Depends(get_current_user)):
    _note_extension_presence(current_user.id, payload.client)


@app.get("/tracker/status", response_model=TrackerStatusResponse)
def tracker_status(current_user: User = Depends(get_current_user)):
    cutoff = datetime.utcnow() - EXTENSION_PRESENCE_WINDOW
    seen = _extension_seen.get(current_user.id, {})
    return TrackerStatusResponse(extension_browsers=sorted(c for c, t in seen.items() if t >= cutoff))


# ---- Live status (Feature 7: novelty) ----
# Lets whichever surface is currently active - the browser extension for
# a tab, window_tracker.py for a system app - push a "here's what I'm
# looking at right now" reading, and lets the web dashboard's Focus Mode
# page show it live. One row per user, upserted in place (see
# LiveStatus in models.py) - this is current state, not a log.

LIVE_STATUS_STALE_AFTER = timedelta(seconds=30)


@app.put("/live-status", response_model=LiveStatusResponse)
def update_live_status(
    payload: LiveStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.source == "extension":
        _note_extension_presence(current_user.id, payload.client)
    row = db.query(LiveStatus).filter(LiveStatus.user_id == current_user.id).first()
    if row is None:
        row = LiveStatus(user_id=current_user.id, source=payload.source, name=payload.name, category=payload.category)
        db.add(row)
    else:
        row.source = payload.source
        row.name = payload.name
        row.category = payload.category

    # Feeds Focus Mode's distraction grace-period clock (Feature 4):
    # every live-status reading while a focus session is active either
    # starts or stops the "currently on a distraction" timer, so time
    # spent there accumulates across the whole session rather than
    # resetting on each switch. See _evaluate_focus_session.
    focus_session = (
        db.query(FocusSession)
        .filter(FocusSession.user_id == current_user.id, FocusSession.status == "active")
        .order_by(FocusSession.id.desc())
        .first()
    )
    if focus_session is not None and focus_session.break_started_at is None:
        # While on a sanctioned break, the LiveStatus row above still
        # updates normally, but distraction accrual/evaluation is
        # skipped entirely - the user is allowed to be away.
        now = datetime.utcnow()
        if payload.category == "distraction":
            if focus_session.distraction_started_at is None:
                focus_session.distraction_started_at = now
        elif focus_session.distraction_started_at is not None:
            focus_session.distraction_seconds_accumulated += int(
                (now - focus_session.distraction_started_at).total_seconds()
            )
            focus_session.distraction_started_at = None
        _evaluate_focus_session(focus_session, now)

    db.commit()
    db.refresh(row)
    return LiveStatusResponse(source=row.source, name=row.name, category=row.category,
                               updated_at=row.updated_at, stale=False)


@app.get("/live-status/{user_id}", response_model=LiveStatusResponse)
def get_live_status(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot view another user's live status")
    row = db.query(LiveStatus).filter(LiveStatus.user_id == user_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="No live status yet - nothing has reported in")
    # Matches the naive-UTC convention used everywhere else in this file
    # (e.g. WeeklyInsight's is_fresh check) - SQLite returns naive
    # datetimes regardless of the DateTime(timezone=True) column type.
    is_stale = (datetime.utcnow() - row.updated_at) > LIVE_STATUS_STALE_AFTER
    return LiveStatusResponse(source=row.source, name=row.name, category=row.category,
                               updated_at=row.updated_at, stale=is_stale)


# ---- Focus Mode (Feature 4) ----

# How much cumulative time (not necessarily consecutive - separate
# distraction visits add up across the whole session) a focus session
# tolerates on a distraction tab/app before it actually breaks. Driven
# by live-status pushes (see update_live_status), which is also what
# powers the extension's every-15s nagging notification while this
# clock is running.
FOCUS_DISTRACTION_GRACE_SECONDS = 60


def _effective_distraction_seconds(session: FocusSession, now: datetime) -> float:
    """The accumulated distraction clock, including whatever's currently
    running if session.distraction_started_at is set (i.e. the most
    recent live-status reading was still 'distraction' as of now)."""
    total = float(session.distraction_seconds_accumulated)
    if session.distraction_started_at is not None:
        total += (now - session.distraction_started_at).total_seconds()
    return total


def _focus_true_elapsed_seconds(session: FocusSession, now: datetime) -> int:
    """Wall-clock time actually spent inside the session: excludes every
    completed break (paused_seconds_accumulated) and, if a break is
    CURRENTLY in progress, freezes at the moment that break started
    instead of continuing to advance with `now`. This is the one place
    "elapsed" is computed - both _evaluate_focus_session and
    _build_focus_out call it, so they can never disagree."""
    end_point = session.ended_at or session.break_started_at or now
    raw_elapsed = (end_point - session.started_at).total_seconds()
    return max(0, int(raw_elapsed) - session.paused_seconds_accumulated)


def _evaluate_focus_session(session: FocusSession, now: Optional[datetime] = None) -> None:
    """Mutates session.status/ended_at based on current time and the
    accumulated distraction clock. No-op if already finalized. Call
    this before reading or acting on a session so its status is always
    current, without needing a background job."""
    if session.status != "active":
        return

    now = now or datetime.utcnow()
    if session.break_started_at is not None:
        # On a sanctioned break - neither the distraction grace clock nor
        # the completion clock advances until they resume.
        return
    if _effective_distraction_seconds(session, now) >= FOCUS_DISTRACTION_GRACE_SECONDS:
        session.status = "broken"
        session.ended_at = now
    elif _focus_true_elapsed_seconds(session, now) >= session.planned_duration_seconds:
        session.status = "completed"
        session.ended_at = now
    # else: still legitimately active, leave as-is


def _build_focus_out(session: FocusSession) -> FocusSessionOut:
    now = datetime.utcnow()
    end_point = session.ended_at or session.break_started_at or now
    elapsed = _focus_true_elapsed_seconds(session, now)
    remaining = max(0, session.planned_duration_seconds - elapsed)
    effective_distraction = _effective_distraction_seconds(session, now if session.status == "active" else end_point)
    return FocusSessionOut(
        id=session.id, user_id=session.user_id,
        planned_duration_seconds=session.planned_duration_seconds,
        started_at=session.started_at, ended_at=session.ended_at,
        status=session.status, elapsed_seconds=elapsed, remaining_seconds=remaining,
        distraction_seconds_accumulated=min(int(effective_distraction), FOCUS_DISTRACTION_GRACE_SECONDS),
        grace_seconds_remaining=max(0, FOCUS_DISTRACTION_GRACE_SECONDS - int(effective_distraction)),
        on_break=session.break_started_at is not None,
        break_is_penalized=session.break_is_penalized if session.break_started_at is not None else None,
    )


@app.post("/focus-sessions/start", response_model=FocusSessionOut, status_code=status.HTTP_201_CREATED)
def start_focus_session(
    payload: FocusSessionStart,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = (
        db.query(FocusSession)
        .filter(FocusSession.user_id == current_user.id, FocusSession.status == "active")
        .first()
    )
    if existing:
        _evaluate_focus_session(existing)
        db.commit()
        if existing.status == "active":
            raise HTTPException(status_code=400, detail="You already have an active focus session")

    session = FocusSession(
        user_id=current_user.id,
        planned_duration_seconds=payload.duration_minutes * 60,
        status="active",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _build_focus_out(session)


@app.get("/focus-sessions/active", response_model=FocusSessionOut)
def get_active_focus_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = (
        db.query(FocusSession)
        .filter(FocusSession.user_id == current_user.id, FocusSession.status == "active")
        .order_by(FocusSession.id.desc())
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="No active focus session")
    _evaluate_focus_session(session)
    db.commit()
    return _build_focus_out(session)


@app.post("/focus-sessions/{session_id}/end", response_model=FocusSessionOut)
def end_focus_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(FocusSession).filter(FocusSession.id == session_id).first()
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Focus session not found")
    _evaluate_focus_session(session)
    if session.status == "active":
        # Still active and neither naturally completed nor broken by
        # accumulated distraction time - ending it now means the user
        # quit early.
        session.status = "broken"
        session.ended_at = datetime.utcnow()
    db.commit()
    return _build_focus_out(session)


@app.post("/focus-sessions/{session_id}/break/start", response_model=FocusSessionOut)
def start_focus_break(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(FocusSession).filter(FocusSession.id == session_id).first()
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Focus session not found")

    now = datetime.utcnow()
    _evaluate_focus_session(session, now)
    db.commit()
    if session.status != "active":
        # Already finished (naturally completed or broken) by the time
        # this was clicked - nothing to pause, just return its final state
        # rather than erroring, matching this file's tolerant style.
        return _build_focus_out(session)
    if session.break_started_at is not None:
        raise HTTPException(status_code=400, detail="Already on break")

    # Finalize any in-progress distraction accrual before freezing the
    # clock, so it doesn't keep silently "running" during the break.
    if session.distraction_started_at is not None:
        session.distraction_seconds_accumulated += int(
            (now - session.distraction_started_at).total_seconds()
        )
        session.distraction_started_at = None

    reference_point = session.last_break_ended_at or session.started_at
    interval_seconds = current_user.break_interval_minutes * 60
    elapsed_since_reference = (now - reference_point).total_seconds()
    session.break_is_penalized = elapsed_since_reference < interval_seconds
    session.break_started_at = now
    db.commit()
    db.refresh(session)
    return _build_focus_out(session)


@app.post("/focus-sessions/{session_id}/break/end", response_model=FocusBreakEndOut)
def end_focus_break(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(FocusSession).filter(FocusSession.id == session_id).first()
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Focus session not found")
    if session.status != "active" or session.break_started_at is None:
        raise HTTPException(status_code=400, detail="Not currently on break")

    now = datetime.utcnow()
    break_duration = int((now - session.break_started_at).total_seconds())
    session.paused_seconds_accumulated += break_duration

    penalized = bool(session.break_is_penalized)
    penalty_seconds = 0
    if penalized:
        # Re-read from the user's CURRENT preference, not a value frozen
        # at break-start - negligible edge case if it changed mid-break.
        penalty_seconds = current_user.break_interval_minutes * 60
        session.planned_duration_seconds += penalty_seconds

    session.last_break_ended_at = now
    session.break_started_at = None
    session.break_is_penalized = None  # consumed - no longer "current"
    _evaluate_focus_session(session, now)
    db.commit()
    db.refresh(session)
    return FocusBreakEndOut(
        session=_build_focus_out(session),
        penalty_applied=penalized,
        penalty_seconds=penalty_seconds,
    )


@app.get("/focus-sessions/history", response_model=list[FocusSessionOut])
def focus_session_history(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sessions = (
        db.query(FocusSession)
        .filter(FocusSession.user_id == current_user.id, FocusSession.status != "active")
        .order_by(FocusSession.id.desc())
        .limit(limit)
        .all()
    )
    return [_build_focus_out(s) for s in sessions]


# ---- Weekly AI Insights (Feature 5) ----

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    from google import genai as google_genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

INSIGHT_CACHE_MAX_AGE = timedelta(hours=6)
# A cached FAILURE ("AI insights unavailable...") gets a much shorter
# freshness window than a real insight - a transient outage (a Gemini
# 503, a rate limit) shouldn't leave the user staring at "unavailable"
# for up to 6 hours after the provider has already recovered. See
# get_insights() for how this interacts with never burying a
# perfectly good previous insight under a failure.
INSIGHT_FAILURE_RETRY_AFTER = timedelta(minutes=3)


def _compute_week_stats(user_id: int, days: int, db: Session) -> dict:
    cutoff = datetime.utcnow() - timedelta(days=days)
    sessions = _sessions_since(user_id, cutoff, db)
    switches = _switches_since(user_id, cutoff, db)

    totals: dict = defaultdict(int)
    for s in sessions:
        totals[s.category] += s.duration
    distraction_switches = sum(1 for sw in switches if sw.category == "distraction")

    return {
        "category_totals_seconds": CategoryTotals(
            productive=totals.get("productive", 0),
            distraction=totals.get("distraction", 0),
            neutral=totals.get("neutral", 0),
        ),
        "total_switch_count": len(switches),
        "distraction_switch_count": distraction_switches,
        "session_count": len(sessions),
    }


def _build_group_context(user: User, days: int, db: Session) -> Optional[dict]:
    """Feature 7 (novelty): lets the weekly insight comment on group
    standing, not just solo stats. None if the user isn't in a group, or
    their group has no one else to compare against yet."""
    if user.group_id is None:
        return None
    group = db.query(Group).filter(Group.id == user.group_id).first()
    if group is None:
        return None
    entries = _compute_group_leaderboard(group.id, days, db)
    if len(entries) < 2:
        return None
    return {"group_name": group.name, "entries": entries, "you_user_id": user.id}


LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "bn": "Bengali",
    "ta": "Tamil",
    "mr": "Marathi",
}


def _build_insight_prompt(
    stats: dict, days: int, group_context: Optional[dict] = None,
    language: str = "en", top_distraction_app: Optional[dict] = None,
) -> str:
    totals = stats["category_totals_seconds"]
    prompt = (
        f"Here is {days} days of a student's computer activity, tracked automatically:\n"
        f"- Productive time: {totals.productive // 60} minutes\n"
        f"- Distracting time: {totals.distraction // 60} minutes\n"
        f"- Neutral time: {totals.neutral // 60} minutes\n"
        f"- Total app/tab switches: {stats['total_switch_count']}\n"
        f"- Switches into distracting apps: {stats['distraction_switch_count']}\n"
        f"- Tracked sessions: {stats['session_count']}\n"
    )

    if top_distraction_app:
        prompt += (
            f'- Their single biggest distraction was "{top_distraction_app["name"]}", '
            f'accounting for {top_distraction_app["total_seconds"] // 60} minutes over these {days} days.\n'
        )

    if group_context:
        lines = [
            f'\nThey are also in a productivity group called "{group_context["group_name"]}", '
            f"ranked by focus score (productive time / (productive + distracting time)) over the same {days} days:"
        ]
        for e in group_context["entries"]:
            tag = " <- this student" if e["user_id"] == group_context["you_user_id"] else ""
            lines.append(
                f'- #{e["rank"]} {e["username"]}: {e["focus_score"]}% focus score, '
                f'{e["productive_seconds"] // 60} min productive{tag}'
            )
        prompt += "\n".join(lines) + "\n"

    prompt += (
        "\nWrite a short (2-3 sentence, 3-4 if a group is included), encouraging, "
        "plain-language summary of this week for the student. Point out one concrete "
        "personal pattern (e.g. a lot of switching, or a good productive/distraction "
        "ratio) and one small, actionable suggestion. "
    )
    if group_context:
        prompt += (
            "Also mention briefly how they compare to their group this week - e.g. who "
            "they're closest to, or how far ahead/behind the top of the group they are - "
            "using only the numbers given, don't invent details like specific days. "
        )
    if top_distraction_app:
        prompt += (
            f'Since "{top_distraction_app["name"]}" was their top distraction, suggest one small, '
            "concrete, TIME-BASED way to cut down on it (e.g. a daily time cap, or moving it to later "
            "in the day) - don't just repeat the stat back. "
        )
    prompt += "Always end your response with exactly one short, standalone motivational sentence. "
    prompt += "Do not use markdown formatting. Keep it warm, not preachy."

    language_name = LANGUAGE_NAMES.get(language, "English")
    if language_name != "English":
        # The dashboard UI itself is translated via static locale files
        # (see frontend/locales/) - this is the one piece of genuinely
        # dynamic, freshly-generated text, so it's simplest to just ask
        # the same LLM call to compose directly in the target language
        # rather than generating English and translating it separately.
        prompt += f" Write your entire response in {language_name}, not English."
    return prompt


# A provider that just reported a billing/credits problem is skipped for
# a while - retrying it on every request only adds a round-trip of
# latency before the next provider runs, and topping up credits takes
# minutes, not seconds.
PROVIDER_BILLING_COOLDOWN = timedelta(minutes=15)
_BILLING_ERROR_MARKERS = ("credit balance", "insufficient", "billing", "402")
_provider_paused_until: dict = {}


def _provider_paused(name: str) -> bool:
    return _provider_paused_until.get(name, datetime.min) > datetime.utcnow()


def _note_provider_failure(name: str, exc: Exception) -> None:
    if any(marker in str(exc).lower() for marker in _BILLING_ERROR_MARKERS):
        _provider_paused_until[name] = datetime.utcnow() + PROVIDER_BILLING_COOLDOWN


def _try_anthropic(prompt: str) -> Optional[str]:
    """Returns the generated text, or None if unavailable/failed for any
    reason (missing package, no key, bad key, no credits, network error,
    etc.) - None signals "try the next provider", not "give up"."""
    if not ANTHROPIC_AVAILABLE or not os.environ.get("ANTHROPIC_API_KEY") or _provider_paused("anthropic"):
        return None
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as exc:
        _note_provider_failure("anthropic", exc)
        print(f"[warn] Anthropic insight generation failed, trying next provider: {exc}", file=sys.stderr)
        return None


GEMINI_INSIGHT_MODELS = ("gemini-flash-lite-latest", "gemini-flash-latest")
_GEMINI_TRANSIENT_MARKERS = ("503", "UNAVAILABLE", "high demand", "429", "RESOURCE_EXHAUSTED")


def _try_gemini(prompt: str, attempts: int = 2, retry_delay_seconds: float = 1.0) -> Optional[str]:
    """Same contract as _try_anthropic - returns None on any failure so
    the caller can fall through to the next provider instead of
    crashing. Uses Gemini's free tier, which doesn't require billing to
    be enabled - a real alternative when the Anthropic key has no
    credits, not just a fallback for show.

    Retries once on Gemini's occasional "503 high demand" /
    429 rate-limit responses, which are genuinely transient (observed
    clearing within a couple of seconds), then moves on to the next
    model. flash-lite goes first: it answers in ~1s and is far less often
    overloaded than flash, which has its own separate free-tier capacity
    and is kept as the backup. Anything else (bad
    key, auth failure) fails fast instead, since retrying those wastes
    the user's time for no benefit."""
    if not GEMINI_AVAILABLE or not os.environ.get("GEMINI_API_KEY"):
        return None
    client = google_genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    # Thinking off: a 3-sentence summary gains nothing from it, and it
    # was taking ~15s per insight versus ~1-3s without. Models with no
    # thinking support (flash-lite) reject the setting outright, so
    # those get retried once with no config instead.
    no_thinking = google_genai.types.GenerateContentConfig(
        thinking_config=google_genai.types.ThinkingConfig(thinking_budget=0),
    )
    last_exc: Optional[Exception] = None
    for model in GEMINI_INSIGHT_MODELS:
        config = no_thinking
        attempt = 0
        while attempt < attempts:
            try:
                resp = client.models.generate_content(model=model, contents=prompt, config=config)
                text = (resp.text or "").strip()
                if text:
                    return text
                break
            except Exception as exc:
                last_exc = exc
                if config is not None and "INVALID_ARGUMENT" in str(exc):
                    config = None
                    continue
                is_transient = any(marker in str(exc) for marker in _GEMINI_TRANSIENT_MARKERS)
                if not is_transient:
                    print(f"[warn] Gemini insight generation failed: {exc}", file=sys.stderr)
                    return None
                attempt += 1
                if attempt < attempts:
                    time.sleep(retry_delay_seconds)
    print(f"[warn] Gemini insight generation failed: {last_exc}", file=sys.stderr)
    return None


def _try_cheaper_inference(prompt: str) -> Optional[str]:
    """Same contract as _try_anthropic - returns None on any failure so
    the caller can fall through to the local writer instead of
    crashing. Uses the CheaperInference proxy (OpenAI-compatible API)
    as a low-cost third fallback."""
    if not OPENAI_AVAILABLE or not os.environ.get("CHEAPER_INFERENCE_API_KEY") or _provider_paused("cheaper_inference"):
        return None
    try:
        client = OpenAI(
            api_key=os.environ["CHEAPER_INFERENCE_API_KEY"],
            base_url="https://api.cheaperinference.com/v1",
        )
        resp = client.chat.completions.create(
            model="claude-fable-5.1",
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        _note_provider_failure("cheaper_inference", exc)
        print(f"[warn] CheaperInference insight generation failed: {exc}", file=sys.stderr)
        return None


# Templates for the local, no-network insight writer used when every LLM
# provider is down or out of credits. Same languages as LANGUAGE_NAMES so
# the fallback respects the dashboard's language exactly like the AI path.
LOCAL_INSIGHT_TEMPLATES = {
    "en": {
        "no_data": "There's no tracked activity for the last {days} days yet. Start the tracker or the browser extension and run one short focus session today - your first real insight builds from there.",
        "neutral_only": "You tracked {neutral} minutes of activity, but none of it was clearly productive or distracting yet.",
        "strong": "You spent {prod} minutes on productive work against just {dist} minutes of distraction - a {ratio}% focus score, which is excellent.",
        "balanced": "You logged {prod} productive minutes and {dist} distracted minutes, a {ratio}% focus score - solid, with clear room to grow.",
        "low": "Distractions took {dist} minutes compared with {prod} productive minutes, a {ratio}% focus score this period.",
        "switch_high": "You switched apps or tabs {switches} times ({dist_switches} into distractions) - try a 25-minute Focus Mode block with only one window open.",
        "switch_ok": "Your switching stayed under control at {switches} switches - keep protecting those long, uninterrupted stretches.",
        "top_app": "{app} was your biggest distraction at {app_min} minutes; try capping it at {cap} minutes a day and saving it for after your main study block.",
        "group_lead": "You're #1 of {n} in {group} - keep setting the pace.",
        "group_behind": "You're #{rank} of {n} in {group}, {gap} points behind {leader}.",
        "closers": [
            "Every focused session is a vote for the person you're becoming.",
            "Small, steady blocks of focus add up faster than you think.",
            "One task at a time - that's where real progress lives.",
        ],
    },
    "hi": {
        "no_data": "पिछले {days} दिनों में अभी तक कोई गतिविधि ट्रैक नहीं हुई है। ट्रैकर या ब्राउज़र एक्सटेंशन चालू करें और आज एक छोटा फ़ोकस सेशन करें - आपकी पहली इनसाइट वहीं से बनेगी।",
        "neutral_only": "आपकी {neutral} मिनट की गतिविधि ट्रैक हुई, लेकिन अभी उसमें से कुछ भी साफ़ तौर पर उत्पादक या ध्यान भटकाने वाला नहीं था।",
        "strong": "आपने {prod} मिनट उत्पादक काम किया और सिर्फ़ {dist} मिनट ध्यान भटका - {ratio}% फ़ोकस स्कोर, जो शानदार है।",
        "balanced": "आपने {prod} मिनट उत्पादक काम और {dist} मिनट ध्यान भटकने में बिताए - {ratio}% फ़ोकस स्कोर, अच्छा है और सुधार की गुंजाइश भी है।",
        "low": "ध्यान भटकाने वाली चीज़ों में {dist} मिनट गए, जबकि उत्पादक काम {prod} मिनट रहा - इस बार फ़ोकस स्कोर {ratio}% रहा।",
        "switch_high": "आपने {switches} बार ऐप या टैब बदले ({dist_switches} बार ध्यान भटकाने वाली चीज़ों पर) - सिर्फ़ एक विंडो खुली रखकर 25 मिनट का फ़ोकस मोड ब्लॉक आज़माएँ।",
        "switch_ok": "आपका स्विच करना {switches} बार तक सीमित रहा - लंबे, बिना रुकावट वाले समय को ऐसे ही बचाए रखें।",
        "top_app": "{app} आपका सबसे बड़ा डिस्ट्रैक्शन रहा ({app_min} मिनट); इसे रोज़ {cap} मिनट तक सीमित करें और अपनी मुख्य पढ़ाई के बाद रखें।",
        "group_lead": "आप {group} में {n} में से #1 हैं - ऐसे ही आगे बढ़ते रहें।",
        "group_behind": "आप {group} में {n} में से #{rank} हैं, {leader} से {gap} अंक पीछे।",
        "closers": [
            "हर छोटा फ़ोकस सेशन आपको अपने लक्ष्य के और क़रीब ले जाता है।",
            "आज का फ़ोकस, कल की कामयाबी है।",
            "एक बार में एक काम - यही असली ताक़त है।",
        ],
    },
    "bn": {
        "no_data": "গত {days} দিনে এখনও কোনো কার্যকলাপ ট্র্যাক হয়নি। ট্র্যাকার বা ব্রাউজার এক্সটেনশন চালু করুন এবং আজ একটি ছোট ফোকাস সেশন করুন - আপনার প্রথম ইনসাইট সেখান থেকেই তৈরি হবে।",
        "neutral_only": "আপনার {neutral} মিনিটের কার্যকলাপ ট্র্যাক হয়েছে, কিন্তু এখনও তার কোনোটাই স্পষ্টভাবে উৎপাদনশীল বা বিক্ষেপকারী নয়।",
        "strong": "আপনি {prod} মিনিট উৎপাদনশীল কাজ করেছেন আর মাত্র {dist} মিনিট মনোযোগ হারিয়েছেন - {ratio}% ফোকাস স্কোর, যা চমৎকার।",
        "balanced": "আপনি {prod} মিনিট উৎপাদনশীল কাজে এবং {dist} মিনিট বিক্ষিপ্ত হয়ে কাটিয়েছেন - {ratio}% ফোকাস স্কোর, ভালো, তবে উন্নতির সুযোগ আছে।",
        "low": "বিক্ষেপে গেছে {dist} মিনিট, যেখানে উৎপাদনশীল কাজ ছিল {prod} মিনিট - এবার ফোকাস স্কোর {ratio}%।",
        "switch_high": "আপনি {switches} বার অ্যাপ বা ট্যাব বদলেছেন ({dist_switches} বার বিক্ষেপের দিকে) - শুধু একটি উইন্ডো খোলা রেখে 25 মিনিটের ফোকাস মোড ব্লক চেষ্টা করুন।",
        "switch_ok": "আপনার সুইচিং {switches} বারের মধ্যে নিয়ন্ত্রিত ছিল - দীর্ঘ, নিরবচ্ছিন্ন সময়গুলো এভাবেই ধরে রাখুন।",
        "top_app": "{app} ছিল আপনার সবচেয়ে বড় বিক্ষেপ ({app_min} মিনিট); এটিকে দিনে {cap} মিনিটে সীমিত করুন এবং মূল পড়াশোনার পরে রাখুন।",
        "group_lead": "আপনি {group}-এ {n} জনের মধ্যে #1 - এভাবেই এগিয়ে চলুন।",
        "group_behind": "আপনি {group}-এ {n} জনের মধ্যে #{rank}, {leader}-এর থেকে {gap} পয়েন্ট পিছিয়ে।",
        "closers": [
            "প্রতিটি ছোট ফোকাস সেশন আপনাকে লক্ষ্যের আরও কাছে নিয়ে যায়।",
            "আজকের মনোযোগই আগামীকালের সাফল্য।",
            "একবারে একটি কাজ - এটাই আসল শক্তি।",
        ],
    },
    "ta": {
        "no_data": "கடந்த {days} நாட்களில் இன்னும் எந்தச் செயல்பாடும் பதிவாகவில்லை. டிராக்கர் அல்லது பிரவுசர் எக்ஸ்டென்ஷனைத் தொடங்கி, இன்று ஒரு சிறிய ஃபோகஸ் அமர்வைச் செய்யுங்கள் - உங்கள் முதல் இன்சைட் அங்கிருந்தே உருவாகும்.",
        "neutral_only": "உங்கள் {neutral} நிமிடச் செயல்பாடு பதிவானது, ஆனால் அதில் எதுவும் இன்னும் தெளிவாகப் பயனுள்ளதாகவோ கவனச்சிதறலாகவோ இல்லை.",
        "strong": "நீங்கள் {prod} நிமிடங்கள் பயனுள்ள வேலை செய்தீர்கள், கவனச்சிதறல் வெறும் {dist} நிமிடங்கள் - {ratio}% ஃபோகஸ் ஸ்கோர், இது அருமை.",
        "balanced": "நீங்கள் {prod} நிமிடங்கள் பயனுள்ள வேலையிலும் {dist} நிமிடங்கள் கவனச்சிதறலிலும் செலவிட்டீர்கள் - {ratio}% ஃபோகஸ் ஸ்கோர், நன்று, இன்னும் மேம்படுத்த இடம் உள்ளது.",
        "low": "கவனச்சிதறலில் {dist} நிமிடங்கள் சென்றன, பயனுள்ள வேலை {prod} நிமிடங்கள் மட்டுமே - இம்முறை ஃபோகஸ் ஸ்கோர் {ratio}%.",
        "switch_high": "நீங்கள் {switches} முறை ஆப் அல்லது டேப் மாற்றினீர்கள் ({dist_switches} முறை கவனச்சிதறலுக்கு) - ஒரே ஒரு சாளரத்தைத் திறந்து வைத்து 25 நிமிட ஃபோகஸ் மோட் அமர்வை முயற்சி செய்யுங்கள்.",
        "switch_ok": "உங்கள் மாற்றங்கள் {switches} முறைக்குள் கட்டுப்பாட்டில் இருந்தன - நீண்ட, இடையூறற்ற நேரங்களை இப்படியே பாதுகாத்திடுங்கள்.",
        "top_app": "{app} உங்கள் மிகப்பெரிய கவனச்சிதறலாக இருந்தது ({app_min} நிமிடங்கள்); அதை நாளொன்றுக்கு {cap} நிமிடங்களாகக் கட்டுப்படுத்தி, முக்கியப் படிப்புக்குப் பிறகு வைத்துக்கொள்ளுங்கள்.",
        "group_lead": "{group} குழுவில் {n} பேரில் நீங்கள் #1 - இப்படியே முன்னேறுங்கள்.",
        "group_behind": "{group} குழுவில் {n} பேரில் நீங்கள் #{rank}, {leader}-ஐ விட {gap} புள்ளிகள் பின்னால்.",
        "closers": [
            "ஒவ்வொரு சிறிய ஃபோகஸ் அமர்வும் உங்களை இலக்கை நோக்கி நெருக்கமாகக் கொண்டு செல்கிறது.",
            "இன்றைய கவனமே நாளைய வெற்றி.",
            "ஒரு நேரத்தில் ஒரு வேலை - அதுவே உண்மையான பலம்.",
        ],
    },
    "mr": {
        "no_data": "गेल्या {days} दिवसांत अजून कोणतीही ॲक्टिव्हिटी ट्रॅक झालेली नाही. ट्रॅकर किंवा ब्राउझर एक्स्टेंशन सुरू करा आणि आज एक छोटे फोकस सेशन करा - तुमची पहिली इनसाइट तिथूनच तयार होईल.",
        "neutral_only": "तुमची {neutral} मिनिटांची ॲक्टिव्हिटी ट्रॅक झाली, पण त्यातील काहीही अजून स्पष्टपणे उत्पादक किंवा विचलित करणारे नव्हते.",
        "strong": "तुम्ही {prod} मिनिटे उत्पादक काम केले आणि फक्त {dist} मिनिटे लक्ष विचलित झाले - {ratio}% फोकस स्कोअर, जो उत्कृष्ट आहे.",
        "balanced": "तुम्ही {prod} मिनिटे उत्पादक कामात आणि {dist} मिनिटे विचलित होण्यात घालवली - {ratio}% फोकस स्कोअर, चांगला आहे आणि सुधारण्यास वाव आहे.",
        "low": "विचलित करणाऱ्या गोष्टींमध्ये {dist} मिनिटे गेली, तर उत्पादक काम {prod} मिनिटे झाले - या वेळी फोकस स्कोअर {ratio}% राहिला.",
        "switch_high": "तुम्ही {switches} वेळा ॲप किंवा टॅब बदलले ({dist_switches} वेळा विचलित करणाऱ्या गोष्टींकडे) - फक्त एक विंडो उघडी ठेवून 25 मिनिटांचा फोकस मोड ब्लॉक करून पाहा.",
        "switch_ok": "तुमचे स्विचिंग {switches} वेळांपर्यंत नियंत्रित राहिले - दीर्घ, अखंड वेळ असाच जपून ठेवा.",
        "top_app": "{app} हे तुमचे सर्वात मोठे विचलन होते ({app_min} मिनिटे); ते रोज {cap} मिनिटांपर्यंत मर्यादित करा आणि मुख्य अभ्यासानंतर ठेवा.",
        "group_lead": "{group} मध्ये {n} पैकी तुम्ही #1 आहात - असेच पुढे चला.",
        "group_behind": "{group} मध्ये {n} पैकी तुम्ही #{rank} आहात, {leader} पेक्षा {gap} गुणांनी मागे.",
        "closers": [
            "प्रत्येक छोटे फोकस सेशन तुम्हाला ध्येयाच्या अधिक जवळ नेते.",
            "आजचा फोकस हेच उद्याचे यश.",
            "एका वेळी एकच काम - हीच खरी ताकद.",
        ],
    },
}

# Switches per tracked hour above which the local writer calls out
# context-switching as the week's main pattern.
LOCAL_INSIGHT_HIGH_SWITCH_RATE = 20


def _build_local_insight(
    stats: dict, days: int, group_context: Optional[dict] = None,
    language: str = "en", top_distraction_app: Optional[dict] = None,
) -> str:
    """Deterministic, offline insight written straight from the same
    stats the LLM prompt uses - the last step of the provider chain, so
    the Insights tab always has a real, data-specific summary even with
    no network, no keys, or every provider out of credits."""
    tpl = LOCAL_INSIGHT_TEMPLATES.get(language, LOCAL_INSIGHT_TEMPLATES["en"])
    totals = stats["category_totals_seconds"]
    prod, dist, neutral = totals.productive // 60, totals.distraction // 60, totals.neutral // 60
    switches, dist_switches = stats["total_switch_count"], stats["distraction_switch_count"]
    closer = tpl["closers"][date_cls.today().toordinal() % len(tpl["closers"])]

    if prod + dist + neutral == 0 and switches == 0:
        return f"{tpl['no_data'].format(days=days)} {closer}"

    parts = []
    if prod + dist == 0:
        parts.append(tpl["neutral_only"].format(neutral=neutral))
    else:
        ratio = round(100 * prod / (prod + dist))
        key = "strong" if ratio >= 70 else "balanced" if ratio >= 40 else "low"
        parts.append(tpl[key].format(prod=prod, dist=dist, ratio=ratio))

    tracked_hours = max((prod + dist + neutral) / 60, 0.5)
    if switches / tracked_hours > LOCAL_INSIGHT_HIGH_SWITCH_RATE or dist_switches >= 10:
        parts.append(tpl["switch_high"].format(switches=switches, dist_switches=dist_switches))
    elif switches > 0:
        parts.append(tpl["switch_ok"].format(switches=switches))

    if top_distraction_app and top_distraction_app["total_seconds"] >= 60:
        app_min = top_distraction_app["total_seconds"] // 60
        daily_avg = app_min / max(days, 1)
        cap = max(10, int(round(daily_avg * 0.5 / 5)) * 5)
        parts.append(tpl["top_app"].format(app=top_distraction_app["name"], app_min=app_min, cap=cap))

    if group_context:
        entries = group_context["entries"]
        me = next((e for e in entries if e["user_id"] == group_context["you_user_id"]), None)
        if me is not None:
            leader = entries[0]
            if me["rank"] == 1:
                parts.append(tpl["group_lead"].format(n=len(entries), group=group_context["group_name"]))
            else:
                gap = round(leader["focus_score"] - me["focus_score"])
                parts.append(tpl["group_behind"].format(
                    rank=me["rank"], n=len(entries), group=group_context["group_name"],
                    gap=gap, leader=leader["username"],
                ))

    parts.append(closer)
    return " ".join(parts)


def _generate_insight_text(
    stats: dict, days: int, group_context: Optional[dict] = None,
    language: str = "en", top_distraction_app: Optional[dict] = None,
) -> tuple[str, bool]:
    """Tries Claude Haiku first, then falls back to Gemini (free tier),
    then to the CheaperInference proxy, if earlier providers are
    unavailable or fail for any reason - including a billing/credits
    error, not just a missing key. If every provider fails, writes the
    insight locally from the stats instead, so the user always gets one.
    Returns (text, ai_generated)."""
    prompt = _build_insight_prompt(stats, days, group_context, language, top_distraction_app)

    for provider in (_try_anthropic, _try_gemini, _try_cheaper_inference):
        text = provider(prompt)
        if text:
            return text, True

    print("[info] All AI providers unavailable - using local insight writer", file=sys.stderr)
    return _build_local_insight(stats, days, group_context, language, top_distraction_app), False


@app.get("/insights/{user_id}", response_model=InsightsResponse)
def get_insights(
    user_id: int,
    days: int = 7,
    force: bool = False,
    language: str = "en",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Cannot view another user's insights")
    if language not in LANGUAGE_NAMES:
        language = "en"

    stats = _compute_week_stats(user_id, days, db)

    # Scoped by language too - otherwise switching the dashboard's
    # language would keep serving whichever language got cached first,
    # since the cache doesn't know the insight text itself is stale for
    # a *different* language even while it's still time-fresh.
    cached = (
        db.query(WeeklyInsight)
        .filter(WeeklyInsight.user_id == user_id, WeeklyInsight.days == days, WeeklyInsight.language == language)
        .order_by(WeeklyInsight.id.desc())
        .first()
    )
    # Rows from before the local writer existed stored a literal
    # "AI insights unavailable..." message - never serve those again;
    # regenerate so the user gets a real (AI or local) insight instead.
    legacy_failure = cached is not None and cached.insight_text.startswith("AI insights unavailable")
    cached_is_fallback = cached is not None and (bool(cached.is_fallback) or legacy_failure)
    max_age = INSIGHT_FAILURE_RETRY_AFTER if cached_is_fallback else INSIGHT_CACHE_MAX_AGE
    is_fresh = cached is not None and (datetime.utcnow() - cached.generated_at) < max_age
    if cached and is_fresh and not force and not legacy_failure:
        return InsightsResponse(user_id=user_id, days=days, insight_text=cached.insight_text,
                                 generated_at=cached.generated_at, cached=True,
                                 ai_generated=not cached_is_fallback, **stats)

    group_context = _build_group_context(current_user, days, db)
    # Reuses Part A's own aggregation, so the AI insight and the History
    # page's "top distraction" callout can never disagree with each other.
    history_data = _compute_history_data(user_id, days, db)
    top_distraction_app = (
        history_data["top_distraction_app"].model_dump() if history_data["top_distraction_app"] else None
    )
    insight_text, ai_generated = _generate_insight_text(stats, days, group_context, language, top_distraction_app)

    # A transient provider outage (every LLM down/rate-limited at this
    # exact moment) shouldn't bury a previously cached GOOD AI insight -
    # the locally-written one is shown for this response, but the AI one
    # stays cached for the next normal request. Otherwise the local
    # insight is cached with the short INSIGHT_FAILURE_RETRY_AFTER
    # window, so a recovered provider takes over again within minutes.
    if not ai_generated and cached is not None and not cached_is_fallback:
        return InsightsResponse(user_id=user_id, days=days, insight_text=insight_text,
                                 generated_at=datetime.utcnow(), cached=False, ai_generated=False, **stats)

    record = WeeklyInsight(user_id=user_id, days=days, language=language,
                           insight_text=insight_text, is_fallback=not ai_generated)
    db.add(record)
    db.commit()
    db.refresh(record)
    return InsightsResponse(user_id=user_id, days=days, insight_text=insight_text,
                             generated_at=record.generated_at, cached=False, ai_generated=ai_generated, **stats)


@app.get("/", include_in_schema=False)
@app.get("/auth", include_in_schema=False)
@app.get("/profile", include_in_schema=False)
def root():
    # Serves the built React app's index.html for its three client-side
    # routes (React Router handles which page renders once it loads) so
    # opening/reloading any of them works from a single local server.
    # Falls back to the old JSON health check when no build exists yet -
    # keeps `uvicorn main:app` usable API-only, which the test suite and
    # extension development both depend on.
    if REACT_DIST_DIR.is_dir():
        index = REACT_DIST_DIR / "index.html"
        if index.is_file():
            return FileResponse(index)
    return {"status": "ok", "service": "distraction-tracker-backend"}


# PWA installability (Milestone 2): vite-plugin-pwa writes manifest.webmanifest,
# sw.js and the icon PNGs straight into the dist root (not dist/assets, which
# is the only React-build subdirectory mounted above) - this mount makes them
# reachable at their absolute paths (/manifest.webmanifest, /sw.js, /pwa-*.png)
# regardless of which page (index.html or app.html) references them, since
# both share this one origin/service-worker scope. Registered LAST, after
# every other route in this file, so it only ever catches paths nothing above
# already claimed - StaticFiles mounted at "/" would otherwise shadow the
# entire API if it were registered any earlier.
if REACT_DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=REACT_DIST_DIR), name="react-dist-root")
