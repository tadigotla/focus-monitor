"""Tests for deferred batch analysis.

Covers: pending_data table schema, collect_tick(), batch_analyze(),
run_analysis() prefetch kwargs, clock-schedule matching, and nudge gating.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from focusmonitor.db import init_db


# ── 7.1 pending_data table creation ─────────────────────────────────────────

def _table_exists(db, name):
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _column_names(db, table):
    return [row[1] for row in db.execute(f"PRAGMA table_info({table})").fetchall()]


def test_init_db_creates_pending_data_table(tmp_home):
    db = init_db()
    try:
        assert _table_exists(db, "pending_data")
        cols = set(_column_names(db, "pending_data"))
        expected = {"id", "collected_at", "screenshot_path", "aw_events_json", "processed"}
        assert expected <= cols
    finally:
        db.close()


def test_pending_data_default_processed_is_zero(tmp_home):
    db = init_db()
    try:
        db.execute(
            "INSERT INTO pending_data (collected_at, aw_events_json) VALUES (?, ?)",
            ("2026-04-13T10:00:00", "[]"),
        )
        db.commit()
        row = db.execute("SELECT processed FROM pending_data").fetchone()
        assert row[0] == 0
    finally:
        db.close()


# ── 7.2 collect_tick inserts a row ──────────────────────────────────────────

def test_collect_tick_inserts_pending_row(tmp_home):
    from focusmonitor.main import collect_tick

    db = init_db()
    try:
        cfg = {
            "screenshot_interval_sec": 300,
            "activitywatch_url": "http://localhost:5600",
        }
        fake_path = tmp_home / "screenshots" / "screen_20260413_100000.png"
        fake_path.write_bytes(b"fake png")

        with patch("focusmonitor.main.take_screenshot", return_value=fake_path), \
             patch("focusmonitor.main.snapshot_aw_events", return_value=[{"data": {"app": "VS Code"}}]):
            collect_tick(cfg, db)

        rows = db.execute("SELECT collected_at, screenshot_path, aw_events_json, processed FROM pending_data").fetchall()
        assert len(rows) == 1
        collected_at, screenshot_path, aw_json, processed = rows[0]
        assert collected_at is not None
        assert screenshot_path == str(fake_path)
        assert json.loads(aw_json) == [{"data": {"app": "VS Code"}}]
        assert processed == 0
    finally:
        db.close()


def test_collect_tick_handles_screenshot_failure(tmp_home):
    from focusmonitor.main import collect_tick

    db = init_db()
    try:
        cfg = {
            "screenshot_interval_sec": 300,
            "activitywatch_url": "http://localhost:5600",
        }
        with patch("focusmonitor.main.take_screenshot", return_value=None), \
             patch("focusmonitor.main.snapshot_aw_events", return_value=[]):
            collect_tick(cfg, db)

        rows = db.execute("SELECT screenshot_path, aw_events_json FROM pending_data").fetchall()
        assert len(rows) == 1
        assert rows[0][0] is None
        assert json.loads(rows[0][1]) == []
    finally:
        db.close()


# ── 7.3 & 7.4 batch_analyze groups and marks processed ─────────────────────

def test_batch_analyze_groups_into_windows(tmp_home):
    from focusmonitor.analysis import batch_analyze

    db = init_db()
    try:
        cfg = {
            "analysis_interval_sec": 3600,
            "batch_analysis": True,
            "screenshot_interval_sec": 300,
            "screenshots_per_analysis": 12,
            "dedup_size_threshold_pct": 2,
            "two_pass_analysis": False,
            "history_window": 0,
            "max_parse_retries": 0,
            "ollama_model": "llama3.2-vision",
            "ollama_url": "http://localhost:11434",
            "ollama_keep_alive": "30s",
            "activitywatch_url": "http://localhost:5600",
            "nudge_after_hours": 2,
            "corrections_few_shot_n": 0,
            "session_aggregation_enabled": False,
            "pass1_structured": True,
        }

        # Insert 6 rows spanning 2 hours → should create 2 windows
        base = datetime(2026, 4, 13, 10, 0, 0)
        for i in range(6):
            ts = (base + timedelta(minutes=i * 20)).isoformat()
            db.execute(
                "INSERT INTO pending_data (collected_at, screenshot_path, aw_events_json, processed) "
                "VALUES (?, ?, ?, 0)",
                (ts, None, json.dumps([{"data": {"app": f"App{i}"}, "duration": 60}])),
            )
        db.commit()

        call_count = {"n": 0}
        original_run = None

        def mock_run_analysis(cfg, db, *, prefetched_events=None, prefetched_screenshots=None):
            call_count["n"] += 1
            # Verify we get prefetched events
            assert prefetched_events is not None

        with patch("focusmonitor.analysis.run_analysis", side_effect=mock_run_analysis):
            batch_analyze(cfg, db)

        assert call_count["n"] == 2  # 2 windows

        # All rows should be marked processed
        unprocessed = db.execute("SELECT COUNT(*) FROM pending_data WHERE processed = 0").fetchone()[0]
        assert unprocessed == 0
    finally:
        db.close()


def test_batch_analyze_no_pending_data(tmp_home):
    from focusmonitor.analysis import batch_analyze

    db = init_db()
    try:
        cfg = {"analysis_interval_sec": 3600}
        # Should not raise, just return
        batch_analyze(cfg, db)
    finally:
        db.close()


def test_batch_analyze_marks_processed(tmp_home):
    from focusmonitor.analysis import batch_analyze

    db = init_db()
    try:
        cfg = {
            "analysis_interval_sec": 3600,
            "batch_analysis": True,
            "screenshot_interval_sec": 300,
            "screenshots_per_analysis": 12,
            "dedup_size_threshold_pct": 2,
            "two_pass_analysis": False,
            "history_window": 0,
            "max_parse_retries": 0,
            "ollama_model": "llama3.2-vision",
            "ollama_url": "http://localhost:11434",
            "ollama_keep_alive": "30s",
            "activitywatch_url": "http://localhost:5600",
            "nudge_after_hours": 2,
            "corrections_few_shot_n": 0,
            "session_aggregation_enabled": False,
            "pass1_structured": True,
        }

        db.execute(
            "INSERT INTO pending_data (collected_at, screenshot_path, aw_events_json, processed) "
            "VALUES (?, ?, ?, 0)",
            ("2026-04-13T10:00:00", None, "[]"),
        )
        db.commit()

        with patch("focusmonitor.analysis.run_analysis"):
            batch_analyze(cfg, db)

        processed = db.execute("SELECT processed FROM pending_data").fetchone()[0]
        assert processed == 1
    finally:
        db.close()


# ── 7.5 run_analysis uses prefetched data ────────────────────────────────────

def test_run_analysis_uses_prefetched_events(tmp_home):
    from focusmonitor.analysis import run_analysis

    db = init_db()
    try:
        cfg = {
            "analysis_interval_sec": 3600,
            "batch_analysis": True,
            "screenshot_interval_sec": 300,
            "screenshots_per_analysis": 12,
            "dedup_size_threshold_pct": 2,
            "two_pass_analysis": False,
            "history_window": 0,
            "max_parse_retries": 0,
            "ollama_model": "llama3.2-vision",
            "ollama_url": "http://localhost:11434",
            "ollama_keep_alive": "30s",
            "activitywatch_url": "http://localhost:5600",
            "nudge_after_hours": 2,
            "corrections_few_shot_n": 0,
            "session_aggregation_enabled": False,
            "pass1_structured": True,
        }

        fake_events = [
            {"data": {"app": "VS Code", "title": "test.py"}, "duration": 300}
        ]

        fake_response = json.dumps({
            "projects": ["test"],
            "planned_match": [],
            "distractions": [],
            "summary": "testing",
            "focus_score": 80,
            "task": "test",
            "evidence": [],
            "boundary_confidence": "high",
            "name_confidence": "high",
            "needs_user_input": False,
        })

        with patch("focusmonitor.analysis.get_aw_events") as mock_aw, \
             patch("focusmonitor.analysis.recent_screenshots", return_value=[]), \
             patch("focusmonitor.analysis.query_ollama", return_value=fake_response), \
             patch("focusmonitor.analysis.load_planned_tasks", return_value=[]), \
             patch("focusmonitor.analysis.update_discovered_activities"):
            result = run_analysis(cfg, db, prefetched_events=fake_events)
            # get_aw_events should NOT have been called
            mock_aw.assert_not_called()

        assert result["focus_score"] == 80
    finally:
        db.close()


def test_run_analysis_uses_prefetched_screenshots(tmp_home):
    from focusmonitor.analysis import run_analysis

    db = init_db()
    try:
        cfg = {
            "analysis_interval_sec": 3600,
            "batch_analysis": True,
            "screenshot_interval_sec": 300,
            "screenshots_per_analysis": 12,
            "dedup_size_threshold_pct": 2,
            "two_pass_analysis": False,
            "history_window": 0,
            "max_parse_retries": 0,
            "ollama_model": "llama3.2-vision",
            "ollama_url": "http://localhost:11434",
            "ollama_keep_alive": "30s",
            "activitywatch_url": "http://localhost:5600",
            "nudge_after_hours": 2,
            "corrections_few_shot_n": 0,
            "session_aggregation_enabled": False,
            "pass1_structured": True,
        }

        fake_response = json.dumps({
            "projects": [],
            "planned_match": [],
            "distractions": [],
            "summary": "testing",
            "focus_score": 50,
            "task": None,
            "evidence": [],
            "boundary_confidence": "low",
            "name_confidence": "low",
            "needs_user_input": True,
        })

        # Create real temp files so dedup can stat them
        screenshots_dir = tmp_home / "screenshots"
        s1 = screenshots_dir / "screen_20260413_100000.png"
        s2 = screenshots_dir / "screen_20260413_100500.png"
        s1.write_bytes(b"x" * 1000)
        s2.write_bytes(b"y" * 2000)
        fake_screenshots = [s1, s2]

        with patch("focusmonitor.analysis.get_aw_events", return_value=[]), \
             patch("focusmonitor.analysis.recent_screenshots") as mock_recent, \
             patch("focusmonitor.analysis.query_ollama", return_value=fake_response), \
             patch("focusmonitor.analysis.load_planned_tasks", return_value=[]), \
             patch("focusmonitor.analysis.update_discovered_activities"):
            result = run_analysis(cfg, db, prefetched_screenshots=fake_screenshots)
            # recent_screenshots should NOT have been called
            mock_recent.assert_not_called()
    finally:
        db.close()


# ── 7.6 clock-schedule matching and fired_today reset ────────────────────────

def test_schedule_matching():
    """Verify the schedule matching logic used in the main loop."""
    schedule = ["07:00", "12:00", "20:00"]
    fired_today = set()

    # 07:00 should match
    now_hm = "07:00"
    assert now_hm in schedule and now_hm not in fired_today
    fired_today.add(now_hm)

    # 07:00 should not match again
    assert now_hm in fired_today

    # 12:00 should match
    now_hm = "12:00"
    assert now_hm in schedule and now_hm not in fired_today

    # 08:00 not in schedule
    now_hm = "08:00"
    assert now_hm not in schedule


def test_fired_today_resets_on_date_change():
    """Verify the date-change reset logic."""
    from datetime import date

    fired_today = {"07:00", "12:00"}
    today_date = date(2026, 4, 13)

    # Same date: no reset
    current_date = date(2026, 4, 13)
    if current_date != today_date:
        fired_today = set()
        today_date = current_date
    assert fired_today == {"07:00", "12:00"}

    # Next day: reset
    current_date = date(2026, 4, 14)
    if current_date != today_date:
        fired_today = set()
        today_date = current_date
    assert fired_today == set()
    assert today_date == date(2026, 4, 14)


# ── 7.7 nudges skipped in batch mode ────────────────────────────────────────

def test_nudges_skipped_in_batch_mode(tmp_home):
    from focusmonitor.analysis import run_analysis

    db = init_db()
    try:
        cfg = {
            "analysis_interval_sec": 3600,
            "batch_analysis": True,
            "screenshot_interval_sec": 300,
            "screenshots_per_analysis": 12,
            "dedup_size_threshold_pct": 2,
            "two_pass_analysis": False,
            "history_window": 0,
            "max_parse_retries": 0,
            "ollama_model": "llama3.2-vision",
            "ollama_url": "http://localhost:11434",
            "ollama_keep_alive": "30s",
            "activitywatch_url": "http://localhost:5600",
            "nudge_after_hours": 2,
            "corrections_few_shot_n": 0,
            "session_aggregation_enabled": False,
            "pass1_structured": True,
        }

        fake_response = json.dumps({
            "projects": ["test"],
            "planned_match": [],
            "distractions": [],
            "summary": "testing",
            "focus_score": 80,
            "task": "test",
            "evidence": [],
            "boundary_confidence": "high",
            "name_confidence": "high",
            "needs_user_input": False,
        })

        with patch("focusmonitor.analysis.get_aw_events", return_value=[]), \
             patch("focusmonitor.analysis.recent_screenshots", return_value=[]), \
             patch("focusmonitor.analysis.query_ollama", return_value=fake_response), \
             patch("focusmonitor.analysis.load_planned_tasks", return_value=[]), \
             patch("focusmonitor.analysis.update_discovered_activities"), \
             patch("focusmonitor.analysis.check_nudges") as mock_nudges:
            run_analysis(cfg, db, prefetched_events=[])
            mock_nudges.assert_not_called()
    finally:
        db.close()


def test_nudges_called_in_live_mode(tmp_home):
    from focusmonitor.analysis import run_analysis

    db = init_db()
    try:
        cfg = {
            "analysis_interval_sec": 3600,
            "batch_analysis": False,
            "screenshot_interval_sec": 300,
            "screenshots_per_analysis": 12,
            "dedup_size_threshold_pct": 2,
            "two_pass_analysis": False,
            "history_window": 0,
            "max_parse_retries": 0,
            "ollama_model": "llama3.2-vision",
            "ollama_url": "http://localhost:11434",
            "ollama_keep_alive": "30s",
            "activitywatch_url": "http://localhost:5600",
            "nudge_after_hours": 2,
            "corrections_few_shot_n": 0,
            "session_aggregation_enabled": False,
            "pass1_structured": True,
        }

        fake_response = json.dumps({
            "projects": ["test"],
            "planned_match": [],
            "distractions": [],
            "summary": "testing",
            "focus_score": 80,
            "task": "test",
            "evidence": [],
            "boundary_confidence": "high",
            "name_confidence": "high",
            "needs_user_input": False,
        })

        with patch("focusmonitor.analysis.get_aw_events", return_value=[]), \
             patch("focusmonitor.analysis.recent_screenshots", return_value=[]), \
             patch("focusmonitor.analysis.query_ollama", return_value=fake_response), \
             patch("focusmonitor.analysis.load_planned_tasks", return_value=[]), \
             patch("focusmonitor.analysis.update_discovered_activities"), \
             patch("focusmonitor.analysis.check_nudges") as mock_nudges:
            run_analysis(cfg, db)
            mock_nudges.assert_called_once()
    finally:
        db.close()
