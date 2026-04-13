"""User corrections and confirmations store.

Corrections and confirmations live in the same `corrections` table,
distinguished by the `user_verdict` column (`corrected` | `confirmed`).
The table is append-only history: once a row is written, it is never
mutated. Re-correcting the same entry simply appends a new row.

See openspec change `task-recognition-loop` and its
`specs/correction-loop/spec.md` for the full requirements.
"""

from __future__ import annotations

import json
from datetime import datetime


# ── validation constants ─────────────────────────────────────────────────────

_VALID_ENTRY_KINDS = ("session", "cycle")
_VALID_USER_VERDICTS = ("corrected", "confirmed")
_VALID_USER_KINDS = (
    "on_planned_task",
    "thinking_offline",
    "meeting",
    "break",
    "other",
)
_VALID_CONFIDENCE = ("low", "medium", "high")


class CorrectionError(ValueError):
    """Raised when a correction write is rejected.

    Subclasses ValueError so callers can catch both a broad exception
    and the specific correction-loop errors. The rejection reason is
    always in the message — the corrections write path is narrow
    enough that structured error types would be overkill.
    """


# ── internal helpers ─────────────────────────────────────────────────────────

def _require(predicate, message):
    if not predicate:
        raise CorrectionError(message)


def _ensure_str(value, field):
    _require(isinstance(value, str) and value.strip(),
             f"{field} must be a non-empty string")
    return value.strip()


def _optional_str(value, field):
    if value is None:
        return None
    _require(isinstance(value, str),
             f"{field} must be a string or None (got {type(value).__name__})")
    s = value.strip()
    return s or None


def _entry_exists(db, entry_kind, entry_id):
    if entry_kind == "session":
        row = db.execute("SELECT 1 FROM sessions WHERE id=?", (entry_id,)).fetchone()
    elif entry_kind == "cycle":
        row = db.execute("SELECT 1 FROM activity_log WHERE id=?", (entry_id,)).fetchone()
    else:
        row = None
    return row is not None


def _row_to_dict(row):
    """Convert a corrections table row tuple into a dict. Keeps the
    JSON blobs (`model_evidence`, `signals`) parsed so callers don't
    repeatedly re-parse them.
    """
    (
        row_id, created_at, entry_kind, entry_id, range_start, range_end,
        model_task, model_evidence, model_boundary_conf, model_name_conf,
        user_verdict, user_task, user_kind, user_note, signals,
    ) = row

    def _load(blob, default):
        if blob is None:
            return default
        try:
            return json.loads(blob)
        except (json.JSONDecodeError, TypeError):
            return default

    return {
        "id": row_id,
        "created_at": created_at,
        "entry_kind": entry_kind,
        "entry_id": entry_id,
        "range_start": range_start,
        "range_end": range_end,
        "model_task": model_task,
        "model_evidence": _load(model_evidence, []),
        "model_boundary_confidence": model_boundary_conf,
        "model_name_confidence": model_name_conf,
        "user_verdict": user_verdict,
        "user_task": user_task,
        "user_kind": user_kind,
        "user_note": user_note,
        "signals": _load(signals, {}),
    }


# ── write path ───────────────────────────────────────────────────────────────

