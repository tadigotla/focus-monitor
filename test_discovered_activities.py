#!/usr/bin/env python3
"""Thorough verification that discovered_activities.json is populated per spec.

Each scenario below maps to a scenario in
openspec/specs/activity-discovery/spec.md. If any test fails, it indicates a
divergence between the code and the spec — stop and report rather than
silently patching.
"""

import json
import shutil
import tempfile
from pathlib import Path

passed = 0
failed = 0
skipped = 0


def test(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}")


def skip(name, reason):
    global skipped
    skipped += 1
    print(f"  SKIP  {name}  ({reason})")


tmpdir = Path(tempfile.mkdtemp())

import focusmonitor.config as config_mod
import focusmonitor.tasks as tasks_mod

original_discovered = config_mod.DISCOVERED_FILE
config_mod.DISCOVERED_FILE = tmpdir / "discovered_activities.json"
tasks_mod.DISCOVERED_FILE = tmpdir / "discovered_activities.json"
DF = tasks_mod.DISCOVERED_FILE


def reset_file():
    if DF.exists():
        DF.unlink()


# ── Scenario: new activity detected ──────────────────────────────────────────
print("\n== New activity detected ==")
reset_file()
# Note: `-` is itself a separator, so "project-a" would split into "project"+"a".
# Use monitor.py as the project name to mirror the spec's own example.
tasks_mod.update_discovered_activities(
    ["monitor.py"],
    ["monitor.py — VS Code"],
)
test("file created", DF.exists())
data = json.loads(DF.read_text())
acts = data["activities"]
test("one entry added", len(acts) == 1)
entry = acts[0]
test("name matches", entry["name"] == "monitor.py")
test("count is 1", entry["count"] == 1)
test("promoted is False", entry["promoted"] is False)
test("first_seen present", "first_seen" in entry)
test("last_seen equals first_seen on first write",
     entry["last_seen"] == entry["first_seen"])
test("sample_signals contains 'monitor.py'", "monitor.py" in entry["sample_signals"])
test("sample_signals contains 'VS Code'", "VS Code" in entry["sample_signals"])


# ── Scenario: known activity detected again (upsert) ─────────────────────────
print("\n== Known activity upsert ==")
reset_file()
tasks_mod.update_discovered_activities(
    ["project-b"],
    ["project-b — Chrome", "project-b — Chrome"],
)
tasks_mod.update_discovered_activities(
    ["project-b"],
    ["project-b — Terminal"],
)
data = json.loads(DF.read_text())
acts = data["activities"]
test("still one entry after upsert", len(acts) == 1)
entry = acts[0]
test("count incremented to 2", entry["count"] == 2)
test("last_seen >= first_seen", entry["last_seen"] >= entry["first_seen"])
signals = entry["sample_signals"]
test("no duplicate signals", len(signals) == len(set(signals)))
test("old signal retained", "Chrome" in signals)
test("new signal merged", "Terminal" in signals)
test("signals capped at 10", len(signals) <= 10)


# ── Scenario: first run with no file ─────────────────────────────────────────
print("\n== First run with no file ==")
reset_file()
test("precondition: file gone", not DF.exists())
tasks_mod.update_discovered_activities(["fresh-project"], ["fresh-project — VS Code"])
test("file recreated", DF.exists())
data = json.loads(DF.read_text())
test("activities key present", "activities" in data)
test("new entry present", any(a["name"] == "fresh-project" for a in data["activities"]))


# ── Scenario: sample signal extraction filters short/long parts ──────────────
print("\n== Signal extraction filter ==")
reset_file()
long_part = "x" * 80  # length 80 — must be filtered (code uses len < 80)
long_title = f"project-c — {long_part}"
tasks_mod.update_discovered_activities(
    ["project-c"],
    [
        "project-c — ab",            # "ab" too short (len 2, code uses > 2)
        "project-c | VS Code",       # "VS Code" should pass
        "project-c: Terminal",       # "Terminal" should pass
        long_title,                  # long_part should be filtered
    ],
)
data = json.loads(DF.read_text())
signals = data["activities"][0]["sample_signals"]
test("short 'ab' excluded", "ab" not in signals)
test("80-char part excluded", long_part not in signals)
test("pipe-separated 'VS Code' included", "VS Code" in signals)
test("colon-separated 'Terminal' included", "Terminal" in signals)


