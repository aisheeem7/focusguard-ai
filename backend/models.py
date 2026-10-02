"""
models.py

Database tables. Mirrors the JSON shapes already produced by
window_tracker.py, plus a users table for per-user scoping.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    api_token = Column(String, unique=True, index=True, nullable=False)
    avatar_url = Column(String, nullable=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True, index=True)
    # Feature 8: how often (minutes) this user wants a break reminder -
    # shared by window_tracker.py, the extension, and Focus Mode's own
    # break/penalty mechanic, so all three surfaces agree on one value
    # instead of each hardcoding their own default.
    break_interval_minutes = Column(Integer, nullable=False, default=50)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    sessions = relationship("SessionRecord", back_populates="user")
    switches = relationship("SwitchRecord", back_populates="user")
    group = relationship("Group", back_populates="members")


class Group(Base):
    """Feature 3: a lightweight friend/class group for the leaderboard.
    Anyone can create one and gets a join_code to share; anyone with that
    code can join. A user belongs to at most one group at a time."""
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    join_code = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("User", back_populates="group")


class LearnedCategory(Base):
    """Feature 6 (novelty): a crowdsourced app/domain -> category cache.
    The first time anyone classifies a given key via the LLM, the result
    is stored here - scoped to the classifying user's group, if any, so
    groupmates reuse it instead of spending another LLM call. Also
    readable across groups as a global fallback tier (see main.py's
    /classify-domain), so the whole userbase teaches the classifier over
    time, not just one group."""
    __tablename__ = "learned_categories"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False, index=True)  # normalized domain or app name
    category = Column(String, nullable=False)  # productive | distraction | neutral
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True, index=True)
    source = Column(String, default="llm")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class FocusSession(Base):
    """Feature 4: a timed commitment session. Reaching the planned
    duration with under FOCUS_DISTRACTION_GRACE_SECONDS of cumulative
    time on a distraction tab/app completes it; crossing that grace
    threshold breaks it. distraction_started_at/accumulated track that
    cumulative clock (see update_live_status in main.py, which is what
    actually drives it, fed by the extension/tracker's live-status
    pushes) - time on a distraction adds up across the whole session,
    even across separate visits, rather than resetting each time you
    switch away."""
    __tablename__ = "focus_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    planned_duration_seconds = Column(Integer, nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, default="active")  # active | completed | broken
    distraction_started_at = Column(DateTime(timezone=True), nullable=True)
    distraction_seconds_accumulated = Column(Integer, nullable=False, default=0)

    # Feature 8: break/penalty tracking. break_started_at is set while a
    # sanctioned break is in progress (freezes the elapsed-time clock -
    # see _focus_true_elapsed_seconds in main.py); paused_seconds_accumulated
    # is the total time spent on completed breaks, excluded from elapsed;
    # last_break_ended_at is the reference point for judging whether the
    # NEXT break is taken early; break_is_penalized is decided the moment
    # a break starts (was it early?) and consumed (reset to None) when
    # that break ends, so end_focus_break knows whether to apply the
    # penalty without re-deriving it from a reference point that's since
    # moved on.
    break_started_at = Column(DateTime(timezone=True), nullable=True)
    paused_seconds_accumulated = Column(Integer, nullable=False, default=0)
    last_break_ended_at = Column(DateTime(timezone=True), nullable=True)
    break_is_penalized = Column(Boolean, nullable=True, default=None)

    user = relationship("User")


class WeeklyInsight(Base):
    """Feature 5: caches the last AI-generated insight per user, so we
    don't call the LLM on every single request - just when the cache is
    stale (see backend main.py) or the user forces a refresh. Cached
    per-language too (see main.py's get_insights) - otherwise switching
    the dashboard's language would keep serving a stale English (or
    whichever language was cached first) insight regardless of the
    user's current choice."""
    __tablename__ = "weekly_insights"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    days = Column(Integer, nullable=False)
    language = Column(String, nullable=False, default="en")
    insight_text = Column(String, nullable=False)
    # True when every LLM provider failed and the text came from the
    # local stats-based writer instead - cached only briefly so a real
    # AI insight replaces it as soon as a provider recovers.
    is_fallback = Column(Boolean, nullable=False, default=False)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")


class LiveStatus(Base):
    """Feature 7 (novelty): the single most-recent "what am I looking at
    right now" reading for a user, pushed by whichever surface is
    currently active (extension for browser tabs, window_tracker.py for
    system apps) and polled by the web dashboard's Focus Mode card. One
    row per user - this is current state, not history, so it's
    upserted in place rather than appended to like SessionRecord."""
    __tablename__ = "live_status"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    source = Column(String, nullable=False)  # "extension" | "system"
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)  # productive | distraction | neutral
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User")


class SessionRecord(Base):
    """Mirrors the session JSON: source/name/category/start_time/end_time/duration."""
    __tablename__ = "session_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source = Column(String, default="agent")
    name = Column(String, nullable=False)
    category = Column(String, default="neutral")
    start_time = Column(String, nullable=False)  # "HH:MM" as produced by the tracker
    end_time = Column(String, nullable=False)
    duration = Column(Integer, nullable=False)  # seconds
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="sessions")


class SwitchRecord(Base):
    """Mirrors the switch JSON: from/to plus the running counters at that point."""
    __tablename__ = "switch_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source = Column(String, default="agent")
    from_app = Column(String, nullable=False)
    to_app = Column(String, nullable=False)
    category = Column(String, default="neutral")
    total_switch_count = Column(Integer, nullable=False)
    distraction_switch_count = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="switches")


class DeviceLink(Base):
    """Which account this machine's background trackers (window_tracker.py
    and the browser extension) should sync to. FocusGuard runs as one
    local app for one person, so a single row: whoever last signed in on
    the web dashboard (or connected the extension popup) is the account
    every surface tracks under, with no separate logins to keep in sync."""
    __tablename__ = "device_links"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User")
