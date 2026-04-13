"""Tests for the deterministic session aggregator.

Everything here is pure-function testing against synthetic cycle
inputs — no Ollama, no ActivityWatch, no DB except in the persistence
tests. The aggregator is the layer that has to be correct by
construction because it glues the LLM's per-cycle classifications
into the thing the user actually looks at.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from focusmonitor.db import init_db
from focusmonitor.sessions import (
    _browser_host,
    _cycles_glue,
    _min_confidence,
    _segment,
    aggregate,
    aggregate_day,
    aw_afk_overlay,
    extract_cycle_signals,
    persist_sessions,
)


# ── helpers for building synthetic cycle rows ────────────────────────────────

BASE = datetime(2026, 4, 12, 10, 0, 0)


def _iso(dt):
    return dt.isoformat()


def _cycle(
    idx,
    *,
    start_min=0,
    duration_min=5,
    task=None,
    name_conf="high",
    boundary_conf="high",
    workspaces=None,
    terminal_cwds=None,
    browser_hosts=None,
    evidence=None,
    kind=None,
):
    """Build a synthetic cycle dict. `idx` becomes the row id so tests can
    trace cycles through the aggregator and make order-dependent
    assertions without relying on object identity.
    """
    start = BASE + timedelta(minutes=start_min)
    end = start + timedelta(minutes=duration_min)
    row = {
        "id": idx,
        "start": _iso(start),
        "end": _iso(end),
        "task": task,
        "name_confidence": name_conf,
        "boundary_confidence": boundary_conf,
        "workspaces": list(workspaces) if workspaces else [],
        "terminal_cwds": list(terminal_cwds) if terminal_cwds else [],
        "browser_hosts": list(browser_hosts) if browser_hosts else [],
        "evidence": list(evidence) if evidence else [],
    }
    if kind is not None:
        row["kind"] = kind
    return row


# ── _browser_host ────────────────────────────────────────────────────────────

class TestBrowserHost:

    def test_strips_scheme(self):
        assert _browser_host("https://github.com/foo/bar") == "github.com"

    def test_no_scheme(self):
        assert _browser_host("github.com/foo/bar/pull/47") == "github.com"

    def test_lowercases(self):
        assert _browser_host("HTTPS://GitHub.com/Foo") == "github.com"

    def test_none_and_empty(self):
        assert _browser_host(None) is None
        assert _browser_host("") is None
        assert _browser_host("   ") is None

    def test_query_string_stripped(self):
        assert _browser_host("github.com?q=x") == "github.com"


# ── extract_cycle_signals ────────────────────────────────────────────────────

class TestExtractCycleSignals:

    def test_collects_non_null_workspaces_and_cwds(self):
        artifacts = [
            {"workspace": "focus-monitor", "terminal_cwd": "~/code/demo",
             "browser_url": "github.com/foo/bar/pull/47"},
            {"workspace": "focus-monitor", "terminal_cwd": "~/code/demo",
             "browser_url": None},
            {"workspace": None, "terminal_cwd": "~/other",
             "browser_url": "https://stackoverflow.com/q/1"},
        ]
        signals = extract_cycle_signals(artifacts)
        assert signals["workspaces"] == ["focus-monitor"]
        assert signals["terminal_cwds"] == ["~/code/demo", "~/other"]
        assert signals["browser_hosts"] == ["github.com", "stackoverflow.com"]

    def test_case_insensitive_dedup(self):
        artifacts = [
            {"workspace": "focus-monitor"},
            {"workspace": "FOCUS-MONITOR"},
            {"workspace": "Focus-Monitor"},
        ]
        signals = extract_cycle_signals(artifacts)
        # Dedup on lowercased, but first-seen-wins for the preserved case.
        assert len(signals["workspaces"]) == 1
        assert signals["workspaces"][0] == "focus-monitor"

    def test_empty_and_none_safe(self):
        assert extract_cycle_signals(None) == {
            "workspaces": [], "terminal_cwds": [], "browser_hosts": []}
        assert extract_cycle_signals([]) == {
            "workspaces": [], "terminal_cwds": [], "browser_hosts": []}
        assert extract_cycle_signals([None, "not a dict", {}])["workspaces"] == []


# ── _cycles_glue: each rule in isolation ─────────────────────────────────────

class TestCyclesGlue:

    def test_workspace_match(self):
        a = _cycle(1, workspaces=["focus-monitor"])
        b = _cycle(2, workspaces=["focus-monitor"])
        assert _cycles_glue(a, b) is True

    def test_workspace_mismatch(self):
        a = _cycle(1, workspaces=["proj-a"])
        b = _cycle(2, workspaces=["proj-b"])
        assert _cycles_glue(a, b) is False

    def test_workspace_case_insensitive(self):
        a = _cycle(1, workspaces=["Focus-Monitor"])
        b = _cycle(2, workspaces=["focus-monitor"])
        assert _cycles_glue(a, b) is True

    def test_terminal_cwd_match(self):
        a = _cycle(1, terminal_cwds=["~/code/demo"])
        b = _cycle(2, terminal_cwds=["~/code/demo"])
        assert _cycles_glue(a, b) is True

    def test_browser_host_match(self):
        a = _cycle(1, browser_hosts=["github.com"])
        b = _cycle(2, browser_hosts=["github.com"])
        assert _cycles_glue(a, b) is True

    def test_task_name_match_requires_medium_conf_both_sides(self):
        a = _cycle(1, task="auth refactor", name_conf="medium")
        b = _cycle(2, task="auth refactor", name_conf="medium")
        assert _cycles_glue(a, b) is True

    def test_task_name_low_conf_does_not_glue(self):
        a = _cycle(1, task="auth refactor", name_conf="low")
        b = _cycle(2, task="auth refactor", name_conf="low")
        # Task match alone isn't enough when confidence is low.
        assert _cycles_glue(a, b) is False

    def test_task_name_case_insensitive(self):
        a = _cycle(1, task="Auth Refactor", name_conf="high")
        b = _cycle(2, task="auth refactor", name_conf="high")
        assert _cycles_glue(a, b) is True

    def test_disjoint_all_signals(self):
        a = _cycle(1, workspaces=["proj-a"], terminal_cwds=["~/a"],
                   browser_hosts=["a.com"], task="ta", name_conf="high")
        b = _cycle(2, workspaces=["proj-b"], terminal_cwds=["~/b"],
                   browser_hosts=["b.com"], task="tb", name_conf="high")
        assert _cycles_glue(a, b) is False


# ── aggregate: spec scenarios ────────────────────────────────────────────────

class TestAggregate:

    def test_single_coherent_activity_becomes_one_session(self):
        cycles = [
            _cycle(i, start_min=i * 5, task="auth refactor",
                   name_conf="high", boundary_conf="high",
                   workspaces=["focus-monitor"],
                   evidence=[{"signal": "workspace", "weight": "strong"}])
            for i in range(5)
        ]
        sessions = aggregate(cycles)
        assert len(sessions) == 1
        s = sessions[0]
        assert s["kind"] == "session"
        assert s["task"] == "auth refactor"
        assert s["cycle_count"] == 5
        assert s["dip_count"] == 0
        assert s["start"] == cycles[0]["start"]
        assert s["end"] == cycles[-1]["end"]
        assert s["cycle_ids"] == [0, 1, 2, 3, 4]

    def test_genuine_task_switch_creates_separate_sessions(self):
        cycles = []
        for i in range(3):
            cycles.append(_cycle(
                i, start_min=i * 5, task="auth",
                workspaces=["focus-monitor"],
                name_conf="high",
            ))
        for i in range(4):
            cycles.append(_cycle(
                i + 3, start_min=(i + 3) * 5, task="other",
                workspaces=["other-project"],
                name_conf="high",
            ))
        sessions = aggregate(cycles)
        assert len(sessions) == 2
        assert sessions[0]["task"] == "auth"
        assert sessions[0]["cycle_count"] == 3
        assert sessions[1]["task"] == "other"
        assert sessions[1]["cycle_count"] == 4

    def test_workspace_glue_overrides_differing_other_fields(self):
        a = _cycle(1, start_min=0, task=None, name_conf="low",
                   workspaces=["focus-monitor"],
                   terminal_cwds=["~/code/focus-monitor"],
                   browser_hosts=["github.com"])
        b = _cycle(2, start_min=5, task=None, name_conf="low",
                   workspaces=["focus-monitor"],
                   terminal_cwds=["~/other"],
                   browser_hosts=["reddit.com"])
        sessions = aggregate([a, b])
        assert len(sessions) == 1
        assert sessions[0]["cycle_count"] == 2

    def test_terminal_cwd_glue(self):
        a = _cycle(1, start_min=0, terminal_cwds=["~/code/demo"],
                   name_conf="high", task="demo")
        b = _cycle(2, start_min=5, terminal_cwds=["~/code/demo"],
                   name_conf="high", task="demo")
        sessions = aggregate([a, b])
        assert len(sessions) == 1

    def test_browser_host_glue_same_host_different_urls(self):
        a = _cycle(1, start_min=0, browser_hosts=["github.com"],
                   name_conf="high")
        b = _cycle(2, start_min=5, browser_hosts=["github.com"],
                   name_conf="high")
        sessions = aggregate([a, b])
        assert len(sessions) == 1

    def test_no_overlapping_signals_stay_split(self):
        a = _cycle(1, start_min=0, workspaces=["proj-a"], name_conf="high")
        b = _cycle(2, start_min=5, workspaces=["proj-b"], name_conf="high")
        sessions = aggregate([a, b])
        assert len(sessions) == 2

    def test_3_minute_reddit_dip_absorbed(self):
        """4 focus-monitor cycles, 3-min reddit dip, 4 more focus-monitor.
        Expect ONE session with dip_count=1 (as in the spec scenario)."""
        cycles = []
        # 4 × 5-min focus-monitor cycles: minutes 0..20
        for i in range(4):
            cycles.append(_cycle(
                i, start_min=i * 5, duration_min=5,
                task="auth", name_conf="high",
                workspaces=["focus-monitor"],
                evidence=[{"signal": "workspace", "weight": "strong"}]))
        # 1 × 3-minute reddit dip at minute 20
        cycles.append(_cycle(
            100, start_min=20, duration_min=3,
            task=None, name_conf="low",
            browser_hosts=["reddit.com"],
            evidence=[{"signal": "reddit", "weight": "weak"}]))
        # 4 × 5-min focus-monitor cycles: minutes 23..43
        for i in range(4):
            cycles.append(_cycle(
                i + 200, start_min=23 + i * 5, duration_min=5,
                task="auth", name_conf="high",
                workspaces=["focus-monitor"]))
        sessions = aggregate(cycles, dip_tolerance_sec=300)
        assert len(sessions) == 1
        s = sessions[0]
        assert s["kind"] == "session"
        assert s["cycle_count"] == 9
        assert s["dip_count"] == 1
        # Evidence from the dip cycle must NOT appear in the aggregated
        # evidence — only the main cycles contribute.
        assert all(e["signal"] != "reddit" for e in s["evidence"])
        assert any(e["signal"] == "workspace" for e in s["evidence"])

    def test_10_minute_distraction_splits_session(self):
        cycles = []
        for i in range(4):
            cycles.append(_cycle(
                i, start_min=i * 5, duration_min=5,
                task="auth", name_conf="high",
                workspaces=["focus-monitor"]))
        # 10-minute distraction (exceeds default 5-minute tolerance)
        cycles.append(_cycle(
            100, start_min=20, duration_min=10,
            task=None, name_conf="low",
            browser_hosts=["reddit.com"]))
        for i in range(4):
            cycles.append(_cycle(
                i + 200, start_min=30 + i * 5, duration_min=5,
                task="auth", name_conf="high",
                workspaces=["focus-monitor"]))
        sessions = aggregate(cycles, dip_tolerance_sec=300)
        assert len(sessions) == 3
        assert sessions[0]["task"] == "auth"
        assert sessions[0]["cycle_count"] == 4
        # The middle entry is single-cycle low-confidence → unclear
        assert sessions[1]["kind"] == "unclear"
        assert sessions[1]["task"] is None
        assert sessions[2]["task"] == "auth"
        assert sessions[2]["cycle_count"] == 4

    def test_standalone_unclear_cycle(self):
        """Low-confidence cycle with no glue match to either neighbor
        becomes its own unclear entry."""
        cycles = [
            _cycle(1, start_min=0, task="a", name_conf="high",
                   workspaces=["proj-a"]),
            _cycle(2, start_min=5, task=None, name_conf="low",
                   duration_min=6,  # > dip tolerance → not absorbed
                   workspaces=[]),
            _cycle(3, start_min=11, task="b", name_conf="high",
                   workspaces=["proj-b"]),
        ]
        sessions = aggregate(cycles, dip_tolerance_sec=300)
        assert len(sessions) == 3
        assert sessions[1]["kind"] == "unclear"
        assert sessions[1]["task"] is None
        assert sessions[1]["cycle_count"] == 1

    def test_aggregation_is_idempotent(self):
        """Pure function: same input → same output, twice."""
        cycles = [
            _cycle(i, start_min=i * 5,
                   task="auth", name_conf="high",
                   workspaces=["focus-monitor"])
            for i in range(5)
        ]
        first = aggregate(cycles)
        second = aggregate(cycles)
        assert first == second

    def test_evidence_aggregates_across_cycles(self):
        cycles = [
            _cycle(1, start_min=0, task="auth", name_conf="high",
                   workspaces=["focus-monitor"],
                   evidence=[
                       {"signal": "workspace", "weight": "strong"},
                       {"signal": "cwd", "weight": "medium"},
                   ]),
            _cycle(2, start_min=5, task="auth", name_conf="high",
                   workspaces=["focus-monitor"],
                   evidence=[
                       {"signal": "workspace", "weight": "strong"},
                       {"signal": "pr url", "weight": "medium"},
                       {"signal": "weak hint", "weight": "weak"},
                   ]),
        ]
        sessions = aggregate(cycles)
        assert len(sessions) == 1
        signals = {e["signal"] for e in sessions[0]["evidence"]}
        assert signals == {"workspace", "cwd", "pr url"}
        # Weak signals dropped.
        assert "weak hint" not in signals
        # workspace appears once (dedup), with strong weight preserved.
        ws_entry = next(e for e in sessions[0]["evidence"] if e["signal"] == "workspace")
        assert ws_entry["weight"] == "strong"

    def test_evidence_prefers_stronger_weight_on_collision(self):
        cycles = [
            _cycle(1, start_min=0, task="t", name_conf="high",
                   workspaces=["ws"],
                   evidence=[{"signal": "same", "weight": "medium"}]),
            _cycle(2, start_min=5, task="t", name_conf="high",
                   workspaces=["ws"],
                   evidence=[{"signal": "same", "weight": "strong"}]),
        ]
        sessions = aggregate(cycles)
        entry = next(e for e in sessions[0]["evidence"] if e["signal"] == "same")
        assert entry["weight"] == "strong"

    def test_session_confidence_is_the_minimum(self):
        cycles = [
            _cycle(1, start_min=0, task="t", name_conf="high",
                   boundary_conf="high", workspaces=["ws"]),
            _cycle(2, start_min=5, task="t", name_conf="medium",
                   boundary_conf="low", workspaces=["ws"]),
        ]
        sessions = aggregate(cycles)
        assert sessions[0]["task_name_confidence"] == "medium"
        assert sessions[0]["boundary_confidence"] == "low"

    def test_empty_cycles_returns_empty(self):
        assert aggregate([]) == []


# ── aw_afk_overlay ───────────────────────────────────────────────────────────

class TestAwAfkOverlay:

    def test_major_afk_overlap_marks_away(self):
        """A 5-minute cycle with a 4-minute afk overlap → away."""
        cycles = [
            _cycle(1, start_min=0, duration_min=5, workspaces=["ws"]),
        ]
        afk_start = (BASE + timedelta(minutes=0, seconds=30)).isoformat()
        afk_events = [{
            "timestamp": afk_start,
            "duration": 4 * 60,  # 4 minutes of afk
            "data": {"status": "afk"},
        }]
        result = aw_afk_overlay(cycles, afk_events)
        assert result[0]["kind"] == "away"

    def test_brief_afk_does_not_mark_away(self):
        """A 30-second afk inside a 5-minute cycle → still session."""
        cycles = [
            _cycle(1, start_min=0, duration_min=5, workspaces=["ws"]),
        ]
        afk_start = (BASE + timedelta(minutes=1)).isoformat()
        afk_events = [{
            "timestamp": afk_start,
            "duration": 30,  # 30 seconds
            "data": {"status": "afk"},
        }]
        result = aw_afk_overlay(cycles, afk_events)
        assert result[0]["kind"] == "session"

    def test_empty_afk_events_marks_everything_session(self):
        cycles = [
            _cycle(1, start_min=0, workspaces=["ws"]),
            _cycle(2, start_min=5, workspaces=["ws"]),
        ]
        result = aw_afk_overlay(cycles, [])
        assert all(c["kind"] == "session" for c in result)

    def test_aw_unreachable_placeholder_empty_events(self):
        """Defensive path: aggregator proceeds with cycle-only analysis
        when afk events are empty."""
        cycles = [
            _cycle(1, start_min=0, task="t", name_conf="high",
                   workspaces=["ws"]),
        ]
        cycles_with_kind = aw_afk_overlay(cycles, [])
        sessions = aggregate(cycles_with_kind)
        assert len(sessions) == 1
        assert sessions[0]["kind"] == "session"

    def test_consecutive_away_cycles_merge_into_one_away_entry(self):
        cycles = [
            _cycle(1, start_min=0, duration_min=5, kind="away"),
            _cycle(2, start_min=5, duration_min=5, kind="away"),
            _cycle(3, start_min=10, duration_min=5, kind="away"),
        ]
        sessions = aggregate(cycles)
        assert len(sessions) == 1
        assert sessions[0]["kind"] == "away"
        assert sessions[0]["cycle_count"] == 3
        assert sessions[0]["start"] == cycles[0]["start"]
        assert sessions[0]["end"] == cycles[-1]["end"]

    def test_afk_with_malformed_events_does_not_raise(self):
        cycles = [_cycle(1, start_min=0, workspaces=["ws"])]
        bad_events = [
            {"timestamp": "not a date", "duration": 60, "data": {"status": "afk"}},
            {"data": {"status": "afk"}},  # missing timestamp
            {"timestamp": BASE.isoformat(), "duration": "bad", "data": {"status": "afk"}},
            None,
            "garbage",
        ]
        # Must not raise.
        result = aw_afk_overlay(cycles, bad_events)
        assert result[0]["kind"] == "session"


# ── persist_sessions ─────────────────────────────────────────────────────────

class TestPersistSessions:

    def test_persist_and_read_roundtrip(self, tmp_home):
        db = init_db()
        sessions = [
            {
                "kind": "session",
                "start": "2026-04-12T10:00:00",
                "end": "2026-04-12T10:30:00",
                "task": "auth refactor",
                "task_name_confidence": "high",
                "boundary_confidence": "high",
                "cycle_count": 6,
                "dip_count": 1,
                "evidence": [{"signal": "workspace", "weight": "strong"}],
            },
        ]
        persist_sessions(db, sessions,
                         "2026-04-12T00:00:00",
                         "2026-04-13T00:00:00")
        rows = db.execute(
            "SELECT task, task_name_confidence, boundary_confidence, "
            "cycle_count, dip_count, evidence_json, kind FROM sessions"
        ).fetchall()
        db.close()
        assert len(rows) == 1
        task, name_conf, bound_conf, cc, dc, ev_json, kind = rows[0]
        assert task == "auth refactor"
        assert name_conf == "high"
        assert bound_conf == "high"
        assert cc == 6
        assert dc == 1
        assert json.loads(ev_json) == [{"signal": "workspace", "weight": "strong"}]
        assert kind == "session"

    def test_persist_is_idempotent_over_same_range(self, tmp_home):
        db = init_db()
        sessions = [
            {
                "kind": "session",
                "start": "2026-04-12T10:00:00",
                "end": "2026-04-12T10:30:00",
                "task": "t",
                "task_name_confidence": "high",
                "boundary_confidence": "high",
                "cycle_count": 1,
                "dip_count": 0,
                "evidence": [],
            },
        ]
        # Run twice — must not produce duplicates.
        persist_sessions(db, sessions,
                         "2026-04-12T00:00:00", "2026-04-13T00:00:00")
        persist_sessions(db, sessions,
                         "2026-04-12T00:00:00", "2026-04-13T00:00:00")
        count = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        db.close()
        assert count == 1

    def test_persist_deletes_only_affected_range(self, tmp_home):
        db = init_db()
        # Day 1 sessions
        persist_sessions(
            db,
            [{"kind": "session", "start": "2026-04-11T10:00:00",
              "end": "2026-04-11T10:30:00", "task": "day1",
              "task_name_confidence": "high", "boundary_confidence": "high",
              "cycle_count": 1, "dip_count": 0, "evidence": []}],
            "2026-04-11T00:00:00", "2026-04-12T00:00:00",
        )
        # Day 2 sessions
        persist_sessions(
            db,
            [{"kind": "session", "start": "2026-04-12T10:00:00",
              "end": "2026-04-12T10:30:00", "task": "day2",
              "task_name_confidence": "high", "boundary_confidence": "high",
              "cycle_count": 1, "dip_count": 0, "evidence": []}],
            "2026-04-12T00:00:00", "2026-04-13T00:00:00",
        )
        tasks = {
            row[0] for row in db.execute("SELECT task FROM sessions").fetchall()
        }
        db.close()
        # Persisting day 2 must NOT delete day 1's rows.
        assert tasks == {"day1", "day2"}


# ── aggregate_day orchestrator ───────────────────────────────────────────────

class TestAggregateDay:
    """Smoke tests for the DB-backed orchestrator. The pure aggregator is
    covered exhaustively above; here we just confirm the row → cycle
    reconstruction works and that it's end-to-end idempotent.
    """

    def _insert_row(self, db, timestamp, cycle_payload):
        db.execute(
            """INSERT INTO activity_log
                (timestamp, window_titles, apps_used, project_detected,
                 is_distraction, summary, raw_response)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                timestamp,
                json.dumps([]),
                json.dumps([]),
                json.dumps([]),
                0,
                cycle_payload.get("summary", ""),
                json.dumps(cycle_payload),
            ),
        )

    def test_aggregate_day_reconstructs_and_persists(self, tmp_home):
        db = init_db()
        cfg = {"analysis_interval_sec": 300,
               "session_dip_tolerance_sec": 300,
               "activitywatch_url": "http://127.0.0.1:1"}
        # Two rows, same workspace, high confidence → one session.
        self._insert_row(db, "2026-04-12T10:05:00", {
            "task": "auth", "name_confidence": "high",
            "boundary_confidence": "high",
            "evidence": [{"signal": "workspace", "weight": "strong"}],
            "cycle_start": "2026-04-12T10:00:00",
            "cycle_end": "2026-04-12T10:05:00",
            "cycle_signals": {"workspaces": ["focus-monitor"],
                              "terminal_cwds": [], "browser_hosts": []},
        })
        self._insert_row(db, "2026-04-12T10:10:00", {
            "task": "auth", "name_confidence": "high",
            "boundary_confidence": "high",
            "evidence": [{"signal": "workspace", "weight": "strong"}],
            "cycle_start": "2026-04-12T10:05:00",
            "cycle_end": "2026-04-12T10:10:00",
            "cycle_signals": {"workspaces": ["focus-monitor"],
                              "terminal_cwds": [], "browser_hosts": []},
        })
        db.commit()
        sessions = aggregate_day(db, cfg, "2026-04-12")
        assert len(sessions) == 1
        assert sessions[0]["task"] == "auth"
        assert sessions[0]["cycle_count"] == 2
        # Idempotent: run again, still one row.
        aggregate_day(db, cfg, "2026-04-12")
        count = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        assert count == 1
        db.close()

    def test_aggregate_day_reads_legacy_rows_without_cycle_fields(self, tmp_home):
        """Rows written before this change lack cycle_start/end/signals.
        The reader falls back gracefully: derive end from the row
        timestamp, derive start by subtracting analysis_interval_sec,
        treat signals as empty."""
        db = init_db()
        cfg = {"analysis_interval_sec": 1800,
               "session_dip_tolerance_sec": 300,
               "activitywatch_url": "http://127.0.0.1:1"}
        self._insert_row(db, "2026-04-12T10:00:00", {
            "projects": ["focus-monitor"],
            "planned_match": ["focus-monitor"],
            "distractions": [],
            "summary": "legacy row",
            "focus_score": 85,
        })
        db.commit()
        sessions = aggregate_day(db, cfg, "2026-04-12")
        # Legacy row has no task, no confidence, no signals → single
        # low-confidence cycle → standalone unclear.
        assert len(sessions) == 1
        assert sessions[0]["kind"] == "unclear"
        db.close()

    def test_aggregate_day_empty_clears_stale_sessions(self, tmp_home):
        db = init_db()
        cfg = {"analysis_interval_sec": 1800,
               "session_dip_tolerance_sec": 300,
               "activitywatch_url": "http://127.0.0.1:1"}
        # Seed a stale session that covers the day
        persist_sessions(
            db,
            [{"kind": "session", "start": "2026-04-12T10:00:00",
              "end": "2026-04-12T10:30:00", "task": "stale",
              "task_name_confidence": "high", "boundary_confidence": "high",
              "cycle_count": 1, "dip_count": 0, "evidence": []}],
            "2026-04-12T00:00:00", "2026-04-13T00:00:00",
        )
        # Aggregation with no activity rows must clear the stale row.
        aggregate_day(db, cfg, "2026-04-12")
        count = db.execute(
            "SELECT COUNT(*) FROM sessions WHERE task='stale'"
        ).fetchone()[0]
        db.close()
        assert count == 0


# ── _segment / _min_confidence small helpers ─────────────────────────────────

class TestSmallHelpers:

    def test_segment_empty(self):
        assert _segment([]) == []

    def test_segment_all_glued(self):
        cycles = [
            _cycle(i, start_min=i * 5, workspaces=["ws"], name_conf="high")
            for i in range(3)
        ]
        segs = _segment(cycles)
        assert len(segs) == 1
        assert len(segs[0]) == 3

    def test_segment_all_split(self):
        cycles = [
            _cycle(1, start_min=0, workspaces=["a"]),
            _cycle(2, start_min=5, workspaces=["b"]),
            _cycle(3, start_min=10, workspaces=["c"]),
        ]
        segs = _segment(cycles)
        assert len(segs) == 3

    def test_min_confidence_picks_lowest(self):
        assert _min_confidence(["high", "medium", "high"]) == "medium"
        assert _min_confidence(["high", "low", "medium"]) == "low"
        assert _min_confidence([]) == "low"
        assert _min_confidence(["high"]) == "high"
