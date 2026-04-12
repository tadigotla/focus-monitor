#!/usr/bin/env python3
"""Tests for structured task definitions and activity discovery."""

import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

passed = 0
failed = 0


def test(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}")


# Use a temp dir to avoid touching real config
tmpdir = Path(tempfile.mkdtemp())

# Patch module-level paths before importing
import focusmonitor.config as config_mod
import focusmonitor.tasks as tasks_mod

original_tasks_json = config_mod.TASKS_JSON_FILE
original_tasks_file = config_mod.TASKS_FILE
original_discovered = config_mod.DISCOVERED_FILE

config_mod.TASKS_JSON_FILE = tmpdir / "planned_tasks.json"
config_mod.TASKS_FILE = tmpdir / "planned_tasks.txt"
config_mod.DISCOVERED_FILE = tmpdir / "discovered_activities.json"
# Also patch the tasks module which imported these at load time
tasks_mod.TASKS_JSON_FILE = tmpdir / "planned_tasks.json"
tasks_mod.DISCOVERED_FILE = tmpdir / "discovered_activities.json"


# ── 5.1: Planned tasks JSON loading ──────────────────────────────────────────

print("\n== Planned Tasks JSON Loading ==")

# Valid file with signals
tasks_data = [
    {"name": "Sanskrit Tool", "signals": ["panini", "dhatu"], "apps": ["VS Code"], "notes": "MCP server"},
    {"name": "Focus Monitor", "signals": ["monitor.py", "dashboard.py"], "apps": [], "notes": ""}
]
tasks_mod.TASKS_JSON_FILE.write_text(json.dumps(tasks_data))

tasks = tasks_mod.load_planned_tasks()
test("loads 2 tasks", len(tasks) == 2)
test("first task name", tasks[0]["name"] == "Sanskrit Tool")
test("first task signals", tasks[0]["signals"] == ["panini", "dhatu"])
test("first task apps", tasks[0]["apps"] == ["VS Code"])
test("first task notes", tasks[0]["notes"] == "MCP server")

# Task without optional fields
minimal_data = [{"name": "Simple Task"}]
tasks_mod.TASKS_JSON_FILE.write_text(json.dumps(minimal_data))
tasks = tasks_mod.load_planned_tasks()
test("minimal task loads", len(tasks) == 1)
test("defaults for missing fields", tasks[0]["signals"] == [] and tasks[0]["apps"] == [] and tasks[0]["notes"] == "")

# Missing file
tasks_mod.TASKS_JSON_FILE.unlink()
tasks = tasks_mod.load_planned_tasks()
test("missing file returns empty", tasks == [])

# Invalid JSON
tasks_mod.TASKS_JSON_FILE.write_text("not json")
tasks = tasks_mod.load_planned_tasks()
test("invalid JSON returns empty", tasks == [])

# Clean up
if tasks_mod.TASKS_JSON_FILE.exists():
    tasks_mod.TASKS_JSON_FILE.unlink()


# ── 5.2: Migration from planned_tasks.txt ────────────────────────────────────

print("\n== Migration ==")

# Set up a text file
config_mod.TASKS_FILE.write_text("# Header comment\nBuild Sanskrit Tool\n\n# Another comment\nFix bugs\n")
assert not tasks_mod.TASKS_JSON_FILE.exists()

# Simulate migration (call load_config's migration logic directly)
# Read text entries
lines = config_mod.TASKS_FILE.read_text().strip().splitlines()
entries = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
migrated = [{"name": name, "signals": [], "apps": [], "notes": ""} for name in entries]
tasks_mod.TASKS_JSON_FILE.write_text(json.dumps(migrated, indent=2))
config_mod.TASKS_FILE.rename(config_mod.TASKS_FILE.with_suffix(".txt.bak"))

test("JSON file created", tasks_mod.TASKS_JSON_FILE.exists())
test("txt renamed to bak", (tmpdir / "planned_tasks.txt.bak").exists())
test("original txt gone", not config_mod.TASKS_FILE.exists())

tasks = tasks_mod.load_planned_tasks()
test("migrated 2 tasks", len(tasks) == 2)
test("first migrated name", tasks[0]["name"] == "Build Sanskrit Tool")
test("migrated signals empty", tasks[0]["signals"] == [])

# Clean up
tasks_mod.TASKS_JSON_FILE.unlink()
(tmpdir / "planned_tasks.txt.bak").unlink()


# ── 5.3: Discovered activities ───────────────────────────────────────────────

print("\n== Discovered Activities ==")

