"""
test_backend.py

Automated tests for the backend API. Run from the backend/ folder:
    pytest tests/ -v

Covers: auth, sessions/switches, analytics, streaks, groups &
leaderboard, focus mode, and insights - including the two real bugs
found and fixed during development (the register race condition, and
the SQLite datetime-comparison issue in focus session evaluation).
"""

from datetime import datetime, timedelta

import main as main_module
from database import SessionLocal
from conftest import register, auth_headers


# ---- Auth ----

def test_register_creates_account(client):
    user = register(client, "alice", "pass123")
    assert user["username"] == "alice"
    assert "api_token" in user


def test_duplicate_username_rejected(client):
    register(client, "alice", "pass123")
    r = client.post("/users/register", json={"username": "alice", "password": "different"})
    assert r.status_code == 400


def test_login_with_correct_credentials(client):
    register(client, "alice", "pass123")
    r = client.post("/users/login", json={"username": "alice", "password": "pass123"})
    assert r.status_code == 200
    assert r.json()["username"] == "alice"


def test_login_with_wrong_password_rejected(client):
    register(client, "alice", "pass123")
    r = client.post("/users/login", json={"username": "alice", "password": "wrong"})
    assert r.status_code == 401


def test_concurrent_registration_does_not_500(client):
    """Regression test for a real bug found during development: two
    simultaneous registration attempts for the same not-yet-existing
    username used to race past the 'already exists' check and crash
    with an unhandled IntegrityError. Uses real threads (not just two
    sequential calls) to actually reproduce the race window, rather
    than just checking the ordinary duplicate-username path."""
    import threading

    results = []

    def do_register():
        r = client.post("/users/register", json={"username": "racer", "password": "p"})
        results.append(r)

    threads = [threading.Thread(target=do_register) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    statuses = sorted(r.status_code for r in results)
    # Neither request should ever 500, regardless of which one "wins"
    # the race - one succeeds outright (201), and the other either also
    # succeeds (200/201, if it lost the race and the endpoint gracefully
    # returns the winning account) or cleanly reports the username is
    # taken (400) - anything in this set is a correct outcome; 500 is not.
    assert all(s in (200, 201, 400) for s in statuses), f"Got statuses: {statuses}"
    assert 500 not in statuses


def test_endpoints_require_auth(client):
    r = client.get("/streaks/1")
    assert r.status_code in (401, 403)


# ---- Sessions & Switches ----

def test_post_session_and_read_it_back(client):
    user = register(client)
    r = client.post("/sessions", json={
        "source": "system", "name": "VS Code", "category": "productive",
        "start_time": "09:00", "end_time": "09:30", "duration": 1800,
    }, headers=auth_headers(user))
    assert r.status_code == 201
    assert r.json()["duration"] == 1800


def test_analytics_aggregates_correctly(client):
    user = register(client)
    client.post("/sessions", json={
        "source": "system", "name": "VS Code", "category": "productive",
        "start_time": "09:00", "end_time": "09:30", "duration": 1800,
    }, headers=auth_headers(user))
    client.post("/sessions", json={
        "source": "system", "name": "Instagram", "category": "distraction",
        "start_time": "09:30", "end_time": "09:32", "duration": 120,
    }, headers=auth_headers(user))
    client.post("/switches", json={
        "source": "system", "from_app": "VS Code", "to_app": "Instagram",
        "category": "distraction", "total_switch_count": 1, "distraction_switch_count": 1,
    }, headers=auth_headers(user))

    r = client.get(f"/analytics/{user['user_id']}", headers=auth_headers(user))
    data = r.json()
    assert data["category_totals_seconds"]["productive"] == 1800
    assert data["category_totals_seconds"]["distraction"] == 120
    assert data["session_count"] == 2
    assert data["total_switch_count"] == 1
    assert data["distraction_switch_count"] == 1


def test_cannot_view_another_users_analytics(client):
    alice = register(client, "alice")
    bob = register(client, "bob")
    r = client.get(f"/analytics/{alice['user_id']}", headers=auth_headers(bob))
    assert r.status_code == 403


# ---- Groups & Leaderboard ----

def test_group_create_and_join(client):
    alice = register(client, "alice")
    bob = register(client, "bob")

    r = client.post("/groups", json={"name": "Study Squad"}, headers=auth_headers(alice))
    assert r.status_code == 201
    group = r.json()
    assert "join_code" in group

    r = client.post("/groups/join", json={"join_code": group["join_code"]}, headers=auth_headers(bob))
    assert r.status_code == 200
    assert r.json()["id"] == group["id"]


def test_join_with_bad_code_fails(client):
    user = register(client)
    r = client.post("/groups/join", json={"join_code": "ZZZZZZ"}, headers=auth_headers(user))
    assert r.status_code == 404


def test_leaderboard_ranks_by_focus_score(client):
    alice = register(client, "alice")
    bob = register(client, "bob")
    client.post("/groups", json={"name": "Squad"}, headers=auth_headers(alice))
    group = client.get("/groups/me", headers=auth_headers(alice)).json()
    client.post("/groups/join", json={"join_code": group["join_code"]}, headers=auth_headers(bob))

    # Alice: mostly productive
    client.post("/sessions", json={
        "source": "system", "name": "VS Code", "category": "productive",
        "start_time": "09:00", "end_time": "10:00", "duration": 3000,
    }, headers=auth_headers(alice))
    client.post("/sessions", json={
        "source": "system", "name": "Instagram", "category": "distraction",
        "start_time": "10:00", "end_time": "10:03", "duration": 200,
    }, headers=auth_headers(alice))
    # Bob: mostly distracted
    client.post("/sessions", json={
        "source": "system", "name": "VS Code", "category": "productive",
        "start_time": "09:00", "end_time": "09:08", "duration": 500,
    }, headers=auth_headers(bob))
    client.post("/sessions", json={
        "source": "system", "name": "TikTok", "category": "distraction",
        "start_time": "09:08", "end_time": "09:33", "duration": 1500,
    }, headers=auth_headers(bob))

    r = client.get("/leaderboard", headers=auth_headers(alice))
    entries = r.json()["entries"]
    assert entries[0]["username"] == "alice"
    assert entries[0]["rank"] == 1
    assert entries[1]["username"] == "bob"


def test_leaderboard_requires_group(client):
    user = register(client)
    r = client.get("/leaderboard", headers=auth_headers(user))
    assert r.status_code == 400


# ---- Focus Mode ----

def test_focus_session_completes_naturally(client):
    user = register(client)
    r = client.post("/focus-sessions/start", json={"duration_minutes": 0}, headers=auth_headers(user))
    assert r.status_code == 201
    session_id = r.json()["id"]

    r = client.get("/focus-sessions/active", headers=auth_headers(user))
    assert r.json()["status"] == "completed"


def _backdate_distraction_clock(user_id: int, seconds_ago: int) -> None:
    """Test helper: simulates time having passed on a distraction
    tab/app without a real sleep, by directly backdating the active
    focus session's distraction_started_at (set moments ago by a real
    PUT /live-status call) in the database."""
    db = SessionLocal()
    session = (
        db.query(main_module.FocusSession)
        .filter(main_module.FocusSession.user_id == user_id, main_module.FocusSession.status == "active")
        .first()
    )
    session.distraction_started_at = datetime.utcnow() - timedelta(seconds=seconds_ago)
    db.commit()
    db.close()


def test_focus_session_breaks_after_distraction_grace_period(client):
    """Focus Mode tolerates brief distractions - it only breaks once
    FOCUS_DISTRACTION_GRACE_SECONDS (60s) of cumulative time on a
    distraction tab/app has passed, driven by live-status pushes from
    the extension/tracker rather than an instant break on the first
    switch (see main.py's update_live_status)."""
    user = register(client)
    client.post("/focus-sessions/start", json={"duration_minutes": 30}, headers=auth_headers(user))

    client.put("/live-status", json={
        "source": "system", "name": "Instagram", "category": "distraction",
    }, headers=auth_headers(user))
    _backdate_distraction_clock(user["user_id"], seconds_ago=61)

    r = client.get("/focus-sessions/active", headers=auth_headers(user))
    assert r.json()["status"] == "broken"


def test_focus_session_not_broken_by_productive_activity(client):
    user = register(client)
    client.post("/focus-sessions/start", json={"duration_minutes": 30}, headers=auth_headers(user))
    client.put("/live-status", json={
        "source": "system", "name": "VS Code", "category": "productive",
    }, headers=auth_headers(user))
    r = client.get("/focus-sessions/active", headers=auth_headers(user))
    assert r.json()["status"] == "active"


def test_focus_session_distraction_time_is_cumulative(client):
    """Two short distraction visits that individually stay under the
    60s grace period should still break the session once their total
    crosses it - the clock doesn't reset just because the user switched
    away and back."""
    user = register(client)
    client.post("/focus-sessions/start", json={"duration_minutes": 30}, headers=auth_headers(user))

    # First visit: 35s on a distraction, then back to productive.
    client.put("/live-status", json={
        "source": "system", "name": "Instagram", "category": "distraction",
    }, headers=auth_headers(user))
    _backdate_distraction_clock(user["user_id"], seconds_ago=35)
    r = client.put("/live-status", json={
        "source": "system", "name": "VS Code", "category": "productive",
    }, headers=auth_headers(user))

    r = client.get("/focus-sessions/active", headers=auth_headers(user))
    assert r.json()["status"] == "active"
    assert r.json()["distraction_seconds_accumulated"] >= 34  # ~35s banked, under the 60s grace

    # Second visit: another 35s - 35+35=70s total, over the 60s grace.
    client.put("/live-status", json={
        "source": "system", "name": "Instagram", "category": "distraction",
    }, headers=auth_headers(user))
    _backdate_distraction_clock(user["user_id"], seconds_ago=35)

    r = client.get("/focus-sessions/active", headers=auth_headers(user))
    assert r.json()["status"] == "broken"


def test_cannot_start_two_focus_sessions_at_once(client):
    user = register(client)
    client.post("/focus-sessions/start", json={"duration_minutes": 30}, headers=auth_headers(user))
    r = client.post("/focus-sessions/start", json={"duration_minutes": 10}, headers=auth_headers(user))
    assert r.status_code == 400


def test_manual_end_before_duration_elapsed_counts_as_broken(client):
    user = register(client)
    r = client.post("/focus-sessions/start", json={"duration_minutes": 30}, headers=auth_headers(user))
    session_id = r.json()["id"]
    r = client.post(f"/focus-sessions/{session_id}/end", headers=auth_headers(user))
    assert r.json()["status"] == "broken"


# ---- Streaks ----

def test_streaks_with_no_data_returns_zero(client):
    user = register(client)
    r = client.get(f"/streaks/{user['user_id']}", headers=auth_headers(user))
    assert r.status_code == 200
    assert r.json()["current_streak"] == 0
    assert r.json()["longest_streak"] == 0


# ---- Insights ----

def test_insights_fallback_when_no_api_key(client, monkeypatch):
    # Isolate all three providers, not just Anthropic - a real dev machine
    # may have a working GEMINI_API_KEY or CHEAPER_INFERENCE_API_KEY in
    # its .env, and this test wants the "every provider is unavailable"
    # path specifically, not just "Anthropic is unavailable".
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("CHEAPER_INFERENCE_API_KEY", raising=False)
    user = register(client)
    client.post("/sessions", json={
        "source": "system", "name": "VS Code", "category": "productive",
        "start_time": "09:00", "end_time": "09:30", "duration": 1800,
    }, headers=auth_headers(user))

    r = client.get(f"/insights/{user['user_id']}", headers=auth_headers(user))
    assert r.status_code == 200
    data = r.json()
    assert data["category_totals_seconds"]["productive"] == 1800
    # Every provider is down, so the local writer must still produce a
    # real, data-specific insight - never an "unavailable" placeholder.
    assert data["ai_generated"] is False
    assert "unavailable" not in data["insight_text"].lower()
    assert "30 minutes" in data["insight_text"]


def test_local_insight_respects_language_and_names_top_distraction(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("CHEAPER_INFERENCE_API_KEY", raising=False)
    user = register(client)
    _seed_session(client, user, "Instagram", "distraction", 3600)

    r_en = client.get(f"/insights/{user['user_id']}", headers=auth_headers(user))
    assert "Instagram" in r_en.json()["insight_text"]

    r_hi = client.get(f"/insights/{user['user_id']}?language=hi", headers=auth_headers(user))
    assert "Instagram" in r_hi.json()["insight_text"]
    assert "मिनट" in r_hi.json()["insight_text"]


def test_insights_are_cached(client, monkeypatch):
    # Same isolation as above - this test only cares about the caching
    # behavior, not the provider chain, so keep it fast/deterministic by
    # not hitting a real API even if one happens to be configured.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("CHEAPER_INFERENCE_API_KEY", raising=False)
    user = register(client)
    r1 = client.get(f"/insights/{user['user_id']}", headers=auth_headers(user))
    r2 = client.get(f"/insights/{user['user_id']}", headers=auth_headers(user))
    assert r1.json()["cached"] is False
    assert r2.json()["cached"] is True


def test_failed_regeneration_does_not_overwrite_good_cached_insight(client, monkeypatch):
    """Regression test for a real bug: a forced refresh that happens to
    land during a provider outage used to unconditionally overwrite the
    cache, so a single bad-timing refresh could bury a perfectly good
    insight under an 'unavailable' placeholder for up to 6 hours. A
    failed regeneration should surface once but leave a good cached
    insight in place for the next normal (non-forced) request."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("CHEAPER_INFERENCE_API_KEY", raising=False)
    user = register(client)

    monkeypatch.setattr(main_module, "_try_anthropic", lambda prompt: "You did great this week!")
    r1 = client.get(f"/insights/{user['user_id']}", headers=auth_headers(user))
    assert r1.json()["insight_text"] == "You did great this week!"

    monkeypatch.setattr(main_module, "_try_anthropic", lambda prompt: None)
    r2 = client.get(f"/insights/{user['user_id']}?force=true", headers=auth_headers(user))
    assert r2.json()["ai_generated"] is False
    assert r2.json()["insight_text"]

    r3 = client.get(f"/insights/{user['user_id']}", headers=auth_headers(user))
    assert r3.json()["insight_text"] == "You did great this week!"
    assert r3.json()["cached"] is True


def test_first_ever_failure_is_retried_quickly_not_for_6_hours(client, monkeypatch):
    """Regression test for a real bug: when NOTHING has ever been cached
    yet, a single transient outage used to get cached as the 'latest'
    insight for the full 6-hour INSIGHT_CACHE_MAX_AGE window - so a
    user's very first visit landing during a brief provider hiccup would
    see 'AI insights unavailable' for hours afterward even once the
    provider recovered, with no way to tell (looks identical to a real
    outage). Failures should only stay cached for the short
    INSIGHT_FAILURE_RETRY_AFTER window, so the next normal (non-forced)
    request past that point automatically retries instead of staying
    stuck."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("CHEAPER_INFERENCE_API_KEY", raising=False)
    user = register(client)

    r1 = client.get(f"/insights/{user['user_id']}", headers=auth_headers(user))
    assert r1.json()["ai_generated"] is False
    assert r1.json()["cached"] is False

    # Immediately after: still within the short retry window, so the
    # same cached failure is served without hitting the providers again.
    r2 = client.get(f"/insights/{user['user_id']}", headers=auth_headers(user))
    assert r2.json()["cached"] is True

    # Backdate the cached failure past INSIGHT_FAILURE_RETRY_AFTER (but
    # still well within the old 6-hour INSIGHT_CACHE_MAX_AGE, which is
    # exactly the gap the bug lived in) and simulate the provider having
    # recovered.
    db = SessionLocal()
    row = db.query(main_module.WeeklyInsight).filter(main_module.WeeklyInsight.user_id == user["user_id"]).first()
    row.generated_at = datetime.utcnow() - main_module.INSIGHT_FAILURE_RETRY_AFTER - timedelta(seconds=5)
    db.commit()
    db.close()
    monkeypatch.setattr(main_module, "_try_anthropic", lambda prompt: "Back online, great week!")

    r3 = client.get(f"/insights/{user['user_id']}", headers=auth_headers(user))
    assert r3.json()["insight_text"] == "Back online, great week!"
    assert r3.json()["cached"] is False
    assert r3.json()["ai_generated"] is True


def test_insights_are_cached_separately_per_language(client, monkeypatch):
    """Regression test: switching the dashboard's language used to keep
    serving whichever language happened to be cached first, since the
    cache didn't distinguish languages - only "is this row time-fresh".
    Each language should get its own cache slot, and the prompt actually
    sent to the model should ask for that language."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("CHEAPER_INFERENCE_API_KEY", raising=False)
    user = register(client)

    captured_prompts = []

    def fake_anthropic(prompt):
        captured_prompts.append(prompt)
        return "Hindi version" if "Hindi" in prompt else "English version"

    monkeypatch.setattr(main_module, "_try_anthropic", fake_anthropic)

    r_en = client.get(f"/insights/{user['user_id']}?language=en", headers=auth_headers(user))
    assert r_en.json()["insight_text"] == "English version"

    r_hi = client.get(f"/insights/{user['user_id']}?language=hi", headers=auth_headers(user))
    assert r_hi.json()["insight_text"] == "Hindi version"
    assert "Write your entire response in Hindi" in captured_prompts[-1]

    # Re-requesting English should still hit its own cache, not the
    # Hindi row that was written afterward.
    r_en_again = client.get(f"/insights/{user['user_id']}?language=en", headers=auth_headers(user))
    assert r_en_again.json()["insight_text"] == "English version"
    assert r_en_again.json()["cached"] is True


# ---- Crowdsourced classification (title-based keyword tier) ----

def test_classify_domain_without_title_is_unaffected(client, monkeypatch):
    """Backward compatibility: a plain domain lookup (no title) must
    keep working exactly as before - keyword classification only
    engages when a title is actually sent."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("CHEAPER_INFERENCE_API_KEY", raising=False)
    user = register(client)
    # Not in app_categories.json (github.com now is, and resolves from
    # the static list) - so this still exercises the LLM path.
    r = client.post("/classify-domain", json={"domain": "some-unlisted-tutorial-site.org"}, headers=auth_headers(user))
    assert r.status_code == 200
    assert r.json()["source"] == "llm_unavailable"


def test_classify_domain_title_productive_keyword(client, monkeypatch):
    """A youtube.com video titled like a tutorial should classify as
    productive from the keyword match alone - no LLM call needed."""
    monkeypatch.setattr(main_module, "_try_anthropic", lambda prompt: (_ for _ in ()).throw(AssertionError("LLM should not be called for a keyword match")))
    user = register(client)
    r = client.post(
        "/classify-domain",
        json={"domain": "youtube.com", "title": "Python Full Course Tutorial for Beginners"},
        headers=auth_headers(user),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["category"] == "educational"
    assert data["source"] == "keyword"


def test_classify_domain_title_distraction_keyword(client, monkeypatch):
    """A youtube.com video titled like a music video should classify as
    a distraction from the keyword match alone."""
    monkeypatch.setattr(main_module, "_try_anthropic", lambda prompt: (_ for _ in ()).throw(AssertionError("LLM should not be called for a keyword match")))
    user = register(client)
    r = client.post(
        "/classify-domain",
        json={"domain": "youtube.com", "title": "Taylor Swift - Official Music Video"},
        headers=auth_headers(user),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["category"] == "non_educational"
    assert data["source"] == "keyword"


def test_classify_domain_title_falls_back_to_llm_when_no_keyword(client, monkeypatch):
    """A title with no keyword match should still fall through to the
    LLM tier, using the title text (not the bare domain) as the subject."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("CHEAPER_INFERENCE_API_KEY", raising=False)
    captured = []

    def fake_anthropic(prompt):
        captured.append(prompt)
        return "productive"

    monkeypatch.setattr(main_module, "_try_anthropic", fake_anthropic)
    user = register(client)
    r = client.post(
        "/classify-domain",
        json={"domain": "youtube.com", "title": "A Chill Afternoon With My Cat"},
        headers=auth_headers(user),
    )
    assert r.status_code == 200
    assert r.json()["source"] == "llm"
    # The prompt uses the normalized (lowercased) key, not the original
    # mixed-case title - see _normalize_key().
    assert "a chill afternoon with my cat" in captured[-1].lower()


# ---- History (Feature 8) ----

def _seed_session(client, user, name, category, duration, days_ago=0, source="system"):
    """Directly inserts a SessionRecord with a controlled created_at, so
    day-bucketed aggregation can be tested deterministically instead of
    depending on "now" at test-run time."""
    db = SessionLocal()
    record = main_module.SessionRecord(
        user_id=user["user_id"], source=source, name=name, category=category,
        start_time="09:00", end_time="09:30", duration=duration,
        created_at=datetime.utcnow() - timedelta(days=days_ago),
    )
    db.add(record)
    db.commit()
    db.close()


def test_history_aggregates_top_apps_and_daily_totals_accurately(client):
    user = register(client)
    # Same app, two separate visits (possibly from different sources) -
    # must be SUMMED, not just the last one kept.
    _seed_session(client, user, "Instagram", "distraction", 300, source="extension")
    _seed_session(client, user, "Instagram", "distraction", 120, source="system")
    _seed_session(client, user, "VS Code", "productive", 1800, source="system")

    r = client.get(f"/history/{user['user_id']}?days=7", headers=auth_headers(user))
    assert r.status_code == 200
    data = r.json()

    by_name = {(e["name"], e["source"]): e["total_seconds"] for e in data["top_apps"]}
    assert by_name[("Instagram", "extension")] == 300
    assert by_name[("Instagram", "system")] == 120
    assert by_name[("VS Code", "system")] == 1800

    # top_distraction_app merges Instagram's two sources: 300 + 120 = 420.
    assert data["top_distraction_app"]["name"] == "Instagram"
    assert data["top_distraction_app"]["total_seconds"] == 420

    assert data["most_productive_day"]["productive_seconds"] == 1800
    today = data["daily_totals"][-1]
    assert today["productive_seconds"] == 1800
    assert today["distraction_seconds"] == 420


def test_history_excludes_data_outside_the_requested_window(client):
    user = register(client)
    _seed_session(client, user, "Old Distraction", "distraction", 5000, days_ago=30)
    _seed_session(client, user, "Recent Work", "productive", 600, days_ago=1)

    r = client.get(f"/history/{user['user_id']}?days=7", headers=auth_headers(user))
    names = {e["name"] for e in r.json()["top_apps"]}
    assert "Recent Work" in names
    assert "Old Distraction" not in names


def test_history_with_no_data_returns_empty_and_null_insights(client):
    user = register(client)
    r = client.get(f"/history/{user['user_id']}", headers=auth_headers(user))
    data = r.json()
    assert data["top_apps"] == []
    assert data["daily_totals"] == []
    assert data["top_distraction_app"] is None
    assert data["most_productive_day"] is None


def test_history_forbidden_for_another_users_data(client):
    alice = register(client, "alice", "pass123")
    bob = register(client, "bob", "pass123")
    r = client.get(f"/history/{bob['user_id']}", headers=auth_headers(alice))
    assert r.status_code == 403


# ---- Break timer + Focus Mode penalty (Feature 8) ----

def test_break_interval_is_editable_and_bounded(client):
    user = register(client)
    r = client.get("/users/me", headers=auth_headers(user))
    assert r.json()["break_interval_minutes"] == 50  # default

    r = client.patch("/users/me", json={"break_interval_minutes": 15}, headers=auth_headers(user))
    assert r.status_code == 200
    assert r.json()["break_interval_minutes"] == 15

    r = client.patch("/users/me", json={"break_interval_minutes": 1}, headers=auth_headers(user))
    assert r.status_code == 400

    r = client.patch("/users/me", json={"break_interval_minutes": 9999}, headers=auth_headers(user))
    assert r.status_code == 400


def _backdate_session_start(user_id: int, seconds_ago: int) -> None:
    """Test helper: backdates the active focus session's started_at so
    an early/late break can be tested without a real sleep."""
    db = SessionLocal()
    session = (
        db.query(main_module.FocusSession)
        .filter(main_module.FocusSession.user_id == user_id, main_module.FocusSession.status == "active")
        .first()
    )
    session.started_at = datetime.utcnow() - timedelta(seconds=seconds_ago)
    db.commit()
    db.close()


def test_early_break_pauses_the_clock_and_penalizes_on_resume(client):
    user = register(client)
    client.patch("/users/me", json={"break_interval_minutes": 15}, headers=auth_headers(user))  # 900s
    r = client.post("/focus-sessions/start", json={"duration_minutes": 30}, headers=auth_headers(user))
    session_id = r.json()["id"]
    planned_before = r.json()["planned_duration_seconds"]

    # Taking a break immediately (0s since session start) is well before
    # the 900s interval - this break should be flagged as penalized.
    r = client.post(f"/focus-sessions/{session_id}/break/start", headers=auth_headers(user))
    assert r.status_code == 200
    assert r.json()["on_break"] is True
    assert r.json()["break_is_penalized"] is True

    # While on break, elapsed/remaining must be FROZEN - simulate a long
    # break by backdating break_started_at, then confirm the session
    # hasn't silently completed or advanced during it.
    db = SessionLocal()
    session = db.query(main_module.FocusSession).filter(main_module.FocusSession.id == session_id).first()
    session.break_started_at = datetime.utcnow() - timedelta(minutes=45)  # longer than the 30-min plan
    db.commit()
    db.close()

    r = client.get("/focus-sessions/active", headers=auth_headers(user))
    assert r.json()["status"] == "active"  # did NOT auto-complete/break while paused
    assert r.json()["remaining_seconds"] == planned_before  # frozen, not decremented

    r = client.post(f"/focus-sessions/{session_id}/break/end", headers=auth_headers(user))
    assert r.status_code == 200
    body = r.json()
    assert body["penalty_applied"] is True
    assert body["penalty_seconds"] == 15 * 60
    assert body["session"]["on_break"] is False
    assert body["session"]["planned_duration_seconds"] == planned_before + 15 * 60
    # Elapsed excludes the ~45-minute break entirely.
    assert body["session"]["elapsed_seconds"] < 10


def test_late_break_is_not_penalized(client):
    user = register(client)
    client.patch("/users/me", json={"break_interval_minutes": 15}, headers=auth_headers(user))  # 900s
    r = client.post("/focus-sessions/start", json={"duration_minutes": 30}, headers=auth_headers(user))
    session_id = r.json()["id"]
    planned_before = r.json()["planned_duration_seconds"]

    # Session "started" 20 minutes ago (> the 15-min interval) - this
    # break is earned, not early.
    _backdate_session_start(user["user_id"], seconds_ago=20 * 60)

    r = client.post(f"/focus-sessions/{session_id}/break/start", headers=auth_headers(user))
    assert r.json()["break_is_penalized"] is False

    r = client.post(f"/focus-sessions/{session_id}/break/end", headers=auth_headers(user))
    body = r.json()
    assert body["penalty_applied"] is False
    assert body["penalty_seconds"] == 0
    assert body["session"]["planned_duration_seconds"] == planned_before


def test_cannot_start_a_second_break_while_already_on_break(client):
    user = register(client)
    r = client.post("/focus-sessions/start", json={"duration_minutes": 30}, headers=auth_headers(user))
    session_id = r.json()["id"]
    client.post(f"/focus-sessions/{session_id}/break/start", headers=auth_headers(user))
    r = client.post(f"/focus-sessions/{session_id}/break/start", headers=auth_headers(user))
    assert r.status_code == 400


def test_cannot_end_a_break_that_was_never_started(client):
    user = register(client)
    r = client.post("/focus-sessions/start", json={"duration_minutes": 30}, headers=auth_headers(user))
    session_id = r.json()["id"]
    r = client.post(f"/focus-sessions/{session_id}/break/end", headers=auth_headers(user))
    assert r.status_code == 400


def test_distraction_time_does_not_accrue_while_on_break(client):
    """A user is sanctioned to be away during a break - being on a
    'distraction' live-status reading while paused should not count
    against the session's distraction grace period."""
    user = register(client)
    r = client.post("/focus-sessions/start", json={"duration_minutes": 30}, headers=auth_headers(user))
    session_id = r.json()["id"]
    client.post(f"/focus-sessions/{session_id}/break/start", headers=auth_headers(user))

    client.put("/live-status", json={
        "source": "system", "name": "Instagram", "category": "distraction",
    }, headers=auth_headers(user))
    _backdate_distraction_clock(user["user_id"], seconds_ago=61)

    r = client.get("/focus-sessions/active", headers=auth_headers(user))
    assert r.json()["status"] == "active"  # not broken - distraction clock was skipped while on break


# ---- Insights name the top distraction app (Feature 8) ----

def test_insight_prompt_includes_top_distraction_app_and_asks_for_motivation(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("CHEAPER_INFERENCE_API_KEY", raising=False)
    user = register(client)
    _seed_session(client, user, "Instagram", "distraction", 3600)

    captured = []

    def fake_anthropic(prompt):
        captured.append(prompt)
        return "You did great!"

    monkeypatch.setattr(main_module, "_try_anthropic", fake_anthropic)
    r = client.get(f"/insights/{user['user_id']}", headers=auth_headers(user))
    assert r.status_code == 200
    prompt = captured[-1]
    assert "Instagram" in prompt
    assert "motivational" in prompt.lower()


# ---- Device link: one account shared by every local tracker ----

def test_device_link_shares_dashboard_account_with_local_trackers(client):
    user = register(client)
    assert client.get("/device-link").status_code == 404

    assert client.post("/device-link", headers=auth_headers(user)).status_code == 204
    r = client.get("/device-link")
    assert r.status_code == 200
    assert r.json() == {"user_id": user["user_id"], "username": "alice", "api_token": user["api_token"]}

    # The extension (its own origin) may read it too.
    r = client.get("/device-link", headers={"Origin": "chrome-extension://abcdef"})
    assert r.status_code == 200

    # Signing in as someone else moves the link; signing out clears it.
    bob = register(client, "bob")
    client.post("/device-link", headers=auth_headers(bob))
    assert client.get("/device-link").json()["username"] == "bob"
    client.delete("/device-link", headers=auth_headers(bob))
    assert client.get("/device-link").status_code == 404


def test_device_link_token_is_never_readable_by_web_pages(client):
    user = register(client)
    client.post("/device-link", headers=auth_headers(user))
    r = client.get("/device-link", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.get("/device-link", headers={"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "no-cors"})
    assert r.status_code == 403


def test_tracker_status_reports_browsers_the_extension_covers(client):
    user = register(client)
    assert client.get("/tracker/status", headers=auth_headers(user)).json() == {"extension_browsers": []}
    client.post("/extension/ping", json={"client": "chrome"}, headers=auth_headers(user))
    client.put("/live-status", json={"source": "extension", "name": "github.com",
                                     "category": "productive", "client": "msedge"}, headers=auth_headers(user))
    r = client.get("/tracker/status", headers=auth_headers(user))
    assert r.json() == {"extension_browsers": ["chrome", "msedge"]}


# ---- Static site lists: classify well-known sites with no LLM at all ----

def test_classify_domain_uses_static_lists_without_llm(client, monkeypatch):
    user = register(client)
    monkeypatch.setattr(main_module, "_classify_category_via_llm",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM should not be called")))
    for domain, expected in [("instagram.com", "non_educational"), ("m.instagram.com", "non_educational"),
                             ("leetcode.com", "educational"), ("docs.google.com", "educational"),
                             ("youtube.com", "unknown")]:
        r = client.post("/classify-domain", json={"domain": domain}, headers=auth_headers(user))
        assert r.json()["category"] == expected, domain


def test_title_keywords_match_whole_words_only(client, monkeypatch):
    user = register(client)
    monkeypatch.setattr(main_module, "_classify_category_via_llm", lambda *a, **k: None)
    r = client.post("/classify-domain", json={"domain": "youtube.com", "title": "Class 12 Physics One Shot - YouTube"},
                    headers=auth_headers(user))
    assert r.json()["category"] == "educational"
    r = client.post("/classify-domain", json={"domain": "youtube.com", "title": "Reactive dogs denote happiness"},
                    headers=auth_headers(user))
    assert r.json()["category"] == "unknown"


def test_leave_group_then_join_another(client):
    alice = register(client)
    bob = register(client, "bob")
    first = client.post("/groups", json={"name": "Study Squad"}, headers=auth_headers(alice)).json()
    second = client.post("/groups", json={"name": "Night Owls"}, headers=auth_headers(bob)).json()
    client.post("/groups/join", json={"join_code": first["join_code"]}, headers=auth_headers(bob))

    assert client.post("/groups/leave", headers=auth_headers(alice)).status_code == 204
    assert client.get("/groups/me", headers=auth_headers(alice)).status_code == 404
    # The group carries on for its remaining members.
    board = client.get("/leaderboard", headers=auth_headers(bob)).json()
    assert [e["username"] for e in board["entries"]] == ["bob"]

    client.post("/groups/join", json={"join_code": second["join_code"]}, headers=auth_headers(alice))
    assert client.get("/groups/me", headers=auth_headers(alice)).json()["name"] == "Night Owls"


# ---- Badges ----

def test_badges_start_locked_with_progress(client):
    user = register(client)
    r = client.get(f"/badges/{user['user_id']}", headers=auth_headers(user))
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 15 and data["earned_count"] == 0
    hours = next(b for b in data["badges"] if b["id"] == "ten_hour_club")
    assert hours == {"id": "ten_hour_club", "tier": 1, "earned": False, "progress": 0, "target": 10}


def test_badges_unlock_from_real_activity(client):
    user = register(client)
    _seed_session(client, user, "VS Code", "productive", 2 * 3600)  # zen day: 2h, no distraction switches
    client.post("/sessions", json={"source": "system", "name": "Notes", "category": "productive",
                                    "start_time": "05:45", "end_time": "06:30", "duration": 2700}, headers=auth_headers(user))
    client.post("/groups", json={"name": "Solo"}, headers=auth_headers(user))
    data = client.get(f"/badges/{user['user_id']}", headers=auth_headers(user)).json()
    earned = {b["id"] for b in data["badges"] if b["earned"]}
    assert {"zen_master", "early_bird", "squad_up"} <= earned
    assert "top_of_pack" not in earned  # needs at least one groupmate to beat
    assert "first_spark" not in earned


def test_cannot_view_another_users_badges(client):
    alice, bob = register(client), register(client, "bob")
    assert client.get(f"/badges/{bob['user_id']}", headers=auth_headers(alice)).status_code == 403


# ---- Online (cloud) mode ----

def test_cloud_mode_disables_single_machine_device_link(client, monkeypatch):
    """Deployed online, many people share one server: signing in must not
    link anyone's account to "this machine" or start a tracker on the
    server, and the token handout must stay closed."""
    monkeypatch.setattr(main_module, "CLOUD_MODE", True)
    spawned = []
    monkeypatch.setattr(main_module.subprocess, "Popen", lambda *a, **k: spawned.append(a))
    user = register(client)
    assert client.post("/device-link", headers=auth_headers(user)).status_code == 204
    assert client.get("/device-link").status_code == 404
    assert client.delete("/device-link", headers=auth_headers(user)).status_code == 204
    assert spawned == []
    db = SessionLocal()
    assert db.query(main_module.DeviceLink).count() == 0
    db.close()
