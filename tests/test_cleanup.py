"""Tests for periodic data cleanup functions.

Covers:
  - `cleanup_old_db_rows`  — retention by days against a real sqlite3 DB
  - `cleanup_log_files`     — size-based log truncation against real files
  - `run_cleanup`           — end-to-end orchestrator
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from focusmonitor import cleanup, config
from focusmonitor.config import DEFAULT_CONFIG


# ── DB cleanup ───────────────────────────────────────────────────────────────

def _make_schema(db):
    db.execute("""CREATE TABLE activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, window_titles TEXT, apps_used TEXT,
        project_detected TEXT, is_distraction INTEGER, summary TEXT, raw_response TEXT
    )""")
    db.execute("""CREATE TABLE nudges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, task TEXT, message TEXT
    )""")
    db.execute("""CREATE TABLE analysis_traces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        activity_log_id INTEGER, created_at TEXT,
        pass1_prompts_json TEXT, pass1_responses_json TEXT,
        pass1_elapsed_ms_json TEXT, pass2_prompt TEXT,
        pass2_response_raw TEXT, pass2_elapsed_ms REAL,
        few_shot_ids_json TEXT, screenshot_paths_json TEXT,
        parse_retries INTEGER DEFAULT 0
    )""")


@pytest.fixture
def memdb():
    """In-memory SQLite with the focus-monitor schema."""
    db = sqlite3.connect(":memory:")
    _make_schema(db)
    yield db
    db.close()


class TestCleanupOldDbRows:

    def test_deletes_old_rows_and_nudges(self, memdb):
        old_ts = (datetime.now() - timedelta(days=60)).isoformat()
        recent_ts = (datetime.now() - timedelta(days=5)).isoformat()
        now_ts = datetime.now().isoformat()

        memdb.execute("INSERT INTO activity_log (timestamp, summary) VALUES (?, 'old')", (old_ts,))
        memdb.execute("INSERT INTO activity_log (timestamp, summary) VALUES (?, 'recent')", (recent_ts,))
        memdb.execute("INSERT INTO activity_log (timestamp, summary) VALUES (?, 'now')", (now_ts,))
        memdb.execute("INSERT INTO nudges (timestamp, task) VALUES (?, 'old')", (old_ts,))
        memdb.execute("INSERT INTO nudges (timestamp, task) VALUES (?, 'new')", (now_ts,))
        memdb.commit()

        deleted = cleanup.cleanup_old_db_rows({"db_retention_days": 30}, memdb)
        assert deleted == 2  # 1 activity_log + 1 nudges

        assert memdb.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0] == 2
        assert memdb.execute("SELECT COUNT(*) FROM nudges").fetchone()[0] == 1

    def test_disabled_returns_zero(self, memdb):
        assert cleanup.cleanup_old_db_rows({"db_retention_days": 0}, memdb) == 0

    def test_deletes_old_analysis_traces(self, memdb):
        old_ts = (datetime.now() - timedelta(days=60)).isoformat()
        recent_ts = (datetime.now() - timedelta(days=5)).isoformat()

        memdb.execute(
            "INSERT INTO analysis_traces (activity_log_id, created_at, pass2_prompt) "
            "VALUES (1, ?, 'old prompt')", (old_ts,)
        )
        memdb.execute(
            "INSERT INTO analysis_traces (activity_log_id, created_at, pass2_prompt) "
            "VALUES (2, ?, 'recent prompt')", (recent_ts,)
        )
        memdb.commit()

        deleted = cleanup.cleanup_old_db_rows({"db_retention_days": 30}, memdb)
        assert deleted >= 1  # at least the old trace row
        assert memdb.execute("SELECT COUNT(*) FROM analysis_traces").fetchone()[0] == 1

    def test_custom_retention_days(self, memdb):
        ts_5d = (datetime.now() - timedelta(days=5)).isoformat()
        ts_now = datetime.now().isoformat()
        memdb.execute("INSERT INTO activity_log (timestamp, summary) VALUES (?, 'old')", (ts_5d,))
        memdb.execute("INSERT INTO activity_log (timestamp, summary) VALUES (?, 'now')", (ts_now,))
        memdb.commit()
        assert cleanup.cleanup_old_db_rows({"db_retention_days": 3}, memdb) == 1
        assert memdb.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0] == 1


# ── Log file truncation ──────────────────────────────────────────────────────

class TestCleanupLogFiles:

    def test_truncates_oversized_log(self, tmp_home):
        big = config.LOG_DIR / "stdout.log"
        small = config.LOG_DIR / "stderr.log"
        big.write_bytes(b"A" * (6 * 1024 * 1024))   # 6 MB
        small.write_bytes(b"B" * (100 * 1024))       # 100 KB

        truncated = cleanup.cleanup_log_files({"log_max_size_mb": 5})
        assert truncated == 1
        assert big.stat().st_size == 1 * 1024 * 1024
        assert small.stat().st_size == 100 * 1024

    def test_preserves_tail_content(self, tmp_home):
        log = config.LOG_DIR / "stdout.log"
        log.write_bytes(b"X" * (5 * 1024 * 1024) + b"TAIL_CONTENT")
        cleanup.cleanup_log_files({"log_max_size_mb": 5})
        assert log.read_bytes().endswith(b"TAIL_CONTENT")

    def test_disabled_returns_zero(self, tmp_home):
        log = config.LOG_DIR / "stdout.log"
        log.write_bytes(b"C" * (10 * 1024 * 1024))
        assert cleanup.cleanup_log_files({"log_max_size_mb": 0}) == 0
        assert log.stat().st_size == 10 * 1024 * 1024

    def test_missing_log_files_are_handled(self, tmp_home):
        # LOG_DIR exists (tmp_home creates it) but is empty.
        assert cleanup.cleanup_log_files({"log_max_size_mb": 5}) == 0


# ── run_cleanup integration ──────────────────────────────────────────────────

class TestRunCleanup:

    def test_completes_on_empty_db(self, memdb, tmp_home):
        full_cfg = DEFAULT_CONFIG.copy()
        cleanup.run_cleanup(full_cfg, memdb)  # must not raise

    def test_prunes_db_end_to_end(self, memdb, tmp_home):
        old = (datetime.now() - timedelta(days=60)).isoformat()
        memdb.execute("INSERT INTO activity_log (timestamp, summary) VALUES (?, 'old')", (old,))
        memdb.commit()
        cleanup.run_cleanup(DEFAULT_CONFIG.copy(), memdb)
        assert memdb.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0] == 0


# ── DEFAULT_CONFIG pins ──────────────────────────────────────────────────────

class TestDefaultConfigCleanupKeys:

    def test_db_retention_days(self):
        assert DEFAULT_CONFIG["db_retention_days"] == 30

    def test_log_max_size_mb(self):
        assert DEFAULT_CONFIG["log_max_size_mb"] == 5
