"""Seeded-SQLite factory for tests.

Provides a pytest fixture that yields a sqlite3 connection with the full
focus-monitor schema applied and optional seed rows inserted. Tests that
just need an empty DB can use `db`; tests that need a reproducible corpus
use `seeded_db`.

The database lives under the per-test `tmp_home` directory, so paths in
`focusmonitor.config` resolve correctly without any additional patching.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

import pytest

from focusmonitor.db import init_db


# A deterministic timestamp used throughout test fixtures so rendered
# output (dashboard snapshots, summaries) is byte-stable across runs.
SEED_NOW = datetime(2026, 4, 12, 15, 0, 0)


def _seed_rows(db: sqlite3.Connection) -> None:
    """Insert a small, hand-picked activity_log corpus.

    Two focused entries on a real planned task, one distraction entry, one
    unknown/low-focus entry. Enough to exercise every dashboard code path
    without being so large that the snapshot becomes unreadable.
    """
    rows = [
        (
            "2026-04-12T09:30:00",
            json.dumps(["focus-monitor — VS Code", "zsh"]),
            json.dumps(["Code", "Terminal"]),
            json.dumps(["focus-monitor"]),
            0,
            "Worked on the test harness — added pytest config and fixtures.",
            json.dumps({
                "projects": ["focus-monitor"],
                "planned_match": ["focus-monitor"],
                "distractions": [],
                "summary": "Worked on the test harness — added pytest config and fixtures.",
                "focus_score": 85,
            }),
        ),
        (
            "2026-04-12T10:00:00",
            json.dumps(["focus-monitor — dashboard.py", "git status"]),
            json.dumps(["Code", "Terminal"]),
            json.dumps(["focus-monitor"]),
            0,
            "Refactored dashboard render helpers.",
            json.dumps({
                "projects": ["focus-monitor"],
                "planned_match": ["focus-monitor"],
                "distractions": [],
                "summary": "Refactored dashboard render helpers.",
                "focus_score": 90,
            }),
        ),
        (
            "2026-04-12T11:30:00",
            json.dumps(["Hacker News", "Twitter"]),
            json.dumps(["Safari"]),
            json.dumps(["news"]),
            1,
            "Browsed news and social media.",
            json.dumps({
                "projects": ["news"],
                "planned_match": [],
                "distractions": ["news", "social media"],
                "summary": "Browsed news and social media.",
                "focus_score": 15,
            }),
        ),
        (
            "2026-04-12T13:00:00",
            json.dumps(["unknown window"]),
            json.dumps(["unknown"]),
            json.dumps([]),
            0,
            "Brief unclassified activity.",
            json.dumps({
                "projects": [],
                "planned_match": [],
                "distractions": [],
                "summary": "Brief unclassified activity.",
                "focus_score": 45,
            }),
        ),
    ]
    db.executemany(
        """
        INSERT INTO activity_log (
            timestamp, window_titles, apps_used, project_detected,
            is_distraction, summary, raw_response
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    db.commit()


@pytest.fixture
def db(tmp_home):
    """Empty DB with the schema applied. Per-test lifetime."""
    conn = init_db()
    yield conn
    conn.close()


@pytest.fixture
def seeded_db(tmp_home):
    """DB populated with a deterministic corpus. Per-test lifetime."""
    conn = init_db()
    _seed_rows(conn)
    yield conn
    conn.close()
