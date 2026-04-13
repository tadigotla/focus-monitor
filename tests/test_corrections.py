"""Tests for the corrections/confirmations store."""

from __future__ import annotations

import json

import pytest

from focusmonitor.corrections import (
    CorrectionError,
    corrections_for,
    record_correction,
    recent_corrections,
)
from focusmonitor.db import init_db


def _seed_session(db, session_id=None):
    """Insert a session row and return its id."""
    cursor = db.execute(
        """INSERT INTO sessions (
            start, end, task, task_name_confidence, boundary_confidence,
            cycle_count, dip_count, evidence_json, kind
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "2026-04-12T10:00:00",
            "2026-04-12T10:30:00",
            "auth refactor",
            "high",
            "high",
            3,
            0,
            json.dumps([{"signal": "workspace", "weight": "strong"}]),
            "session",
        ),
    )
    db.commit()
    return cursor.lastrowid


def _model_state(**overrides):
    base = {
        "range_start": "2026-04-12T10:00:00",
        "range_end": "2026-04-12T10:30:00",
        "task": "auth refactor",
        "evidence": [{"signal": "workspace", "weight": "strong"}],
        "boundary_confidence": "high",
        "name_confidence": "high",
        "signals": {
            "workspaces": ["focus-monitor"],
            "terminal_cwds": [],
            "browser_hosts": [],
        },
    }
    base.update(overrides)
    return base


def _user_state(**overrides):
    base = {
        "verdict": "corrected",
        "user_kind": "on_planned_task",
        "user_task": "auth refactor",
        "user_note": None,
    }
    base.update(overrides)
    return base


# ── happy path writes ────────────────────────────────────────────────────────

class TestRecordCorrection:

    def test_happy_path_inserts_row(self, tmp_home):
        db = init_db()
        sid = _seed_session(db)
        row_id = record_correction(db, "session", sid, _model_state(), _user_state())
        assert isinstance(row_id, int)
        # Session row unchanged.
        task = db.execute("SELECT task FROM sessions WHERE id=?", (sid,)).fetchone()[0]
        assert task == "auth refactor"
        db.close()

    def test_happy_path_confirmation(self, tmp_home):
        db = init_db()
        sid = _seed_session(db)
        row_id = record_correction(
            db, "session", sid, _model_state(),
            _user_state(verdict="confirmed"),
        )
        row = db.execute(
            "SELECT user_verdict FROM corrections WHERE id=?",
            (row_id,),
        ).fetchone()
        assert row[0] == "confirmed"
        db.close()

    def test_returns_inserted_id(self, tmp_home):
        db = init_db()
        sid = _seed_session(db)
        row_id = record_correction(db, "session", sid, _model_state(), _user_state())
        # Verify the id maps to a real row
        row = db.execute(
            "SELECT entry_kind, entry_id FROM corrections WHERE id=?",
            (row_id,),
        ).fetchone()
        assert row == ("session", sid)
        db.close()

    def test_re_correcting_appends_new_row(self, tmp_home):
        """Append-only history: correcting the same entry twice leaves
        both rows in place."""
        db = init_db()
        sid = _seed_session(db)
        first = record_correction(db, "session", sid, _model_state(), _user_state())
        second = record_correction(
            db, "session", sid, _model_state(),
            _user_state(user_task="different task"),
        )
        assert first != second
        rows = db.execute(
            "SELECT id, user_task FROM corrections WHERE entry_id=? ORDER BY id",
            (sid,),
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][1] == "auth refactor"
        assert rows[1][1] == "different task"
        db.close()


# ── rejection paths ──────────────────────────────────────────────────────────

class TestRecordCorrectionRejections:

    def test_rejects_unknown_entry_kind(self, tmp_home):
        db = init_db()
        sid = _seed_session(db)
        with pytest.raises(CorrectionError, match="entry_kind"):
            record_correction(db, "bogus", sid, _model_state(), _user_state())
        db.close()

    def test_rejects_non_existent_session(self, tmp_home):
        db = init_db()
        with pytest.raises(CorrectionError, match="no session with id=9999"):
            record_correction(db, "session", 9999, _model_state(), _user_state())
        db.close()

    def test_rejects_missing_user_kind(self, tmp_home):
        db = init_db()
        sid = _seed_session(db)
        with pytest.raises(CorrectionError, match="user_kind"):
            record_correction(
                db, "session", sid, _model_state(),
                _user_state(user_kind=None),
            )
        db.close()

    def test_rejects_invalid_user_kind(self, tmp_home):
        db = init_db()
        sid = _seed_session(db)
        with pytest.raises(CorrectionError, match="user_kind"):
            record_correction(
                db, "session", sid, _model_state(),
                _user_state(user_kind="something_made_up"),
            )
        db.close()

    def test_rejects_invalid_verdict(self, tmp_home):
        db = init_db()
        sid = _seed_session(db)
        with pytest.raises(CorrectionError, match="verdict"):
            record_correction(
                db, "session", sid, _model_state(),
                _user_state(verdict="maybe"),
            )
        db.close()

    def test_rejects_missing_range(self, tmp_home):
        db = init_db()
        sid = _seed_session(db)
        with pytest.raises(CorrectionError, match="range_start"):
            record_correction(
                db, "session", sid,
                _model_state(range_start=""),
                _user_state(),
            )
        db.close()

    def test_rejects_invalid_confidence(self, tmp_home):
        db = init_db()
        sid = _seed_session(db)
        with pytest.raises(CorrectionError, match="boundary_confidence"):
            record_correction(
                db, "session", sid,
                _model_state(boundary_confidence="ultra"),
                _user_state(),
            )
        db.close()

    def test_rejects_evidence_not_a_list(self, tmp_home):
        db = init_db()
        sid = _seed_session(db)
        with pytest.raises(CorrectionError, match="evidence"):
            record_correction(
                db, "session", sid,
                _model_state(evidence="not a list"),
                _user_state(),
            )
        db.close()

    def test_rejects_signals_not_a_dict(self, tmp_home):
        db = init_db()
        sid = _seed_session(db)
        with pytest.raises(CorrectionError, match="signals"):
            record_correction(
                db, "session", sid,
                _model_state(signals=["not a dict"]),
                _user_state(),
            )
        db.close()

    def test_rejects_non_dict_model_state(self, tmp_home):
        db = init_db()
        sid = _seed_session(db)
        with pytest.raises(CorrectionError, match="model_state"):
            record_correction(db, "session", sid, "not a dict", _user_state())
        db.close()


# ── read: corrections_for ────────────────────────────────────────────────────

class TestCorrectionsFor:

    def test_empty_store_returns_empty_list(self, tmp_home):
        db = init_db()
        sid = _seed_session(db)
        assert corrections_for(db, "session", sid) == []
        db.close()

    def test_returns_most_recent_first(self, tmp_home):
        db = init_db()
        sid = _seed_session(db)
        record_correction(db, "session", sid, _model_state(),
                          _user_state(user_task="first"))
        record_correction(db, "session", sid, _model_state(),
                          _user_state(user_task="second"))
        result = corrections_for(db, "session", sid)
        assert len(result) == 2
        assert result[0]["user_task"] == "second"
        assert result[1]["user_task"] == "first"
        db.close()

    def test_filters_by_entry(self, tmp_home):
        db = init_db()
        sid_a = _seed_session(db)
        sid_b = _seed_session(db)
        record_correction(db, "session", sid_a, _model_state(),
                          _user_state(user_task="a"))
        record_correction(db, "session", sid_b, _model_state(),
                          _user_state(user_task="b"))
        result_a = corrections_for(db, "session", sid_a)
        result_b = corrections_for(db, "session", sid_b)
        assert len(result_a) == 1
        assert result_a[0]["user_task"] == "a"
        assert len(result_b) == 1
        assert result_b[0]["user_task"] == "b"
        db.close()

    def test_parses_json_blobs_back(self, tmp_home):
        db = init_db()
        sid = _seed_session(db)
        record_correction(db, "session", sid, _model_state(), _user_state())
        result = corrections_for(db, "session", sid)
        assert result[0]["model_evidence"] == [
            {"signal": "workspace", "weight": "strong"}
        ]
        assert result[0]["signals"]["workspaces"] == ["focus-monitor"]
        db.close()


# ── read: recent_corrections ─────────────────────────────────────────────────

class TestRecentCorrections:

    def test_zero_limit_short_circuits_no_query(self, tmp_home):
        """Spy on execute calls: passing limit=0 must not issue any
        query against the corrections table at all. We wrap the real
        connection in a spy so sqlite3.Connection.execute being
        read-only doesn't get in the way."""
        real_db = init_db()
        sid = _seed_session(real_db)
        record_correction(real_db, "session", sid, _model_state(), _user_state())

        issued = []

        class SpyConn:
            def execute(self, sql, *args, **kw):
                issued.append(sql)
                return real_db.execute(sql, *args, **kw)

            def commit(self):
                return real_db.commit()

            def close(self):
                return real_db.close()

        spy = SpyConn()
        result = recent_corrections(spy, 0)
        assert result == []
        # Zero issued queries — not just zero SELECTs — the contract
        # is no DB work at all when retrieval is disabled.
        assert issued == []
        real_db.close()

    def test_negative_limit_returns_empty(self, tmp_home):
        db = init_db()
        assert recent_corrections(db, -5) == []
        db.close()

    def test_partial_fill(self, tmp_home):
        db = init_db()
        sid = _seed_session(db)
        record_correction(db, "session", sid, _model_state(),
                          _user_state(user_task="only"))
        result = recent_corrections(db, 5)
        assert len(result) == 1
        assert result[0]["user_task"] == "only"
        db.close()

    def test_limit_respected(self, tmp_home):
        db = init_db()
        sid = _seed_session(db)
        for i in range(7):
            record_correction(db, "session", sid, _model_state(),
                              _user_state(user_task=f"task-{i}"))
        result = recent_corrections(db, 3)
        assert len(result) == 3
        # Most recent first.
        assert result[0]["user_task"] == "task-6"
        assert result[1]["user_task"] == "task-5"
        assert result[2]["user_task"] == "task-4"
        db.close()

    def test_empty_store(self, tmp_home):
        db = init_db()
        assert recent_corrections(db, 5) == []
        db.close()

    def test_mixed_confirmations_and_corrections(self, tmp_home):
        db = init_db()
        sid = _seed_session(db)
        record_correction(db, "session", sid, _model_state(),
                          _user_state(verdict="corrected", user_task="corrected one"))
        record_correction(db, "session", sid, _model_state(),
                          _user_state(verdict="confirmed", user_task="confirmed one"))
        result = recent_corrections(db, 5)
        assert len(result) == 2
        verdicts = [r["user_verdict"] for r in result]
        assert "corrected" in verdicts
        assert "confirmed" in verdicts
