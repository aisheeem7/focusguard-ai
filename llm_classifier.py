"""
llm_classifier.py

Falls back to Claude Haiku to classify apps/window names that aren't
covered by app_categories.json, so the tracker doesn't need a manually
maintained list to cover every possible app or website.

Results are cached in learned_categories.json (created automatically),
keyed by lowercased app name, so each unique app is only ever classified
once - not once per switch.

Setup:
    pip install anthropic
    Set the ANTHROPIC_API_KEY environment variable:
        Mac/Linux:  export ANTHROPIC_API_KEY=your_key_here
        Windows:    setx ANTHROPIC_API_KEY "your_key_here"   (restart terminal after)

If no API key is set or the 'anthropic' package isn't installed, the
classifier silently disables itself and unrecognized apps default to
"neutral" - the rest of the tracker still works normally.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

CACHE_PATH = Path(__file__).with_name("learned_categories.json")
VALID_LABELS = {"productive", "distraction", "ambiguous", "neutral"}

CLASSIFICATION_PROMPT = """You are classifying a desktop application or browser window/tab name for a personal productivity tracker.

Name: "{app_name}"

Classify it as exactly ONE of these four labels:
- productive: work/coding/study tools - IDEs, terminals, code hosting, coding practice sites, office/document tools, project management, study/learning platforms, design tools used for work
- distraction: social media, entertainment streaming, games, casual browsing sites
- ambiguous: apps that could go either way depending on how they're used right now, such as a generic photo gallery, a video platform, or a general-purpose media player
- neutral: system utilities, file managers, communication apps, or anything else that's neither clearly productive nor clearly distracting

Respond with ONLY the single label word (productive, distraction, ambiguous, or neutral) and nothing else."""


class LLMClassifier:
    def __init__(self, cache_path: Path = CACHE_PATH, enabled: bool = True):
        self.cache_path = cache_path
        self.cache: dict[str, str] = {}
        self.enabled = enabled
        self._client = None
        self._load_cache()
        if self.enabled:
            self._init_client()

    def _load_cache(self) -> None:
        if self.cache_path.exists():
            try:
                self.cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.cache = {}

    def _save_cache(self) -> None:
        try:
            self.cache_path.write_text(json.dumps(self.cache, indent=2), encoding="utf-8")
        except OSError as exc:
            print(f"[warn] Could not write {self.cache_path}: {exc}", file=sys.stderr)

    def _init_client(self) -> None:
        import os
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print(
                "[info] ANTHROPIC_API_KEY not set - LLM auto-classification disabled; "
                "unrecognized apps will default to 'neutral'. Add them to "
                "app_categories.json manually, or set the API key to enable "
                "auto-classification.",
                file=sys.stderr,
            )
            self.enabled = False
            return
        try:
            import anthropic
            self._client = anthropic.Anthropic()
        except ImportError:
            print(
                "[warn] 'anthropic' package not installed (pip install anthropic) - "
                "LLM auto-classification disabled.",
                file=sys.stderr,
            )
            self.enabled = False

    def classify(self, app_name: str) -> str:
        key = app_name.strip().lower()
        if key in self.cache:
            return self.cache[key]

        if not self.enabled or self._client is None:
            return "neutral"

        label = self._call_model(app_name)
        self.cache[key] = label
        self._save_cache()
        return label

    def _call_model(self, app_name: str) -> str:
        try:
            resp = self._client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=10,
                messages=[{"role": "user", "content": CLASSIFICATION_PROMPT.format(app_name=app_name)}],
            )
            label = resp.content[0].text.strip().lower()
            if label not in VALID_LABELS:
                label = "neutral"
            return label
        except Exception as exc:
            print(f"[warn] LLM classification failed for '{app_name}': {exc}", file=sys.stderr)
            return "neutral"
