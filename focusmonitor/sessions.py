"""Deterministic session aggregation.

Turns per-cycle analysis rows into coherent `sessions` — the unit the
dashboard actually shows. Everything here is a pure function plus a
thin SQLite writer; no LLM calls, no external HTTP beyond an AW afk
fetch that fails open when ActivityWatch is unreachable.

See openspec change `task-recognition-loop` and its
`specs/session-aggregation/spec.md` for the requirements this
implements.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError

from focusmonitor.activitywatch import _parse_aw_ts


# ── glue rules ───────────────────────────────────────────────────────────────

# The set of pairwise glue predicates the segmentation pass tries, in order.
# Documented here so a future tweak to the ruleset is one list edit instead
# of a scavenger hunt through branching code.
_GLUE_SIGNALS = (
    "workspace",          # shared non-null workspace (case-insensitive)
    "terminal_cwd",       # shared non-null terminal cwd (case-insensitive)
    "browser_host",       # shared non-null browser URL host (case-insensitive)
    "task_name",          # same task name, both cycles at name_conf >= medium
)


_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
_WEIGHT_RANK = {"weak": 0, "medium": 1, "strong": 2}


# ── small utilities ──────────────────────────────────────────────────────────

def _parse_iso(value):
    """Parse an ISO-8601 string into an aware or naive datetime.

    focus-monitor writes naive local isoformat timestamps (via
    `datetime.now().isoformat()`), but AW events are UTC with a `Z`
    suffix. Accept both so the aggregator can mix the two when
    applying the afk overlay.
    """
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise TypeError(f"expected ISO string or datetime, got {type(value).__name__}")
    clean = value.strip()
    if clean.endswith("Z"):
        clean = clean[:-1] + "+00:00"
    return datetime.fromisoformat(clean)


def _to_naive(dt):
    """Strip tzinfo so comparisons across aware and naive values work.

    focus-monitor analysis rows are naive local time; AW events are
    UTC-aware. The afk overlay crosses both sources. Dropping tzinfo
    means the overlay silently assumes both clocks are on the same
    wall time — which is true for the single-user local machine this
    product targets, but explicitly false if AW is ever pointed at
    a UTC-offset server. That would be a separate design change.
    """
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _browser_host(url):
    """Return the lowercased host portion of a URL string, or None."""
    if not url or not isinstance(url, str):
        return None
    s = url.strip()
    for prefix in ("https://", "http://"):
        if s.lower().startswith(prefix):
            s = s[len(prefix):]
            break
    host = s.split("/", 1)[0].split("?", 1)[0]
    return host.lower() or None


def _min_confidence(levels):
    if not levels:
        return "low"
    return min(levels, key=lambda lvl: _CONFIDENCE_RANK.get(lvl, 0))


def _segment_duration_seconds(segment_pairs):
    """Total span (first.start → last.end) in seconds for a list of
    (cycle, is_dip) pairs. Not a sum of durations — we care about the
    wall-clock window, not screen-time.
    """
    if not segment_pairs:
        return 0.0
    first_cycle = segment_pairs[0][0]
    last_cycle = segment_pairs[-1][0]
    start = _to_naive(_parse_iso(first_cycle["start"]))
    end = _to_naive(_parse_iso(last_cycle["end"]))
    return max(0.0, (end - start).total_seconds())


# ── pass 1 artifact → cycle signal extraction ────────────────────────────────

def extract_cycle_signals(artifacts):
    """Given a list of Pass 1 structured artifacts for one cycle, return
    the distinct workspaces, terminal cwds, and browser hosts seen across
    them. The aggregator uses these as the glue signature.
    """
    workspaces = []
    cwds = []
    hosts = []
    seen_ws = set()
    seen_cwd = set()
    seen_host = set()
    for art in (artifacts or []):
        if not isinstance(art, dict):
            continue
        ws = art.get("workspace")
        if isinstance(ws, str) and ws.strip() and ws.strip().lower() not in seen_ws:
            workspaces.append(ws.strip())
            seen_ws.add(ws.strip().lower())
        cwd = art.get("terminal_cwd")
        if isinstance(cwd, str) and cwd.strip() and cwd.strip().lower() not in seen_cwd:
            cwds.append(cwd.strip())
            seen_cwd.add(cwd.strip().lower())
        host = _browser_host(art.get("browser_url"))
        if host and host not in seen_host:
            hosts.append(host)
            seen_host.add(host)
    return {
        "workspaces": workspaces,
        "terminal_cwds": cwds,
        "browser_hosts": hosts,
    }


# ── pairwise glue predicate ──────────────────────────────────────────────────

def _lower_set(values):
    return {str(v).strip().lower() for v in (values or []) if str(v).strip()}


def _cycles_glue(a, b):
    """Return True iff two consecutive cycles belong to the same session.

    Applies each rule in `_GLUE_SIGNALS` in order. Short-circuits on
    the first match.
    """
    ws_a = _lower_set(a.get("workspaces"))
    ws_b = _lower_set(b.get("workspaces"))
    if ws_a & ws_b:
        return True

    cwd_a = _lower_set(a.get("terminal_cwds"))
    cwd_b = _lower_set(b.get("terminal_cwds"))
    if cwd_a & cwd_b:
        return True

    host_a = _lower_set(a.get("browser_hosts"))
    host_b = _lower_set(b.get("browser_hosts"))
    if host_a & host_b:
        return True

    task_a = (a.get("task") or "").strip().lower() or None
    task_b = (b.get("task") or "").strip().lower() or None
    if task_a and task_a == task_b:
        conf_a = a.get("name_confidence", "low")
        conf_b = b.get("name_confidence", "low")
        if (
            _CONFIDENCE_RANK.get(conf_a, 0) >= _CONFIDENCE_RANK["medium"]
            and _CONFIDENCE_RANK.get(conf_b, 0) >= _CONFIDENCE_RANK["medium"]
        ):
            return True

    return False


# ── segmentation + dip absorption ────────────────────────────────────────────

def _segment(cycles):
    """Greedy pairwise segmentation of consecutive cycles.

    Produces a list of segments, each a non-empty list of cycle dicts.
    Consecutive cycles that glue land in the same segment; the first
    cycle that doesn't glue to the one before it starts a new segment.
    """
    if not cycles:
        return []
    segments = [[cycles[0]]]
    for prev_i in range(1, len(cycles)):
        prev = cycles[prev_i - 1]
        curr = cycles[prev_i]
        if _cycles_glue(prev, curr):
            segments[-1].append(curr)
        else:
            segments.append([curr])
    return segments


def _apply_dips(segments, dip_tolerance_sec):
    """Absorb short non-matching segments into their neighbors.

    A segment is a "dip" when:
      * Its wall-clock duration is ≤ dip_tolerance_sec, AND
      * The last cycle of the segment before it would glue to the
        first cycle of the segment after it (i.e. the neighbors form
        one coherent session without the dip in the middle).

    The dip's cycles are marked is_dip=True so evidence aggregation
    can ignore them later; the session's `dip_count` is incremented by
    how many cycles the dip contributed.

    Returns: list of segments, each a list of `(cycle, is_dip)` tuples.
    """
    marked = [[(c, False) for c in seg] for seg in segments]
    if len(marked) < 2:
        return marked

    out = []
    i = 0
    while i < len(marked):
        if not out:
            out.append(marked[i])
            i += 1
            continue

        curr = marked[i]
        # Only the middle segments can be absorbed — a dip needs both
        # a left and a right neighbor.
        can_dip = (
            i + 1 < len(marked)
            and _segment_duration_seconds(curr) <= dip_tolerance_sec
            and _cycles_glue(out[-1][-1][0], marked[i + 1][0][0])
        )
        if can_dip:
            for c, _ in curr:
                out[-1].append((c, True))
            for c, _ in marked[i + 1]:
                out[-1].append((c, False))
            i += 2
        else:
            out.append(curr)
            i += 1
    return out


# ── evidence aggregation ─────────────────────────────────────────────────────

def _aggregate_evidence(cycles):
    """Union strong+medium signals across the given cycles, dedup by
    signal string, prefer the stronger weight on collisions.

    Weak-weight signals are dropped entirely. The returned list is
    ordered by weight (strong before medium) then alphabetically so
    the dashboard rendering is stable.
    """
    best = {}
    for cycle in cycles:
        for entry in cycle.get("evidence", []) or []:
            if not isinstance(entry, dict):
                continue
            signal = entry.get("signal")
            weight = entry.get("weight")
            if not isinstance(signal, str) or not signal.strip():
                continue
            if weight not in ("strong", "medium"):
                continue
            key = signal.strip()
            prev = best.get(key)
            if prev is None or _WEIGHT_RANK[weight] > _WEIGHT_RANK[prev]:
                best[key] = weight
    return [
        {"signal": s, "weight": w}
        for s, w in sorted(
            best.items(),
            key=lambda kv: (-_WEIGHT_RANK[kv[1]], kv[0]),
        )
    ]


# ── session emission ─────────────────────────────────────────────────────────

def _emit_active_sessions(segments_with_flags):
    """Turn marked segments into session dicts. Single-cycle segments
    whose one main cycle has name_confidence=low become `unclear`
    entries rather than sessions; everything else is a `session`.
    """
    sessions = []
    for segment in segments_with_flags:
        if not segment:
            continue
        all_cycles = [c for c, _ in segment]
        main_cycles = [c for c, is_dip in segment if not is_dip]
        dip_count = sum(1 for _, is_dip in segment if is_dip)

        if not main_cycles:
            continue  # pathological: segment is all dip — skip

        # Standalone unclear: exactly one main cycle AND its name
        # confidence is "low". Glue rules guarantee that a low-confidence
        # cycle with no signal overlap against either neighbor lands in
        # a segment of its own.
        is_unclear = (
            len(main_cycles) == 1
            and main_cycles[0].get("name_confidence", "low") == "low"
        )

        # Canonical task name: first non-null task among main cycles.
        task = None
        if not is_unclear:
            for c in main_cycles:
                t = c.get("task")
                if isinstance(t, str) and t.strip():
                    task = t.strip()
                    break

        name_confs = [c.get("name_confidence", "low") for c in main_cycles]
        boundary_confs = [c.get("boundary_confidence", "low") for c in main_cycles]

        sessions.append({
            "kind": "unclear" if is_unclear else "session",
            "start": all_cycles[0]["start"],
            "end": all_cycles[-1]["end"],
            "task": None if is_unclear else task,
            "task_name_confidence": _min_confidence(name_confs),
            "boundary_confidence": _min_confidence(boundary_confs),
            "cycle_count": len(all_cycles),
            "dip_count": dip_count,
            "evidence": _aggregate_evidence(main_cycles),
            "cycle_ids": [c.get("id") for c in all_cycles],
        })
    return sessions


def _emit_away_entry(away_cycles):
    """Collapse a run of afk-marked cycles into a single away entry."""
    return {
        "kind": "away",
        "start": away_cycles[0]["start"],
        "end": away_cycles[-1]["end"],
        "task": None,
        "task_name_confidence": "low",
        "boundary_confidence": "high",
        "cycle_count": len(away_cycles),
        "dip_count": 0,
        "evidence": [],
        "cycle_ids": [c.get("id") for c in away_cycles],
    }


# ── public pure aggregator ───────────────────────────────────────────────────

def aggregate(cycles, dip_tolerance_sec=300):
    """Aggregate an ordered list of cycle dicts into session/unclear/away
    entries.

    Each cycle dict must carry at least:
      - `start`, `end` — ISO timestamps
      - `task`, `name_confidence`, `boundary_confidence`
      - `workspaces`, `terminal_cwds`, `browser_hosts` — lists
      - `evidence` — list of `{signal, weight}`

    A cycle can additionally carry `kind="away"` (set by the afk
    overlay) to be emitted as part of an away run instead of going
    through session glue.

    The function is pure: same input, same output. No DB, no HTTP,
    no clock reads.
    """
    if not cycles:
        return []

    result = []
    i = 0
    while i < len(cycles):
        if cycles[i].get("kind") == "away":
            start_i = i
            while i < len(cycles) and cycles[i].get("kind") == "away":
                i += 1
            result.append(_emit_away_entry(cycles[start_i:i]))
            continue

        # Collect consecutive non-away cycles and run the glue+dip pipeline.
        start_i = i
        while i < len(cycles) and cycles[i].get("kind") != "away":
            i += 1
        active = cycles[start_i:i]
        segments = _segment(active)
        with_dips = _apply_dips(segments, dip_tolerance_sec)
        result.extend(_emit_active_sessions(with_dips))

    return result


# ── afk overlay ──────────────────────────────────────────────────────────────

def aw_afk_overlay(cycles, afk_events, threshold=0.5):
    """Return a new cycles list with `kind="away"` set on cycles that
    overlap ≥ `threshold` (fraction) with afk events.

    `afk_events` is the list shape AW's query endpoint returns:
    `[{"timestamp": iso, "duration": seconds, "data": {"status": "afk"|"not-afk"}}, ...]`.
    """
    # Pre-parse afk intervals once.
    afk_intervals = []
    for ev in (afk_events or []):
        if not isinstance(ev, dict):
            continue
        status = (ev.get("data") or {}).get("status") if isinstance(ev.get("data"), dict) else None
        if status != "afk":
            continue
        try:
            e_start = _to_naive(_parse_iso(ev["timestamp"]))
        except (KeyError, ValueError, TypeError):
            continue
        try:
            duration = float(ev.get("duration", 0) or 0)
        except (TypeError, ValueError):
            duration = 0.0
        e_end = e_start + timedelta(seconds=duration)
        if e_end > e_start:
            afk_intervals.append((e_start, e_end))

    result = []
    for cycle in cycles:
        new_cycle = dict(cycle)
        try:
            c_start = _to_naive(_parse_iso(cycle["start"]))
            c_end = _to_naive(_parse_iso(cycle["end"]))
        except (KeyError, ValueError, TypeError):
            new_cycle.setdefault("kind", "session")
            result.append(new_cycle)
            continue

        total_sec = (c_end - c_start).total_seconds()
        if total_sec <= 0:
            new_cycle.setdefault("kind", "session")
            result.append(new_cycle)
            continue

        overlap_sec = 0.0
        for (a_start, a_end) in afk_intervals:
            lo = max(c_start, a_start)
            hi = min(c_end, a_end)
            if hi > lo:
                overlap_sec += (hi - lo).total_seconds()

        if overlap_sec / total_sec >= threshold:
            new_cycle["kind"] = "away"
        else:
            new_cycle.setdefault("kind", "session")
        result.append(new_cycle)

    return result


# ── AW afk fetch (defensive, fail-open) ──────────────────────────────────────

def fetch_afk_events(cfg, start_iso, end_iso):
    """Fetch raw afk events from ActivityWatch for the given range.

    Returns an empty list on any error (bucket missing, HTTP failure,
    malformed response). The aggregator continues with cycle-only
    analysis when the overlay has nothing to apply.
    """
    base = cfg.get("activitywatch_url", "http://localhost:5600")
    try:
        resp = urlopen(f"{base}/api/0/buckets")
        buckets = json.loads(resp.read())
    except (URLError, Exception):
        return []

    watcher = None
    for name in buckets:
        if name.startswith("aw-watcher-afk"):
            watcher = name
            break
    if not watcher:
        return []

    try:
        query = json.dumps({
            "query": [
                f'events = query_bucket("{watcher}");',
                "RETURN = events;",
            ],
            "timeperiods": [f"{start_iso}/{end_iso}"],
        }).encode()
        req = Request(
            f"{base}/api/0/query/",
            data=query,
            headers={"Content-Type": "application/json"},
        )
        resp = urlopen(req)
        results = json.loads(resp.read())
    except (URLError, Exception):
        return []

    if results and len(results) > 0:
        return results[0]
    return []


# ── persistence ──────────────────────────────────────────────────────────────

def persist_sessions(db, sessions, range_start, range_end):
    """Write `sessions` to the `sessions` table idempotently.

    Deletes any existing session rows whose `start` falls within
    `[range_start, range_end)` before inserting. Re-running
    aggregation over the same range produces the same stored rows.
    """
    db.execute(
        "DELETE FROM sessions WHERE start >= ? AND start < ?",
        (range_start, range_end),
    )
    for s in sessions:
        db.execute(
            """
            INSERT INTO sessions (
                start, end, task, task_name_confidence, boundary_confidence,
                cycle_count, dip_count, evidence_json, kind
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                s["start"],
                s["end"],
                s.get("task"),
                s.get("task_name_confidence", "low"),
                s.get("boundary_confidence", "low"),
                int(s.get("cycle_count", 0)),
                int(s.get("dip_count", 0)),
                json.dumps(s.get("evidence", [])),
                s.get("kind", "session"),
            ),
        )
    db.commit()


