"""Tests for the SQLite schema-init path.

Covers the invariants specified in the openspec change
`task-recognition-loop`:

  - `init_db` creates `sessions` and `corrections` tables on a fresh DB.
  - Existing `activity_log` schema is unchanged (no new or renamed
    columns).
  - Re-running `init_db` against an already-initialized DB is a no-op.
"""

from __future__ import annotations

from focusmonitor.db import init_db


def _table_exists(db, name):
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _column_names(db, table):
    return [row[1] for row in db.execute(f"PRAGMA table_info({table})").fetchall()]


def test_init_db_creates_sessions_table(tmp_home):
    db = init_db()
    try:
        assert _table_exists(db, "sessions")
        cols = set(_column_names(db, "sessions"))
        expected = {
            "id", "start", "end", "task",
            "task_name_confidence", "boundary_confidence",
            "cycle_count", "dip_count", "evidence_json", "kind",
        }
        assert expected <= cols
    finally:
        db.close()


def test_init_db_creates_corrections_table(tmp_home):
    db = init_db()
    try:
        assert _table_exists(db, "corrections")
        cols = set(_column_names(db, "corrections"))
        expected = {
            "id", "created_at", "entry_kind", "entry_id",
            "range_start", "range_end",
            "model_task", "model_evidence",
            "model_boundary_confidence", "model_name_confidence",
            "user_verdict", "user_task", "user_kind", "user_note",
            "signals",
        }
        assert expected <= cols
    finally:
        db.close()


def test_init_db_preserves_activity_log_schema(tmp_home):
    db = init_db()
    try:
        assert _table_exists(db, "activity_log")
        cols = _column_names(db, "activity_log")
        # Back-compat: exact column set must match what rows written
        # before this change expect to read back.
        assert cols == [
            "id",
            "timestamp",
            "window_titles",
            "apps_used",
            "project_detected",
            "is_distraction",
            "summary",
            "raw_response",
        ]
    finally:
        db.close()


def test_init_db_preserves_nudges_schema(tmp_home):
    db = init_db()
    try:
        assert _table_exists(db, "nudges")
        cols = _column_names(db, "nudges")
        assert cols == ["id", "timestamp", "task", "message"]
    finally:
        db.close()


def test_init_db_is_idempotent(tmp_home):
    db1 = init_db()
    db1.execute(
        "INSERT INTO activity_log (timestamp, summary) VALUES (?, ?)",
        ("2026-04-12T15:00:00", "test row"),
    )
    db1.commit()
    db1.close()

    db2 = init_db()
    try:
        # The row from the first open must still be there — init_db
        # must not drop or recreate existing tables.
        rows = db2.execute(
            "SELECT timestamp, summary FROM activity_log"
        ).fetchall()
        assert rows == [("2026-04-12T15:00:00", "test row")]
        # And both new tables must exist.
        assert _table_exists(db2, "sessions")
        assert _table_exists(db2, "corrections")
    finally:
        db2.close()


def test_init_db_creates_analysis_traces_table(tmp_home):
    db = init_db()
    try:
        assert _table_exists(db, "analysis_traces")
        cols = set(_column_names(db, "analysis_traces"))
        expected = {
            "id", "activity_log_id", "created_at",
            "pass1_prompts_json", "pass1_responses_json",
            "pass1_elapsed_ms_json",
            "pass2_prompt", "pass2_response_raw", "pass2_elapsed_ms",
            "few_shot_ids_json", "screenshot_paths_json",
            "parse_retries",
        }
        assert expected <= cols
    finally:
        db.close()


def test_analysis_traces_indexes_present(tmp_home):
    db = init_db()
    try:
        indexes = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='analysis_traces'"
            ).fetchall()
        }
        assert "idx_traces_activity_log_id" in indexes
        assert "idx_traces_created_at" in indexes
    finally:
        db.close()


def test_corrections_indexes_present(tmp_home):
    db = init_db()
    try:
        indexes = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='corrections'"
            ).fetchall()
        }
        assert "idx_corrections_created_at" in indexes
        assert "idx_corrections_entry" in indexes
    finally:
        db.close()