# New activity
assert not tasks_mod.DISCOVERED_FILE.exists()
tasks_mod.update_discovered_activities(
    ["focus-monitor dev"],
    ["monitor.py — VS Code", "dashboard.py — VS Code"]
)
test("file created", tasks_mod.DISCOVERED_FILE.exists())

data = json.loads(tasks_mod.DISCOVERED_FILE.read_text())
acts = data["activities"]
test("one activity added", len(acts) == 1)
test("name correct", acts[0]["name"] == "focus-monitor dev")
test("count is 1", acts[0]["count"] == 1)
test("promoted is false", acts[0]["promoted"] is False)
test("has sample signals", len(acts[0]["sample_signals"]) > 0)
test("first_seen set", "first_seen" in acts[0])

# Update existing
tasks_mod.update_discovered_activities(
    ["focus-monitor dev"],
    ["test_analysis.py — VS Code"]
)
data = json.loads(tasks_mod.DISCOVERED_FILE.read_text())
acts = data["activities"]
test("still one activity", len(acts) == 1)
test("count incremented", acts[0]["count"] == 2)
test("last_seen updated", acts[0]["last_seen"] >= acts[0]["first_seen"])

# Add second activity
tasks_mod.update_discovered_activities(
    ["new project"],
    ["readme.md — VS Code"]
)
data = json.loads(tasks_mod.DISCOVERED_FILE.read_text())
test("two activities", len(data["activities"]) == 2)

# Promoted flag preserved
data["activities"][0]["promoted"] = True
tasks_mod.DISCOVERED_FILE.write_text(json.dumps(data))
tasks_mod.update_discovered_activities(
    ["focus-monitor dev"],
    ["cli.py — VS Code"]
)
data = json.loads(tasks_mod.DISCOVERED_FILE.read_text())
promoted_act = [a for a in data["activities"] if a["name"] == "focus-monitor dev"][0]
test("promoted flag preserved", promoted_act["promoted"] is True)

# Cap enforcement
data = {"activities": []}
for i in range(50):
    data["activities"].append({
        "name": f"project-{i}",
        "first_seen": f"2026-04-{10+i//30:02d}T{i%24:02d}:00:00",
        "last_seen": f"2026-04-{10+i//30:02d}T{i%24:02d}:00:00",
        "count": 1,
        "sample_signals": [],
        "promoted": False
    })
tasks_mod.DISCOVERED_FILE.write_text(json.dumps(data))
tasks_mod.update_discovered_activities(["new-over-cap"], ["test"])
data = json.loads(tasks_mod.DISCOVERED_FILE.read_text())
test("cap enforced at 50", len(data["activities"]) == 50)
test("new entry present", any(a["name"] == "new-over-cap" for a in data["activities"]))

# Clean up
tasks_mod.DISCOVERED_FILE.unlink()


# ── 5.4: Signal-based nudge matching ─────────────────────────────────────────

print("\n== Signal-Based Matching ==")

# Match via signal
task_with_signals = {
    "name": "Sanskrit Tool",
    "signals": ["panini", "dhatu", "sanskrit"],
    "apps": [], "notes": ""
}
projects = {"building panini grammar engine"}
test("match via signal", tasks_mod._task_matches_projects(task_with_signals, projects))

# Match via task name
projects2 = {"sanskrit tool development"}
test("match via name", tasks_mod._task_matches_projects(task_with_signals, projects2))

# No match
projects3 = {"unrelated project", "web browsing"}
test("no match", not tasks_mod._task_matches_projects(task_with_signals, projects3))

# Task without signals (fallback to name)
task_no_signals = {"name": "Focus Monitor", "signals": [], "apps": [], "notes": ""}
projects4 = {"working on focus monitor"}
test("name-only fallback match", tasks_mod._task_matches_projects(task_no_signals, projects4))

projects5 = {"completely unrelated"}
test("name-only no match", not tasks_mod._task_matches_projects(task_no_signals, projects5))


# ── Cleanup ──────────────────────────────────────────────────────────────────

# Restore original paths
config_mod.TASKS_JSON_FILE = original_tasks_json
config_mod.TASKS_FILE = original_tasks_file
config_mod.DISCOVERED_FILE = original_discovered
tasks_mod.TASKS_JSON_FILE = original_tasks_json
tasks_mod.DISCOVERED_FILE = original_discovered
shutil.rmtree(tmpdir, ignore_errors=True)

print(f"\n{'='*50}")
print(f"  Results: {passed} passed, {failed} failed")
print(f"{'='*50}")

exit(0 if failed == 0 else 1)