# ── Scenario: cap reached with non-promoted entries ──────────────────────────
print("\n== Cap eviction (non-promoted) ==")
reset_file()
seeded = {"activities": []}
for i in range(50):
    ts = f"2026-04-{1 + (i // 24):02d}T{i % 24:02d}:00:00"
    seeded["activities"].append({
        "name": f"seed-{i:02d}",
        "first_seen": ts,
        "last_seen": ts,
        "count": 1,
        "sample_signals": [],
        "promoted": False,
    })
DF.write_text(json.dumps(seeded))
# seed-00 has the oldest last_seen
tasks_mod.update_discovered_activities(["new-over-cap"], ["new-over-cap — VS Code"])
data = json.loads(DF.read_text())
names = [a["name"] for a in data["activities"]]
test("length stays at 50", len(data["activities"]) == 50)
test("new entry retained", "new-over-cap" in names)
test("oldest non-promoted evicted", "seed-00" not in names)


# ── Scenario: promoted protection at cap ─────────────────────────────────────
print("\n== Promoted protection ==")
reset_file()
seeded = {"activities": []}
for i in range(50):
    ts = f"2026-04-{1 + (i // 24):02d}T{i % 24:02d}:00:00"
    seeded["activities"].append({
        "name": f"seed-{i:02d}",
        "first_seen": ts,
        "last_seen": ts,
        "count": 1,
        "sample_signals": [],
        "promoted": (i == 0),  # oldest one is promoted
    })
DF.write_text(json.dumps(seeded))
tasks_mod.update_discovered_activities(["new-entry"], ["new-entry — VS Code"])
data = json.loads(DF.read_text())
names = [a["name"] for a in data["activities"]]
test("length stays at 50", len(data["activities"]) == 50)
test("promoted seed-00 retained", "seed-00" in names)
test("next-oldest non-promoted seed-01 evicted", "seed-01" not in names)
test("new entry retained", "new-entry" in names)


# ── Scenario: all entries promoted, cap reached ──────────────────────────────
print("\n== All promoted, cap reached ==")
reset_file()
seeded = {"activities": []}
for i in range(50):
    ts = f"2026-04-{1 + (i // 24):02d}T{i % 24:02d}:00:00"
    seeded["activities"].append({
        "name": f"seed-{i:02d}",
        "first_seen": ts,
        "last_seen": ts,
        "count": 1,
        "sample_signals": [],
        "promoted": True,
    })
DF.write_text(json.dumps(seeded))
tasks_mod.update_discovered_activities(["new-all-promoted"], ["new-all-promoted — VS Code"])
data = json.loads(DF.read_text())
names = [a["name"] for a in data["activities"]]
test("length stays at 50", len(data["activities"]) == 50)
test("oldest seed-00 evicted", "seed-00" not in names)
test("new entry retained", "new-all-promoted" in names)


# ── Scenario: promoted flag preserved across upserts ─────────────────────────
print("\n== Promoted flag preserved ==")
reset_file()
seeded = {"activities": [{
    "name": "sticky",
    "first_seen": "2026-04-01T10:00:00",
    "last_seen": "2026-04-01T10:00:00",
    "count": 1,
    "sample_signals": ["Chrome"],
    "promoted": True,
}]}
DF.write_text(json.dumps(seeded))
tasks_mod.update_discovered_activities(["sticky"], ["sticky — VS Code"])
data = json.loads(DF.read_text())
entry = [a for a in data["activities"] if a["name"] == "sticky"][0]
test("promoted stays True", entry["promoted"] is True)
test("count incremented to 2", entry["count"] == 2)
test("new signal merged in", "VS Code" in entry["sample_signals"])


# ── Cleanup ──────────────────────────────────────────────────────────────────
config_mod.DISCOVERED_FILE = original_discovered
tasks_mod.DISCOVERED_FILE = original_discovered
shutil.rmtree(tmpdir, ignore_errors=True)

print(f"\n{'='*50}")
print(f"  Results: {passed} passed, {failed} failed, {skipped} skipped")
print(f"{'='*50}")

exit(0 if failed == 0 else 1)
