"""Planned task loading, discovered activities, and signal matching."""

import json
import os
import re
from datetime import datetime
from focusmonitor.config import TASKS_JSON_FILE, DISCOVERED_FILE

MAX_DISCOVERED = 50


def _write_json_atomic(path, data):
    """Write JSON to `path` via a temp-file + os.replace so a crash mid-write
    cannot corrupt the original file. Removes the tmp file on error.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, path)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


def load_planned_tasks():
    """Load planned tasks from JSON file. Returns list of task dicts."""
    if not TASKS_JSON_FILE.exists():
        return []
    try:
        data = json.loads(TASKS_JSON_FILE.read_text())
        if not isinstance(data, list):
            return []
        tasks = []
        for entry in data:
            if not isinstance(entry, dict) or "name" not in entry:
                continue
            tasks.append({
                "name": entry["name"],
                "signals": entry.get("signals", []),
                "apps": entry.get("apps", []),
                "notes": entry.get("notes", ""),
            })
        return tasks
    except (json.JSONDecodeError, OSError):
        return []


def update_discovered_activities(projects, top_titles, planned_tasks=None):
    """Upsert detected projects into discovered_activities.json.

    Drops any project whose name case-insensitively matches a planned task.
    `activity_log.project_detected` is NOT filtered — that column keeps the
    raw LLM output for forensic purposes. See openspec change
    `filter-planned-tasks-from-discoveries` for rationale.
    """
    if not projects:
        return

    blocked = {t["name"].lower() for t in (planned_tasks or []) if t.get("name")}
    projects = [p for p in projects if p and p.lower() not in blocked]
    if not projects:
        return

    if DISCOVERED_FILE.exists():
        try:
            data = json.loads(DISCOVERED_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            data = {"activities": []}
    else:
        data = {"activities": []}

    activities = data.get("activities", [])
    now = datetime.now().isoformat()

    current_signals = set()
    for title in top_titles[:10]:
        for part in re.split(r'\s*[—–\-|:]\s*', title):
            part = part.strip()
            if part and len(part) > 2 and len(part) < 80:
                current_signals.add(part)

    for project_name in projects:
        if not project_name:
            continue
        existing = None
        for act in activities:
            if act.get("name", "").lower() == project_name.lower():
                existing = act
                break

        if existing:
            existing["last_seen"] = now
            existing["count"] = existing.get("count", 0) + 1
            old_signals = set(existing.get("sample_signals", []))
            merged = old_signals | current_signals
            existing["sample_signals"] = list(merged)[:10]
        else:
            # Make room before appending so the new entry is never a candidate
            # for immediate eviction (matters when all existing entries are
            # promoted — see openspec activity-discovery "All entries promoted").
            _evict_over(activities, MAX_DISCOVERED - 1)
            activities.append({
                "name": project_name,
                "first_seen": now,
                "last_seen": now,
                "count": 1,
                "sample_signals": list(current_signals)[:10],
                "promoted": False,
            })

    data["activities"] = activities
    _write_json_atomic(DISCOVERED_FILE, data)


def _evict_over(activities, limit):
    """Shrink activities in-place to `limit` entries, preferring non-promoted."""
    while len(activities) > limit:
        non_promoted = [a for a in activities if not a.get("promoted")]
        if non_promoted:
            oldest = min(non_promoted, key=lambda a: a.get("last_seen", ""))
        else:
            oldest = min(activities, key=lambda a: a.get("last_seen", ""))
        activities.remove(oldest)


def _task_matches_projects(task, recent_projects):
    """Check if a task (dict) matches any recent project names via name or signals."""
    name_lower = task["name"].lower()
    if any(name_lower in p for p in recent_projects):
        return True
    for signal in task.get("signals", []):
        signal_lower = signal.lower()
        if any(signal_lower in p for p in recent_projects):
            return True
    return False


# ═════════════════════════════════════════════════════════════════════════════
#  Mutation helpers for planned_tasks.json
#  Used by dashboard write endpoints. Every helper is atomic via
#  _write_json_atomic. Name matching is case-insensitive.
# ═════════════════════════════════════════════════════════════════════════════

def _read_planned_raw():
    """Return the raw list from planned_tasks.json, or [] on any error.

    Unlike load_planned_tasks(), this preserves the on-disk shape (including
    `apps`) so mutation round-trips don't drop fields.
    """
    if not TASKS_JSON_FILE.exists():
        return []
    try:
        data = json.loads(TASKS_JSON_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _find_task_index(tasks, name):
    """Case-insensitive index lookup. Returns -1 if not found."""
    target = (name or "").strip().lower()
    for i, t in enumerate(tasks):
        if isinstance(t, dict) and t.get("name", "").strip().lower() == target:
            return i
    return -1


def add_planned_task(name, signals=None, notes=""):
    """Append a new planned task. Returns True on success, False on duplicate."""
    name = (name or "").strip()
    if not name:
        return False
    tasks = _read_planned_raw()
    if _find_task_index(tasks, name) >= 0:
        return False
    tasks.append({
        "name": name,
        "signals": list(signals or []),
        "apps": [],
        "notes": notes or "",
    })
    _write_json_atomic(TASKS_JSON_FILE, tasks)
    return True


def update_planned_task(name, signals=None, notes=None):
    """Update an existing task's signals and/or notes. None means leave unchanged."""
    tasks = _read_planned_raw()
    idx = _find_task_index(tasks, name)
    if idx < 0:
        return False
    entry = tasks[idx]
    if signals is not None:
        entry["signals"] = list(signals)
    if notes is not None:
        entry["notes"] = notes
    _write_json_atomic(TASKS_JSON_FILE, tasks)
    return True


