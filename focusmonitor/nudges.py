"""Nudge checking and sending."""

import json
import subprocess
from datetime import datetime, timedelta
from focusmonitor.tasks import load_planned_tasks, _task_matches_projects


def check_nudges(cfg, db, analysis_result):
    """If a planned task hasn't appeared in recent analyses, nudge."""
    tasks = load_planned_tasks()
    if not tasks:
        return

    hours = cfg["nudge_after_hours"]
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

    rows = db.execute(
        "SELECT project_detected FROM activity_log WHERE timestamp > ?",
        (cutoff,)
    ).fetchall()

    recent_projects = set()
    for row in rows:
        try:
            for p in json.loads(row[0]):
                recent_projects.add(p.lower())
        except (json.JSONDecodeError, TypeError):
            pass

    for task in tasks:
        if not _task_matches_projects(task, recent_projects):
            send_nudge(cfg, db, task["name"])


def send_nudge(cfg, db, task_name):
    """Send a macOS notification reminding the user about a task."""
    msg = f"You haven't touched '{task_name}' in a while. Want to pick it back up?"

    recent = db.execute(
        "SELECT timestamp FROM nudges WHERE task = ? ORDER BY timestamp DESC LIMIT 1",
        (task_name,)
    ).fetchone()
    if recent:
        last = datetime.fromisoformat(recent[0])
        if datetime.now() - last < timedelta(hours=1):
            return

    subprocess.run([
        "osascript", "-e",
        f'display notification "{msg}" with title "Focus Monitor" sound name "Purr"'
    ], capture_output=True)

    db.execute("INSERT INTO nudges (timestamp, task, message) VALUES (?, ?, ?)",
               (datetime.now().isoformat(), task_name, msg))
    db.commit()
    print(f"  🔔 Nudge sent: {task_name}")
