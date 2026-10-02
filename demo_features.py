"""
demo_features.py

Shows a clearly labeled, individual output for each of the 6 features -
useful for a demo/report to your mentor without needing to run the full
tracker loop or wait for real events to happen naturally.

Requires the backend running and TRACKER_BACKEND_URL / TRACKER_USERNAME /
TRACKER_PASSWORD set, same as window_tracker.py. Run it after you've
tracked at least a little real activity (and joined/created a group) so
Features 2, 3, and 5 have something real to show - otherwise they'll
correctly report "no data yet" rather than fake numbers.

Usage:
    python demo_features.py
"""

from __future__ import annotations

import sys
from backend_client import BackendClient
from notifier import DesktopNotifier


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def feature_1_notifications(notifier: DesktopNotifier) -> None:
    section("Feature 1 - Real-Time Distraction Notifications")
    print("Firing a real test notification now...")
    notifier.notify(
        title="Feature 1 demo",
        message="This is what a distraction alert looks like as a desktop notification.",
    )
    print("If desktop notifications are supported on this machine, a popup "
          "should have just appeared. If not, this text is the fallback.")


def feature_2_streaks(backend: BackendClient) -> None:
    section("Feature 2 - Focus Streaks & Badges")
    data = backend.get_streaks()
    if data is None:
        print("Could not fetch streak data (backend unreachable or no account).")
        return
    print(f"Current streak: {data['current_streak']} day(s)")
    print(f"Longest streak ever: {data['longest_streak']} day(s)")
    if data["badges"]:
        print(f"Badges earned: {', '.join(data['badges'])}")
    else:
        print("Badges earned: none yet")
    print(f"\nDay-by-day (most recent {len(data['days'])} tracked days):")
    for day in data["days"]:
        mark = "SUCCESS" if day["is_success"] else "MISSED"
        print(f"  {day['date']}  [{mark}]  "
              f"productive={day['productive_seconds']}s  "
              f"distraction_switches={day['distraction_switches']}")


def feature_3_leaderboard(backend: BackendClient) -> None:
    section("Feature 3 - Leaderboard")
    data = backend.get_leaderboard()
    if data is None:
        print("No group joined yet, or backend unreachable. Try:")
        print("  python window_tracker.py --create-group \"My Group\"")
        return
    print(f"Group: {data['group_name']}  (last {data['days']} days)\n")
    for entry in data["entries"]:
        print(f"  #{entry['rank']}  {entry['username']:<20} {entry['focus_score']}% focus "
              f"(productive={entry['productive_seconds']}s, distraction={entry['distraction_seconds']}s)")


def feature_4_focus_mode(backend: BackendClient) -> None:
    section("Feature 4 - Focus Mode")
    print("Starting a short (0-minute, for demo purposes) focus session...")
    session = backend.start_focus_session(0)
    if session is None:
        print("Could not start a focus session (backend unreachable, or one's already active).")
        return
    print(f"Session id={session['id']} status={session['status']}")
    print("Ending it now to show how a completed session looks...")
    result = backend.end_focus_session(session["id"])
    if result:
        print(f"Final status: {result['status']}")
        print(f"Elapsed: {result['elapsed_seconds']}s | "
              f"Distraction time accumulated: {result['distraction_seconds_accumulated']}s")
    print("\n(In real use: 'python window_tracker.py --focus 25' runs this live for "
          "25 real minutes, breaking once 60s of cumulative time on a distraction "
          "tab/app has passed - brief distractions are tolerated, not instant-broken.)")


def feature_5_insights(backend: BackendClient) -> None:
    section("Feature 5 - Weekly AI Insight Report")
    print("Fetching (this may call the AI the first time today)...")
    report = backend.get_insights(days=7)
    if report is None:
        print("Could not fetch insights (backend unreachable).")
        return
    totals = report["category_totals_seconds"]
    print(f"Last {report['days']} days ({'cached' if report['cached'] else 'freshly generated'}):")
    print(f"  Productive:  {totals['productive'] // 60} min")
    print(f"  Distraction: {totals['distraction'] // 60} min")
    print(f"  Neutral:     {totals['neutral'] // 60} min")
    print(f"  Sessions tracked: {report['session_count']}")
    print(f"  Switches: {report['total_switch_count']} total, "
          f"{report['distraction_switch_count']} into distracting apps")
    print(f"\n  AI summary: {report['insight_text']}")


def feature_6_break_reminder(notifier: DesktopNotifier) -> None:
    section("Feature 6 - Smart Break Reminders")
    print("This triggers automatically after 50 minutes of unbroken productive "
          "time (configurable with --break-reminder-minutes) - not something "
          "with a stored value to fetch, so here's a live example of what it "
          "looks like when it fires:")
    notifier.notify(
        title="Time for a quick break?",
        message="You've been focused for 50 min - a short break helps you sustain this.",
    )
    print("If desktop notifications are supported, a popup should have just appeared.")


def main() -> None:
    backend = BackendClient()
    notifier = DesktopNotifier()

    if not backend.enabled:
        print("[error] Backend not configured or unreachable.", file=sys.stderr)
        print("Set TRACKER_BACKEND_URL, TRACKER_USERNAME, TRACKER_PASSWORD first, "
              "and make sure `uvicorn main:app --port 8000` is running.", file=sys.stderr)
        sys.exit(1)

    print(f"Connected as user_id={backend.user_id}")

    feature_1_notifications(notifier)
    feature_2_streaks(backend)
    feature_3_leaderboard(backend)
    feature_4_focus_mode(backend)
    feature_5_insights(backend)
    feature_6_break_reminder(notifier)

    print(f"\n{'=' * 60}")
    print("  Demo complete - all 6 features shown above.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
