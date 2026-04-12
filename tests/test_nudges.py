"""Tests for `focusmonitor.nudges`.

The module fires `osascript` to post macOS notifications. We monkey-patch
`subprocess.run` to avoid touching the real notification system during
tests — the goal is to verify the decision logic (who gets nudged, when,
and whether we rate-limit), not the macOS side effect.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

import pytest

from focusmonitor import config, nudges


def _make_db():
    db = sqlite3.connect(":memory:")
    db.execute("""CREATE TABLE activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, window_titles TEXT, apps_used TEXT,
        project_detected TEXT, is_distraction INTEGER, summary TEXT, raw_response TEXT
    )""")
    db.execute("""CREATE TABLE nudges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, task TEXT, message TEXT
    )""")
    return db


@pytest.fixture
def capture_osascript(monkeypatch):
    """Replace subprocess.run with a capture stub."""
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        class _R:
            returncode = 0
            stdout = b""
            stderr = b""
        return _R()

    monkeypatch.setattr("focusmonitor.nudges.subprocess.run", fake_run)
    return calls


# ── send_nudge ───────────────────────────────────────────────────────────────

class TestSendNudge:

    def test_fires_osascript_and_records_nudge(self, capture_osascript):
        db = _make_db()
        nudges.send_nudge({}, db, "Sanskrit Tool")
        assert len(capture_osascript) == 1
        cmd = capture_osascript[0]
        assert cmd[0] == "osascript"
        assert "Sanskrit Tool" in cmd[-1]
        count = db.execute("SELECT COUNT(*) FROM nudges WHERE task = ?",
                           ("Sanskrit Tool",)).fetchone()[0]
        assert count == 1
        db.close()

    def test_rate_limits_within_an_hour(self, capture_osascript):
        db = _make_db()
        # Pre-seed a recent nudge for the same task.
        recent_ts = (datetime.now() - timedelta(minutes=10)).isoformat()
        db.execute("INSERT INTO nudges (timestamp, task, message) VALUES (?, ?, ?)",
                   (recent_ts, "Sanskrit Tool", "earlier"))
        db.commit()

        nudges.send_nudge({}, db, "Sanskrit Tool")
        assert capture_osascript == []  # no osascript fired
        count = db.execute("SELECT COUNT(*) FROM nudges").fetchone()[0]
        assert count == 1  # no new row
        db.close()

    def test_sends_again_after_rate_limit_window(self, capture_osascript):
        db = _make_db()
        # Seed a nudge older than the 1-hour rate-limit window.
        stale_ts = (datetime.now() - timedelta(hours=2)).isoformat()
        db.execute("INSERT INTO nudges (timestamp, task, message) VALUES (?, ?, ?)",
                   (stale_ts, "Sanskrit Tool", "older"))
        db.commit()

        nudges.send_nudge({}, db, "Sanskrit Tool")
        assert len(capture_osascript) == 1
        count = db.execute("SELECT COUNT(*) FROM nudges").fetchone()[0]
        assert count == 2
        db.close()


# ── check_nudges ─────────────────────────────────────────────────────────────

class TestCheckNudges:

    def test_no_tasks_no_nudges(self, tmp_home, capture_osascript):
        db = _make_db()
        # No planned_tasks.json → load_planned_tasks returns []
        nudges.check_nudges({"nudge_after_hours": 2}, db, {})
        assert capture_osascript == []
        db.close()

    def test_task_recently_worked_on_no_nudge(self, tmp_home, capture_osascript):
        config.TASKS_JSON_FILE.write_text(json.dumps([
            {"name": "Focus Monitor", "signals": [], "apps": [], "notes": ""},
        ]))
        db = _make_db()
        # Insert a recent row that mentions the task.
        recent = (datetime.now() - timedelta(minutes=30)).isoformat()
        db.execute(
            "INSERT INTO activity_log (timestamp, project_detected) VALUES (?, ?)",
            (recent, json.dumps(["focus monitor"])),
        )
        db.commit()
        nudges.check_nudges({"nudge_after_hours": 2}, db, {})
        assert capture_osascript == []
        db.close()

    def test_task_untouched_gets_nudged(self, tmp_home, capture_osascript):
        config.TASKS_JSON_FILE.write_text(json.dumps([
            {"name": "Untouched Task", "signals": [], "apps": [], "notes": ""},
        ]))
        db = _make_db()
        # Insert a recent row that mentions a DIFFERENT project.
        recent = (datetime.now() - timedelta(minutes=30)).isoformat()
        db.execute(
            "INSERT INTO activity_log (timestamp, project_detected) VALUES (?, ?)",
            (recent, json.dumps(["something else"])),
        )
        db.commit()
        nudges.check_nudges({"nudge_after_hours": 2}, db, {})
        assert len(capture_osascript) == 1
        assert "Untouched Task" in capture_osascript[0][-1]
        db.close()

    def test_malformed_project_detected_is_ignored(
        self, tmp_home, capture_osascript
    ):
        """A row with invalid JSON in project_detected should not crash the
        nudge path — it should be silently skipped."""
        config.TASKS_JSON_FILE.write_text(json.dumps([
            {"name": "Task", "signals": [], "apps": [], "notes": ""},
        ]))
        db = _make_db()
        recent = (datetime.now() - timedelta(minutes=30)).isoformat()
        db.execute(
            "INSERT INTO activity_log (timestamp, project_detected) VALUES (?, ?)",
            (recent, "not-json"),
        )
        db.commit()
        # Must not raise. Task will be considered "not seen" and get nudged.
        nudges.check_nudges({"nudge_after_hours": 2}, db, {})
        db.close()
