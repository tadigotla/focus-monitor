"""Planned task loading, discovered activities, and signal matching."""

import json
import re
from datetime import datetime
from focusmonitor.config import TASKS_JSON_FILE, DISCOVERED_FILE

MAX_DISCOVERED = 50


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
    DISCOVERED_FILE.write_text(json.dumps(data, indent=2))


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
