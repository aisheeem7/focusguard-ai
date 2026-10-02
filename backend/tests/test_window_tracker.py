"""
test_window_tracker.py

How the desktop tracker names and classifies apps - by program rather
than by window title, without false substring matches, and without ever
making its polling loop wait on an online server.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import window_tracker as wt  # noqa: E402

AW = wt.ActiveWindow


class FakeBackend:
    enabled = True

    def __init__(self, online=False, delay=0.0, answer="productive"):
        self.online = online
        self.delay = delay
        self.answer = answer
        self.calls = []
        self.sessions, self.switches = [], []

    def classify(self, name):
        self.calls.append(name)
        time.sleep(self.delay)
        return self.answer

    def classify_title(self, title):
        self.calls.append(title)
        time.sleep(self.delay)
        return self.answer

    def post_session(self, record):
        self.sessions.append((record["name"], record["category"]))

    def post_switch(self, record):
        self.switches.append((record["from_app"], record["to_app"], record["category"]))

    def post_live_status(self, name, category):
        pass


def make_tracker(backend, tmp_path):
    categorizer = wt.AppCategorizer(backend=backend)
    return wt.WindowTracker(out_path=tmp_path / "a.jsonl", switch_out_path=tmp_path / "s.jsonl",
                            categorizer=categorizer, use_ui=False, backend=backend, interactive=False)


def test_desktop_apps_are_named_after_the_program_not_the_document(tmp_path):
    tracker = make_tracker(FakeBackend(), tmp_path)
    word = AW("WINWORD - Report.docx - Word", "WINWORD", "Report.docx - Word", "Microsoft Word")
    explorer = AW("Downloads - File Explorer", "explorer", "Downloads - File Explorer", "Windows Explorer")
    assert tracker._identify(word, None) == ("Microsoft Word", None, "productive")
    assert tracker._identify(explorer, None) == ("File Explorer", None, "neutral")
    # Unknown programs use their own file description, not the title.
    tool = AW("SomeTool - draft 3", "SomeTool", "draft 3", "Some Tool Pro")
    assert tracker._identify(tool, None)[0] == "Some Tool Pro"
    # Media players keep what's playing, since that decides the category.
    vlc = AW("vlc - lecture.mp4 - VLC media player", "vlc", "lecture.mp4 - VLC media player", "VLC media player")
    assert tracker._identify(vlc, None) == ("lecture.mp4 - VLC media player", None, "ambiguous")


def test_opening_another_folder_is_not_a_switch(tmp_path):
    backend = FakeBackend()
    tracker = make_tracker(backend, tmp_path)
    for title in ("Downloads - File Explorer", "Documents - File Explorer"):
        window = AW(title, "explorer", title, "Windows Explorer")
        name, page, known = tracker._identify(window, None)
        tracker._switch(name, page_title=page, known_category=known, process=window.process)
    assert tracker.total_switch_count == 0
    assert tracker._current.name == "File Explorer"


def test_lists_match_whole_words_only():
    categorizer = wt.AppCategorizer(backend=None)
    assert categorizer.raw_categorize("Password Manager") == "neutral"  # not "word"
    assert categorizer.raw_categorize("Digital Art Studio") == "neutral"  # not "git"
    assert categorizer.raw_categorize("WINWORD - Essay - Word") == "productive"


def test_shell_helpers_are_ignored_but_file_explorer_is_not():
    categorizer = wt.AppCategorizer(backend=None)
    assert categorizer.should_ignore("Search", "SearchHost")
    assert not categorizer.should_ignore("File Explorer", "explorer")


def test_online_lookup_never_blocks_the_polling_loop(tmp_path):
    backend = FakeBackend(online=True, delay=0.5)
    tracker = make_tracker(backend, tmp_path)
    tracker._switch("Microsoft Word", known_category="productive")

    started = time.monotonic()
    tracker._switch("Some Tool Pro")
    assert time.monotonic() - started < 0.2
    assert tracker._current.category == "neutral"  # provisional
    assert backend.switches == []  # logged once the category is known

    time.sleep(0.7)
    tracker._check_pending_category()
    assert tracker._current.category == "productive"
    assert backend.switches == [("Microsoft Word", "Some Tool Pro", "productive")]

    # Cached: the next visit is classified instantly, with no new lookup.
    tracker._switch("Microsoft Word", known_category="productive")
    tracker._switch("Some Tool Pro")
    assert tracker._current.category == "productive"
    assert backend.calls == ["Some Tool Pro"]


def test_idle_time_is_not_counted(tmp_path, monkeypatch):
    backend = FakeBackend()
    tracker = make_tracker(backend, tmp_path)
    window = AW("WINWORD - Essay - Word", "WINWORD", "Essay - Word", "Microsoft Word")
    monkeypatch.setattr(wt, "get_active_window", lambda: window)
    monkeypatch.setattr(wt, "seconds_since_last_input", lambda: 1.0)
    tracker._poll_window()
    tracker._current.start_dt -= wt.timedelta(minutes=20)

    monkeypatch.setattr(wt, "seconds_since_last_input", lambda: 10 * 60.0)
    tracker._poll_window()
    assert tracker._current is None
    record = [line for line in Path(tmp_path / "a.jsonl").read_text().splitlines()][-1]
    duration = wt.json.loads(record)["duration"]
    assert 9 * 60 <= duration <= 10 * 60 + 5  # ends at the last input, not now

    # Coming back to the same app isn't a switch.
    monkeypatch.setattr(wt, "seconds_since_last_input", lambda: 0.5)
    tracker._poll_window()
    assert tracker._current.name == "Microsoft Word"
    assert tracker.total_switch_count == 0