def delete_planned_task(name):
    """Remove the task with the given name (case-insensitive)."""
    tasks = _read_planned_raw()
    idx = _find_task_index(tasks, name)
    if idx < 0:
        return False
    tasks.pop(idx)
    _write_json_atomic(TASKS_JSON_FILE, tasks)
    return True


# ═════════════════════════════════════════════════════════════════════════════
#  Mutation helpers for discovered_activities.json
# ═════════════════════════════════════════════════════════════════════════════

def _read_discovered_raw():
    """Return the raw dict from discovered_activities.json, or a fresh shell."""
    if not DISCOVERED_FILE.exists():
        return {"activities": []}
    try:
        data = json.loads(DISCOVERED_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"activities": []}
    if not isinstance(data, dict):
        return {"activities": []}
    if not isinstance(data.get("activities"), list):
        data["activities"] = []
    return data


def _find_activity(activities, name):
    """Case-insensitive match. Returns the dict or None."""
    target = (name or "").strip().lower()
    for a in activities:
        if isinstance(a, dict) and a.get("name", "").strip().lower() == target:
            return a
    return None


def hide_discovered(name):
    """Set hidden=True on the named discovery. Returns False if not found."""
    data = _read_discovered_raw()
    entry = _find_activity(data["activities"], name)
    if entry is None:
        return False
    entry["hidden"] = True
    _write_json_atomic(DISCOVERED_FILE, data)
    return True


def promote_discovered(name):
    """Create a planned task from a discovered entry and mark it promoted.

    Returns False if the discovered entry is missing, OR if a planned task
    with the same name already exists (idempotent guard). On success both
    files are updated atomically (two separate atomic writes, one per file).
    """
    disc = _read_discovered_raw()
    entry = _find_activity(disc["activities"], name)
    if entry is None:
        return False

    canonical_name = entry.get("name", "").strip()
    if not canonical_name:
        return False

    # Reject if a planned task with this name already exists — idempotent.
    tasks = _read_planned_raw()
    if _find_task_index(tasks, canonical_name) >= 0:
        return False

    sample_signals = list(entry.get("sample_signals") or [])
    tasks.append({
        "name": canonical_name,
        "signals": sample_signals,
        "apps": [],
        "notes": "",
    })
    _write_json_atomic(TASKS_JSON_FILE, tasks)

    entry["promoted"] = True
    _write_json_atomic(DISCOVERED_FILE, disc)
    return True
