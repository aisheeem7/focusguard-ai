"""
schemas.py

Pydantic models for request validation and response shaping. These are
the "API contract" - the extension team (and your own tracker) build
against these shapes.
"""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


# ---- Auth ----

class UserRegister(BaseModel):
    username: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    user_id: int
    username: str
    api_token: str


class UserProfileOut(BaseModel):
    id: int
    username: str
    avatar_url: Optional[str] = None
    break_interval_minutes: int = 50

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    username: Optional[str] = None
    # Feature 8: how often (minutes) this user wants a break reminder,
    # shared across window_tracker.py, the extension, and Focus Mode's
    # break/penalty mechanic. Bounded to a sane range server-side.
    break_interval_minutes: Optional[int] = None


# ---- Sessions ----

class SessionCreate(BaseModel):
    source: str = "agent"
    name: str
    category: str = "neutral"
    start_time: str
    end_time: str
    duration: int


class SessionOut(SessionCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Switches ----

class SwitchCreate(BaseModel):
    source: str = "agent"  # "system" (window_tracker.py) or "extension" (browser)
    from_app: str
    to_app: str
    category: str = "neutral"
    total_switch_count: int
    distraction_switch_count: int


class SwitchOut(SwitchCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Analytics ----

class CategoryTotals(BaseModel):
    productive: int = 0
    distraction: int = 0
    neutral: int = 0


class AnalyticsResponse(BaseModel):
    user_id: int
    date: Optional[str] = None
    category_totals_seconds: CategoryTotals
    total_switch_count: int
    distraction_switch_count: int
    session_count: int


# ---- Streaks & Badges (Feature 2) ----

class DayStat(BaseModel):
    date: str
    productive_seconds: int = 0
    distraction_seconds: int = 0
    neutral_seconds: int = 0
    total_switches: int = 0
    distraction_switches: int = 0
    is_success: bool


class StreaksResponse(BaseModel):
    user_id: int
    current_streak: int
    longest_streak: int
    threshold: int
    badges: list[str]
    days: list[DayStat]


# ---- Crowdsourced classification (Feature 6: novelty) ----

class DomainClassifyRequest(BaseModel):
    domain: str
    # The page/video title, when the caller has one - lets a domain that
    # hosts both productive and distracting content (youtube.com above
    # all) be classified by what's actually on the page, not just which
    # site it's on. Optional and backward compatible: omitted, classification
    # falls back to the domain alone exactly as before.
    title: Optional[str] = None


class DomainClassifyResponse(BaseModel):
    category: str  # educational | non_educational | unknown (extension's vocabulary)
    confidence: float
    source: str  # keyword | group_cache | global_cache | llm | llm_unavailable | invalid


# ---- Groups & Leaderboard (Feature 3) ----

class GroupCreate(BaseModel):
    name: str


class GroupJoin(BaseModel):
    join_code: str


class GroupOut(BaseModel):
    id: int
    name: str
    join_code: str

    class Config:
        from_attributes = True


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: int
    username: str
    productive_seconds: int
    distraction_seconds: int
    focus_score: float  # 0-100, productive / (productive + distraction)


class LeaderboardResponse(BaseModel):
    group_id: int
    group_name: str
    days: int
    entries: list[LeaderboardEntry]


# ---- Focus Mode (Feature 4) ----

class FocusSessionStart(BaseModel):
    duration_minutes: int


class FocusSessionOut(BaseModel):
    id: int
    user_id: int
    planned_duration_seconds: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    status: str  # active | completed | broken
    elapsed_seconds: int
    remaining_seconds: int
    distraction_seconds_accumulated: int  # cumulative time on a distraction tab/app this session, capped at the grace threshold
    grace_seconds_remaining: int  # how much of that grace budget is left before the session breaks
    on_break: bool = False
    break_is_penalized: Optional[bool] = None  # only meaningful while on_break is true

    class Config:
        from_attributes = True


class FocusBreakEndOut(BaseModel):
    session: FocusSessionOut
    penalty_applied: bool
    penalty_seconds: int


# ---- Live status (Feature 7: novelty) ----

class LiveStatusUpdate(BaseModel):
    source: str  # "extension" | "system"
    name: str
    category: str  # productive | distraction | neutral
    # Which browser the extension is running in (chrome, msedge, brave...),
    # so window_tracker.py knows that browser's windows are already covered
    # and doesn't count the same time twice. Optional/backward compatible.
    client: Optional[str] = None


class LiveStatusResponse(BaseModel):
    source: str
    name: str
    category: str
    updated_at: datetime
    stale: bool  # true if no surface has pushed a reading recently

    class Config:
        from_attributes = True


# ---- Weekly AI Insights (Feature 5) ----

class InsightsResponse(BaseModel):
    user_id: int
    days: int
    category_totals_seconds: CategoryTotals
    total_switch_count: int
    distraction_switch_count: int
    session_count: int
    insight_text: str
    generated_at: datetime
    cached: bool
    ai_generated: bool = True


# ---- History (Feature 8) ----

class AppTimeEntry(BaseModel):
    name: str
    category: str
    source: str  # "extension" | "system" | "combined" (merged across sources)
    total_seconds: int


class DayCategoryTotal(BaseModel):
    date: str
    productive_seconds: int = 0
    distraction_seconds: int = 0
    neutral_seconds: int = 0


class HistoryResponse(BaseModel):
    user_id: int
    days: int
    top_apps: list[AppTimeEntry]
    daily_totals: list[DayCategoryTotal]
    top_distraction_app: Optional[AppTimeEntry] = None
    most_productive_day: Optional[DayCategoryTotal] = None


# ---- Device link: one account shared by every local tracker ----

class DeviceLinkOut(BaseModel):
    user_id: int
    username: str
    api_token: str


class ExtensionPing(BaseModel):
    client: str  # chrome | msedge | brave | opera | vivaldi | firefox


class TrackerStatusResponse(BaseModel):
    # Browsers the extension has checked in from recently - the system
    # tracker leaves those browsers' windows to the extension.
    extension_browsers: list[str]
    # Whether this account's desktop tracker has checked in within the
    # last minute - a website can't see desktop apps on its own.
    system_tracker_online: bool = False
    # The server runs on this machine (it can start the tracker itself).
    local_mode: bool = False


# ---- Badges (achievement catalog) ----

class BadgeProgress(BaseModel):
    id: str
    tier: int  # 1 common | 2 rare | 3 epic
    earned: bool
    progress: int
    target: int


class BadgesResponse(BaseModel):
    user_id: int
    earned_count: int
    total: int
    badges: list[BadgeProgress]