def record_correction(db, entry_kind, entry_id, model_state, user_state):
    """Insert one row into the `corrections` table.

    `model_state` must contain:
      - `range_start`, `range_end`        — ISO timestamps
      - `task` (nullable)                 — the model's verdict
      - `evidence` (list)                 — model's evidence list
      - `boundary_confidence`             — low|medium|high
      - `name_confidence`                 — low|medium|high
      - `signals` (dict, may be empty)    — the structured artifacts
                                            visible at the time

    `user_state` must contain:
      - `verdict`                         — corrected | confirmed
      - `user_kind`                       — one of _VALID_USER_KINDS
      - `user_task` (nullable)            — the user's corrected task
      - `user_note` (nullable)            — optional free text

    Returns the inserted row's id. Raises `CorrectionError` on any
    validation or lookup failure; never silently accepts bad input.
    """
    _require(entry_kind in _VALID_ENTRY_KINDS,
             f"entry_kind must be one of {_VALID_ENTRY_KINDS}, got {entry_kind!r}")
    _require(isinstance(entry_id, int),
             f"entry_id must be an int, got {type(entry_id).__name__}")
    _require(isinstance(model_state, dict), "model_state must be a dict")
    _require(isinstance(user_state, dict), "user_state must be a dict")

    _require(_entry_exists(db, entry_kind, entry_id),
             f"no {entry_kind} with id={entry_id} found")

    range_start = _ensure_str(model_state.get("range_start"), "model_state.range_start")
    range_end = _ensure_str(model_state.get("range_end"), "model_state.range_end")

    model_task = _optional_str(model_state.get("task"), "model_state.task")
    evidence = model_state.get("evidence", [])
    _require(isinstance(evidence, list),
             "model_state.evidence must be a list")

    model_boundary = model_state.get("boundary_confidence", "low")
    model_name = model_state.get("name_confidence", "low")
    _require(model_boundary in _VALID_CONFIDENCE,
             f"model_state.boundary_confidence must be one of {_VALID_CONFIDENCE}")
    _require(model_name in _VALID_CONFIDENCE,
             f"model_state.name_confidence must be one of {_VALID_CONFIDENCE}")

    signals = model_state.get("signals", {})
    _require(isinstance(signals, dict), "model_state.signals must be a dict")

    verdict = user_state.get("verdict")
    _require(verdict in _VALID_USER_VERDICTS,
             f"user_state.verdict must be one of {_VALID_USER_VERDICTS}")

    user_kind = user_state.get("user_kind")
    _require(user_kind in _VALID_USER_KINDS,
             f"user_state.user_kind must be one of {_VALID_USER_KINDS}")

    user_task = _optional_str(user_state.get("user_task"), "user_state.user_task")
    user_note = _optional_str(user_state.get("user_note"), "user_state.user_note")

    cursor = db.execute(
        """
        INSERT INTO corrections (
            created_at, entry_kind, entry_id, range_start, range_end,
            model_task, model_evidence, model_boundary_confidence,
            model_name_confidence, user_verdict, user_task, user_kind,
            user_note, signals
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(),
            entry_kind,
            entry_id,
            range_start,
            range_end,
            model_task,
            json.dumps(evidence),
            model_boundary,
            model_name,
            verdict,
            user_task,
            user_kind,
            user_note,
            json.dumps(signals),
        ),
    )
    db.commit()
    return cursor.lastrowid


# ── read paths ───────────────────────────────────────────────────────────────

_SELECT_COLUMNS = (
    "id, created_at, entry_kind, entry_id, range_start, range_end, "
    "model_task, model_evidence, model_boundary_confidence, "
    "model_name_confidence, user_verdict, user_task, user_kind, "
    "user_note, signals"
)


def corrections_for(db, entry_kind, entry_id):
    """Return all corrections filed against a given entry, most-recent-first."""
    rows = db.execute(
        f"SELECT {_SELECT_COLUMNS} FROM corrections "
        "WHERE entry_kind=? AND entry_id=? "
        "ORDER BY created_at DESC, id DESC",
        (entry_kind, entry_id),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def recent_corrections(db, limit):
    """Return the N most recent correction rows for few-shot retrieval.

    When `limit` is 0 or negative, returns `[]` without issuing a
    query. This is the contract the Pass 2 prompt builder relies on
    (`corrections_few_shot_n=0` disables retrieval entirely).
    """
    if not isinstance(limit, int) or limit <= 0:
        return []
    rows = db.execute(
        f"SELECT {_SELECT_COLUMNS} FROM corrections "
        "ORDER BY created_at DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]