# ── cycle reconstruction from activity_log rows ──────────────────────────────

def _cycle_from_activity_row(row, fallback_duration_sec):
    """Rebuild a cycle dict from one `activity_log` row.

    The validated Pass 2 dict we stashed in `raw_response` carries the
    new fields (task, evidence, confidences) and, when recent enough,
    the Pass 1 signals (`cycle_signals`, `cycle_start`, `cycle_end`).
    Older rows fall back to sensible defaults so the aggregator can
    still run over historical data without crashing.
    """
    row_id, timestamp, raw = row
    try:
        parsed = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        parsed = {}

    cycle_end = parsed.get("cycle_end") or timestamp
    cycle_start = parsed.get("cycle_start")
    if not cycle_start:
        try:
            end_dt = _to_naive(_parse_iso(cycle_end))
            cycle_start = (end_dt - timedelta(seconds=fallback_duration_sec)).isoformat()
        except (TypeError, ValueError):
            cycle_start = cycle_end

    signals = parsed.get("cycle_signals") or {}
    return {
        "id": row_id,
        "start": cycle_start,
        "end": cycle_end,
        "task": parsed.get("task"),
        "name_confidence": parsed.get("name_confidence", "low"),
        "boundary_confidence": parsed.get("boundary_confidence", "low"),
        "evidence": parsed.get("evidence", []),
        "workspaces": signals.get("workspaces", []),
        "terminal_cwds": signals.get("terminal_cwds", []),
        "browser_hosts": signals.get("browser_hosts", []),
    }


