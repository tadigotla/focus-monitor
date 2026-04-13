"""Tests for the Scope API — query functions and HTTP endpoints.

Query functions are tested against in-memory SQLite populated via
init_db() + synthetic data. HTTP tests use the handler directly
without starting a real server.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta
from http.server import HTTPServer
from unittest.mock import MagicMock

import pytest

from focusmonitor.db import init_db
from scope.api import queries
from scope.api.server import ScopeHandler, _send_json, _send_error


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def scopedb(tmp_home):
    """In-memory DB via init_db with synthetic data."""
    db = init_db()
    now = datetime.now()

    # Insert a few activity_log rows
    for i in range(3):
        ts = (now - timedelta(hours=3 - i)).isoformat()
        raw = json.dumps({
            "task": f"task-{i}",
            "focus_score": 50 + i * 20,
            "name_confidence": ["low", "medium", "high"][i],
            "boundary_confidence": "high",
            "evidence": [{"signal": f"signal-{i}", "weight": "strong"}],
            "projects": [f"project-{i}"],
            "planned_match": [],
            "distractions": [],
            "summary": f"summary {i}",
            "cycle_signals": {
                "workspaces": ["focus-monitor"],
                "terminal_cwds": [],
                "browser_hosts": [],
            },
        })
        db.execute(
            "INSERT INTO activity_log (timestamp, window_titles, apps_used, "
            "project_detected, is_distraction, summary, raw_response) "
            "VALUES (?, ?, ?, ?, 0, ?, ?)",
            (ts, '["title"]', '["VSCode"]', '["proj"]', f"summary {i}", raw),
        )

    # Insert a trace for the first cycle
    db.execute(
        "INSERT INTO analysis_traces (activity_log_id, created_at, "
        "pass1_prompts_json, pass1_responses_json, pass1_elapsed_ms_json, "
        "pass2_prompt, pass2_response_raw, pass2_elapsed_ms, "
        "few_shot_ids_json, screenshot_paths_json, parse_retries) "
        "VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
        (
            now.isoformat(),
            json.dumps("extraction prompt"),
            json.dumps(["response 1"]),
            json.dumps([42.5]),
            "classification prompt text",
            '{"task": "task-0"}',
            100.0,
            json.dumps([]),
            json.dumps(["/tmp/screen.png"]),
        ),
    )

    # Insert a session
    s_start = (now - timedelta(hours=3)).isoformat()
    s_end = (now - timedelta(hours=1)).isoformat()
    db.execute(
        "INSERT INTO sessions (start, end, task, task_name_confidence, "
        "boundary_confidence, cycle_count, dip_count, evidence_json, kind) "
        "VALUES (?, ?, 'task-0', 'high', 'high', 3, 0, '[]', 'session')",
        (s_start, s_end),
    )

    # Insert a correction for cycle 2
    db.execute(
        "INSERT INTO corrections (created_at, entry_kind, entry_id, "
        "range_start, range_end, model_task, model_evidence, "
        "model_boundary_confidence, model_name_confidence, "
        "user_verdict, user_task, user_kind, user_note, signals) "
        "VALUES (?, 'cycle', 2, ?, ?, 'task-1', '[]', 'medium', 'medium', "
        "'corrected', 'real-task', 'on_planned_task', NULL, ?)",
        (now.isoformat(), s_start, s_end,
         json.dumps({"workspaces": ["focus-monitor"], "terminal_cwds": [], "browser_hosts": []})),
    )

    db.commit()
    yield db
    db.close()


# ── Query function tests ────────────────────────────────────────────────────

class TestGetCycles:

    def test_returns_cycles_for_today(self, scopedb):
        today = datetime.now().strftime("%Y-%m-%d")
        cycles = queries.get_cycles(scopedb, today)
        assert len(cycles) == 3
        assert cycles[0]["task"] == "task-0"
        assert cycles[2]["focus_score"] == 90

    def test_pagination(self, scopedb):
        today = datetime.now().strftime("%Y-%m-%d")
        page = queries.get_cycles(scopedb, today, limit=2, offset=1)
        assert len(page) == 2
        assert page[0]["task"] == "task-1"

    def test_empty_date(self, scopedb):
        cycles = queries.get_cycles(scopedb, "2020-01-01")
        assert cycles == []


class TestGetCycle:

    def test_returns_full_cycle(self, scopedb):
        cycle = queries.get_cycle(scopedb, 1)
        assert cycle is not None
        assert cycle["id"] == 1
        assert "raw_response" in cycle
        assert cycle["raw_response"]["task"] == "task-0"

    def test_not_found(self, scopedb):
        assert queries.get_cycle(scopedb, 999) is None


class TestGetCycleTrace:

    def test_returns_trace(self, scopedb):
        trace = queries.get_cycle_trace(scopedb, 1)
        assert trace is not None
        assert trace["activity_log_id"] == 1
        assert trace["pass2_prompt"] == "classification prompt text"
        assert trace["pass2_elapsed_ms"] == 100.0
        assert isinstance(trace["pass1_responses"], list)

    def test_not_found(self, scopedb):
        assert queries.get_cycle_trace(scopedb, 999) is None


class TestGetCycleCorrections:

    def test_returns_corrections(self, scopedb):
        corrs = queries.get_cycle_corrections(scopedb, 2)
        assert len(corrs) == 1
        assert corrs[0]["user_task"] == "real-task"

    def test_empty_for_uncorrected(self, scopedb):
        assert queries.get_cycle_corrections(scopedb, 1) == []


class TestGetCorrections:

    def test_returns_all(self, scopedb):
        corrs = queries.get_corrections(scopedb)
        assert len(corrs) == 1

    def test_pagination(self, scopedb):
        corrs = queries.get_corrections(scopedb, limit=0)
        assert corrs == []


class TestGetSessions:

    def test_returns_sessions(self, scopedb):
        today = datetime.now().strftime("%Y-%m-%d")
        sessions = queries.get_sessions(scopedb, today)
        assert len(sessions) == 1
        assert sessions[0]["task"] == "task-0"


class TestGetSession:

    def test_returns_session_with_cycles(self, scopedb):
        session = queries.get_session(scopedb, 1)
        assert session is not None
        assert session["task"] == "task-0"
        assert isinstance(session["cycle_ids"], list)

    def test_not_found(self, scopedb):
        assert queries.get_session(scopedb, 999) is None


class TestGetCorrectionRate:

    def test_returns_rate(self, scopedb):
        rates = queries.get_correction_rate(scopedb, days=30)
        assert len(rates) >= 1
        # We have 3 cycles and 1 correction today
        today_rate = rates[-1]
        assert today_rate["total_cycles"] == 3
        assert today_rate["corrections"] == 1


class TestGetConfidenceCalibration:

    def test_returns_calibration(self, scopedb):
        cal = queries.get_confidence_calibration(scopedb)
        assert "high" in cal
        assert "medium" in cal
        assert "low" in cal
        # The medium-confidence cycle was corrected
        assert cal["medium"]["corrected"] == 1


class TestGetPerTaskAccuracy:

    def test_returns_task_accuracy(self, scopedb):
        acc = queries.get_per_task_accuracy(scopedb)
        assert len(acc) >= 1
        task_names = [a["task"] for a in acc]
        assert "task-1" in task_names


class TestGetFewShotImpact:

    def test_returns_impact(self, scopedb):
        impact = queries.get_few_shot_impact(scopedb, 1)
        assert impact is not None
        assert impact["correction_id"] == 1
        assert "before" in impact
        assert "after" in impact
        assert "accuracy" in impact["before"]
        assert "accuracy" in impact["after"]
        assert isinstance(impact["signal_overlap"], list)

    def test_not_found(self, scopedb):
        assert queries.get_few_shot_impact(scopedb, 999) is None

    def test_empty_signals_returns_zero_counts(self, scopedb):
        # Insert a correction with empty signals
        scopedb.execute(
            "INSERT INTO corrections (created_at, entry_kind, entry_id, "
            "range_start, range_end, model_task, model_evidence, "
            "model_boundary_confidence, model_name_confidence, "
            "user_verdict, user_task, user_kind, user_note, signals) "
            "VALUES (?, 'cycle', 1, ?, ?, 'x', '[]', 'low', 'low', "
            "'corrected', 'y', 'other', NULL, '{}')",
            (datetime.now().isoformat(), datetime.now().isoformat(),
             datetime.now().isoformat()),
        )
        scopedb.commit()
        cid = scopedb.execute("SELECT MAX(id) FROM corrections").fetchone()[0]
        impact = queries.get_few_shot_impact(scopedb, cid)
        assert impact["before"]["total"] == 0
        assert impact["after"]["total"] == 0


# ── HTTP endpoint tests ─────────────────────────────────────────────────────

class _FakeHandler(ScopeHandler):
    """Subclass that captures responses without a real socket."""

    def __init__(self, path):
        self.path = path
        self.headers = {}
        self._response_status = None
        self._response_headers = {}
        self.wfile = io.BytesIO()

    def send_response(self, code, message=None):
        self._response_status = code

    def send_header(self, key, value):
        self._response_headers[key] = value

    def end_headers(self):
        pass

    def log_message(self, format, *args):
        pass


class _NoCloseDb:
    """Wrapper that forwards everything to a real DB but suppresses close()."""
    def __init__(self, db):
        self._db = db
    def close(self):
        pass  # don't close the shared test DB
    def __getattr__(self, name):
        return getattr(self._db, name)


def _make_handler(db, path, method="GET"):
    """Create a ScopeHandler with a fake request against the given path.

    Monkeypatches _open_db to return a wrapper around the test's
    in-memory DB so the per-request connection logic works.
    """
    import scope.api.server as server_mod
    original_open = server_mod._open_db
    server_mod._open_db = lambda: _NoCloseDb(db)

    handler = _FakeHandler(path)

    if method == "GET":
        handler.do_GET()
    elif method == "OPTIONS":
        handler.do_OPTIONS()

    server_mod._open_db = original_open

    status = handler._response_status
    body = handler.wfile.getvalue()
    data = json.loads(body) if body else None
    cors = handler._response_headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"

    return status, data, cors


class TestHealthEndpoint:

    def test_returns_ok(self, scopedb):
        status, data, cors = _make_handler(scopedb, "/api/health")
        assert status == 200
        assert data == {"status": "ok"}

    def test_cors_header_present(self, scopedb):
        _, _, cors = _make_handler(scopedb, "/api/health")
        assert cors is True


class TestCyclesEndpoint:

    def test_returns_cycles(self, scopedb):
        today = datetime.now().strftime("%Y-%m-%d")
        status, data, _ = _make_handler(scopedb, f"/api/cycles?date={today}")
        assert status == 200
        assert isinstance(data, list)
        assert len(data) == 3


class TestCycleEndpoint:

    def test_returns_cycle(self, scopedb):
        status, data, _ = _make_handler(scopedb, "/api/cycles/1")
        assert status == 200
        assert data["id"] == 1

    def test_not_found(self, scopedb):
        status, data, _ = _make_handler(scopedb, "/api/cycles/999")
        assert status == 404
        assert "error" in data


class TestCycleTraceEndpoint:

    def test_returns_trace(self, scopedb):
        status, data, _ = _make_handler(scopedb, "/api/cycles/1/trace")
        assert status == 200
        assert data["pass2_prompt"] == "classification prompt text"


class TestCorrectionsEndpoint:

    def test_returns_corrections(self, scopedb):
        status, data, _ = _make_handler(scopedb, "/api/corrections")
        assert status == 200
        assert isinstance(data, list)
        assert len(data) == 1


class TestStatsEndpoint:

    def test_correction_rate(self, scopedb):
        status, data, _ = _make_handler(scopedb, "/api/stats/correction-rate?days=30")
        assert status == 200
        assert isinstance(data, list)


class TestFewShotImpactEndpoint:

    def test_returns_impact(self, scopedb):
        status, data, _ = _make_handler(scopedb, "/api/stats/few-shot-impact?correction_id=1")
        assert status == 200
        assert data["correction_id"] == 1
        assert "before" in data
        assert "after" in data

    def test_missing_param(self, scopedb):
        status, data, _ = _make_handler(scopedb, "/api/stats/few-shot-impact")
        assert status == 400

    def test_not_found(self, scopedb):
        status, data, _ = _make_handler(scopedb, "/api/stats/few-shot-impact?correction_id=999")
        assert status == 404


class TestNotFoundEndpoint:

    def test_unknown_path(self, scopedb):
        status, data, _ = _make_handler(scopedb, "/api/nonexistent")
        assert status == 404
        assert "error" in data


class TestOptionsEndpoint:

    def test_cors_preflight(self, scopedb):
        handler = _FakeHandler("/api/health")
        handler.do_OPTIONS()

        assert handler._response_status == 204
        assert "Access-Control-Allow-Origin" in handler._response_headers
        assert "Access-Control-Allow-Methods" in handler._response_headers
