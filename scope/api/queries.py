"""Read-only query functions for the Scope API.

Each function takes a sqlite3.Connection and returns Python dicts/lists.
The HTTP layer serializes them to JSON. No function writes to the DB.
"""

import json
from datetime import datetime, timedelta


def _parse_json(blob, default=None):
    if blob is None:
        return default
    try:
        return json.loads(blob)
    except (json.JSONDecodeError, TypeError):
        return default


def _date_range(date_str):
    """Return (start_iso, end_iso) for a YYYY-MM-DD date string."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        d = datetime.now()
    start = d.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


# ── Cycles ──────────────────────────────────────────────────────────────────

def get_cycles(db, date, limit=50, offset=0):
    start, end = _date_range(date)
    rows = db.execute(
        "SELECT id, timestamp, summary, raw_response "
        "FROM activity_log WHERE timestamp >= ? AND timestamp < ? "
        "ORDER BY timestamp ASC LIMIT ? OFFSET ?",
        (start, end, limit, offset),
    ).fetchall()
    cycles = []
    for row_id, ts, summary, raw in rows:
        parsed = _parse_json(raw, {})
        cycles.append({
            "id": row_id,
            "timestamp": ts,
            "task": parsed.get("task"),
            "focus_score": parsed.get("focus_score", -1),
            "name_confidence": parsed.get("name_confidence", "low"),
            "boundary_confidence": parsed.get("boundary_confidence", "low"),
            "summary": summary or "",
        })
    return cycles


def get_cycle(db, cycle_id):
    row = db.execute(
        "SELECT id, timestamp, window_titles, apps_used, "
        "project_detected, is_distraction, summary, raw_response "
        "FROM activity_log WHERE id = ?",
        (cycle_id,),
    ).fetchone()
    if row is None:
        return None
    row_id, ts, titles, apps, projects, distraction, summary, raw = row
    parsed = _parse_json(raw, {})
    return {
        "id": row_id,
        "timestamp": ts,
        "window_titles": _parse_json(titles, []),
        "apps_used": _parse_json(apps, []),
        "project_detected": _parse_json(projects, []),
        "is_distraction": bool(distraction),
        "summary": summary or "",
        "raw_response": parsed,
    }


# ── Traces ──────────────────────────────────────────────────────────────────

def get_cycle_trace(db, cycle_id):
    try:
        row = db.execute(
            "SELECT id, activity_log_id, created_at, "
            "pass1_prompts_json, pass1_responses_json, pass1_elapsed_ms_json, "
            "pass2_prompt, pass2_response_raw, pass2_elapsed_ms, "
            "few_shot_ids_json, screenshot_paths_json, parse_retries "
            "FROM analysis_traces WHERE activity_log_id = ?",
            (cycle_id,),
        ).fetchone()
    except Exception:
        # Table may not exist for DBs created before trace logging
        return None
    if row is None:
        return None
    (trace_id, al_id, created, p1_prompts, p1_responses, p1_elapsed,
     p2_prompt, p2_raw, p2_elapsed, fs_ids, ss_paths, retries) = row
    return {
        "id": trace_id,
        "activity_log_id": al_id,
        "created_at": created,
        "pass1_prompt": _parse_json(p1_prompts),
        "pass1_responses": _parse_json(p1_responses, []),
        "pass1_elapsed_ms": _parse_json(p1_elapsed, []),
        "pass2_prompt": p2_prompt,
        "pass2_response_raw": p2_raw,
        "pass2_elapsed_ms": p2_elapsed,
        "few_shot_ids": _parse_json(fs_ids, []),
        "screenshot_paths": _parse_json(ss_paths, []),
        "parse_retries": retries or 0,
    }


# ── Corrections ─────────────────────────────────────────────────────────────

def _correction_row_to_dict(row):
    (cid, created, ekind, eid, rstart, rend, mtask, mevidence,
     mbconf, mnconf, uverdict, utask, ukind, unote, signals) = row
    return {
        "id": cid,
        "created_at": created,
        "entry_kind": ekind,
        "entry_id": eid,
        "range_start": rstart,
        "range_end": rend,
        "model_task": mtask,
        "model_evidence": _parse_json(mevidence, []),
        "model_boundary_confidence": mbconf,
        "model_name_confidence": mnconf,
        "user_verdict": uverdict,
        "user_task": utask,
        "user_kind": ukind,
        "user_note": unote,
        "signals": _parse_json(signals, {}),
    }


_CORRECTIONS_COLS = (
    "id, created_at, entry_kind, entry_id, range_start, range_end, "
    "model_task, model_evidence, model_boundary_confidence, "
    "model_name_confidence, user_verdict, user_task, user_kind, "
    "user_note, signals"
)


def get_cycle_corrections(db, cycle_id):
    rows = db.execute(
        f"SELECT {_CORRECTIONS_COLS} FROM corrections "
        "WHERE entry_kind='cycle' AND entry_id=? "
        "ORDER BY created_at DESC",
        (cycle_id,),
    ).fetchall()
    return [_correction_row_to_dict(r) for r in rows]


def get_corrections(db, limit=50, offset=0):
    rows = db.execute(
        f"SELECT {_CORRECTIONS_COLS} FROM corrections "
        "ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return [_correction_row_to_dict(r) for r in rows]


# ── Sessions ────────────────────────────────────────────────────────────────

def get_sessions(db, date):
    start, end = _date_range(date)
    rows = db.execute(
        "SELECT id, start, end, task, task_name_confidence, "
        "boundary_confidence, cycle_count, dip_count, evidence_json, kind "
        "FROM sessions WHERE start >= ? AND start < ? "
        "ORDER BY start ASC",
        (start, end),
    ).fetchall()
    sessions = []
    for (sid, s, e, task, tnc, bc, cc, dc, ej, kind) in rows:
        sessions.append({
            "id": sid,
            "start": s,
            "end": e,
            "task": task,
            "task_name_confidence": tnc,
            "boundary_confidence": bc,
            "cycle_count": cc,
            "dip_count": dc,
            "evidence": _parse_json(ej, []),
            "kind": kind,
        })
    return sessions


def get_session(db, session_id):
    row = db.execute(
        "SELECT id, start, end, task, task_name_confidence, "
        "boundary_confidence, cycle_count, dip_count, evidence_json, kind "
        "FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    sid, s, e, task, tnc, bc, cc, dc, ej, kind = row
    # Find constituent cycle IDs by time range overlap
    cycle_ids = [
        r[0] for r in db.execute(
            "SELECT id FROM activity_log "
            "WHERE timestamp >= ? AND timestamp <= ? "
            "ORDER BY timestamp ASC",
            (s, e),
        ).fetchall()
    ]
    return {
        "id": sid,
        "start": s,
        "end": e,
        "task": task,
        "task_name_confidence": tnc,
        "boundary_confidence": bc,
        "cycle_count": cc,
        "dip_count": dc,
        "evidence": _parse_json(ej, []),
        "kind": kind,
        "cycle_ids": cycle_ids,
    }


# ── Stats ───────────────────────────────────────────────────────────────────

def get_correction_rate(db, days=30):
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    # Get per-day cycle counts
    cycle_rows = db.execute(
        "SELECT DATE(timestamp) as d, COUNT(*) "
        "FROM activity_log WHERE DATE(timestamp) >= ? "
        "GROUP BY d ORDER BY d",
        (cutoff,),
    ).fetchall()
    # Get per-day correction counts
    corr_rows = db.execute(
        "SELECT DATE(created_at) as d, COUNT(*) "
        "FROM corrections WHERE user_verdict='corrected' "
        "AND DATE(created_at) >= ? "
        "GROUP BY d ORDER BY d",
        (cutoff,),
    ).fetchall()
    corr_map = {d: c for d, c in corr_rows}
    result = []
    for d, total in cycle_rows:
        corrections = corr_map.get(d, 0)
        rate = corrections / total if total > 0 else 0.0
        result.append({
            "date": d,
            "total_cycles": total,
            "corrections": corrections,
            "rate": round(rate, 4),
        })
    return result


def get_confidence_calibration(db):
    result = {}
    for level in ("high", "medium", "low"):
        # Count cycles at this name_confidence level
        # raw_response is JSON, extract name_confidence via LIKE
        total_row = db.execute(
            "SELECT COUNT(*) FROM activity_log "
            "WHERE raw_response LIKE ?",
            (f'%"name_confidence": "{level}"%',),
        ).fetchone()
        total = total_row[0] if total_row else 0

        # Count how many of those were corrected
        # Join via activity_log.id = corrections.entry_id where entry_kind='cycle'
        corrected_row = db.execute(
            "SELECT COUNT(DISTINCT al.id) FROM activity_log al "
            "INNER JOIN corrections c ON c.entry_id = al.id "
            "AND c.entry_kind = 'cycle' AND c.user_verdict = 'corrected' "
            "WHERE al.raw_response LIKE ?",
            (f'%"name_confidence": "{level}"%',),
        ).fetchone()
        corrected = corrected_row[0] if corrected_row else 0

        accuracy = (total - corrected) / total if total > 0 else 0.0
        result[level] = {
            "total": total,
            "corrected": corrected,
            "accuracy": round(accuracy, 4),
        }
    return result


def get_per_task_accuracy(db):
    # Get all cycles with a non-null task
    rows = db.execute(
        "SELECT al.id, al.raw_response FROM activity_log al"
    ).fetchall()

    task_stats = {}  # task_name -> {total, corrected}
    for al_id, raw in rows:
        parsed = _parse_json(raw, {})
        task = parsed.get("task")
        if task is None:
            task = "(unrecognized)"
        if task not in task_stats:
            task_stats[task] = {"total": 0, "corrected": 0}
        task_stats[task]["total"] += 1

    # Get corrected cycle IDs with user-provided task names
    corr_rows = db.execute(
        "SELECT entry_id, user_task FROM corrections "
        "WHERE entry_kind='cycle' AND user_verdict='corrected'"
    ).fetchall()

    # Map cycle IDs to their model task for counting
    for al_id, raw in rows:
        parsed = _parse_json(raw, {})
        task = parsed.get("task") or "(unrecognized)"
        was_corrected = any(cid == al_id for cid, _ in corr_rows)
        if was_corrected:
            task_stats[task]["corrected"] += 1

    result = []
    for task, stats in sorted(task_stats.items(), key=lambda x: -x[1]["total"]):
        total = stats["total"]
        corrected = stats["corrected"]
        accuracy = (total - corrected) / total if total > 0 else 0.0
        result.append({
            "task": task,
            "total": total,
            "corrected": corrected,
            "accuracy": round(accuracy, 4),
        })
    return result


def get_few_shot_impact(db, correction_id):
    """Measure accuracy on similar cycles before/after a correction.

    "Similar" = cycles sharing at least one workspace, terminal_cwd,
    or browser_host with the correction's signals field.
    """
    row = db.execute(
        f"SELECT {_CORRECTIONS_COLS} FROM corrections WHERE id = ?",
        (correction_id,),
    ).fetchone()
    if row is None:
        return None

    corr = _correction_row_to_dict(row)
    corr_ts = corr["created_at"]
    signals = corr.get("signals") or {}

    # Extract signal values to match against cycle_signals in raw_response
    match_values = set()
    for key in ("workspaces", "terminal_cwds", "browser_hosts"):
        vals = signals.get(key)
        if isinstance(vals, list):
            match_values.update(v for v in vals if v)

    if not match_values:
        return {
            "correction_id": correction_id,
            "correction": corr,
            "signal_overlap": [],
            "before": {"total": 0, "corrected": 0, "accuracy": 0},
            "after": {"total": 0, "corrected": 0, "accuracy": 0},
        }

    # Get all cycles and check for signal overlap
    all_cycles = db.execute(
        "SELECT id, timestamp, raw_response FROM activity_log"
    ).fetchall()

    corrected_ids = {
        r[0] for r in db.execute(
            "SELECT entry_id FROM corrections "
            "WHERE entry_kind='cycle' AND user_verdict='corrected'"
        ).fetchall()
    }

    before = {"total": 0, "corrected": 0}
    after = {"total": 0, "corrected": 0}

    for al_id, ts, raw in all_cycles:
        parsed = _parse_json(raw, {})
        cycle_signals = parsed.get("cycle_signals", {})
        cycle_values = set()
        for key in ("workspaces", "terminal_cwds", "browser_hosts"):
            vals = cycle_signals.get(key)
            if isinstance(vals, list):
                cycle_values.update(v for v in vals if v)

        if not match_values & cycle_values:
            continue

        bucket = after if ts >= corr_ts else before
        bucket["total"] += 1
        if al_id in corrected_ids:
            bucket["corrected"] += 1

    def _acc(b):
        t = b["total"]
        return round((t - b["corrected"]) / t, 4) if t > 0 else 0

    return {
        "correction_id": correction_id,
        "correction": corr,
        "signal_overlap": sorted(match_values),
        "before": {**before, "accuracy": _acc(before)},
        "after": {**after, "accuracy": _acc(after)},
    }