def aggregate_day(db, cfg, day_iso):
    """Re-aggregate one calendar day's activity_log rows into sessions
    and persist them. Intended to be called right after a new
    analysis cycle writes a row.

    `day_iso` is `YYYY-MM-DD`. The affected range is
    `[day_iso T00:00:00, day_iso+1 T00:00:00)`.
    """
    start_iso = f"{day_iso}T00:00:00"
    next_day = (_parse_iso(start_iso) + timedelta(days=1)).isoformat()
    end_iso = next_day

    rows = db.execute(
        "SELECT id, timestamp, raw_response FROM activity_log "
        "WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp ASC",
        (start_iso, end_iso),
    ).fetchall()
    if not rows:
        persist_sessions(db, [], start_iso, end_iso)
        return []

    fallback_duration = int(cfg.get("analysis_interval_sec", 1800))
    cycles = [_cycle_from_activity_row(r, fallback_duration) for r in rows]

    afk_events = fetch_afk_events(cfg, start_iso, end_iso)
    cycles = aw_afk_overlay(cycles, afk_events)

    dip_tolerance = int(cfg.get("session_dip_tolerance_sec", 300))
    sessions = aggregate(cycles, dip_tolerance_sec=dip_tolerance)
    persist_sessions(db, sessions, start_iso, end_iso)
    return sessions
