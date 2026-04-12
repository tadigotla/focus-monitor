"""Discovery-scenario tests.

Each scenario below maps to a scenario in
`openspec/specs/activity-discovery/spec.md`. If any test fails, it indicates
a divergence between the code and the spec — stop and report rather than
silently patching.
"""

from __future__ import annotations

import json

import pytest

from focusmonitor import config, tasks


# Access DISCOVERED_FILE via `config.DISCOVERED_FILE` so the tmp_home rebind
# is visible at call time (see `tests/test_tasks.py` for the same rationale).


# ── Scenario: new activity detected ──────────────────────────────────────────

class TestNewActivity:

    def test_file_created_with_single_entry(self, tmp_home):
        tasks.update_discovered_activities(
            ["monitor.py"],
            ["monitor.py — VS Code"],
        )
        assert config.DISCOVERED_FILE.exists()
        data = json.loads(config.DISCOVERED_FILE.read_text())
        acts = data["activities"]
        assert len(acts) == 1
        entry = acts[0]
        assert entry["name"] == "monitor.py"
        assert entry["count"] == 1
        assert entry["promoted"] is False
        assert entry["last_seen"] == entry["first_seen"]
        assert "monitor.py" in entry["sample_signals"]
        assert "VS Code" in entry["sample_signals"]


# ── Scenario: known activity detected again (upsert) ────────────────────────

class TestUpsertKnownActivity:

    def test_count_increments_and_signals_merge(self, tmp_home):
        tasks.update_discovered_activities(
            ["project-b"],
            ["project-b — Chrome", "project-b — Chrome"],
        )
        tasks.update_discovered_activities(
            ["project-b"],
            ["project-b — Terminal"],
        )
        data = json.loads(config.DISCOVERED_FILE.read_text())
        acts = data["activities"]
        assert len(acts) == 1
        entry = acts[0]
        assert entry["count"] == 2
        assert entry["last_seen"] >= entry["first_seen"]
        signals = entry["sample_signals"]
        assert len(signals) == len(set(signals))
        assert "Chrome" in signals
        assert "Terminal" in signals
        assert len(signals) <= 10


# ── Scenario: first run with no file ─────────────────────────────────────────

class TestFirstRun:

    def test_file_created_fresh(self, tmp_home):
        assert not config.DISCOVERED_FILE.exists()
        tasks.update_discovered_activities(
            ["fresh-project"], ["fresh-project — VS Code"]
        )
        assert config.DISCOVERED_FILE.exists()
        data = json.loads(config.DISCOVERED_FILE.read_text())
        assert "activities" in data
        assert any(a["name"] == "fresh-project" for a in data["activities"])


# ── Scenario: signal-extraction filter ──────────────────────────────────────

class TestSignalExtractionFilter:

    def test_too_short_and_too_long_excluded(self, tmp_home):
        long_part = "x" * 80  # code uses `len < 80`, so 80 is filtered
        tasks.update_discovered_activities(
            ["project-c"],
            [
                "project-c — ab",            # "ab" too short (len 2, code uses > 2)
                "project-c | VS Code",       # "VS Code" passes
                "project-c: Terminal",       # "Terminal" passes
                f"project-c — {long_part}",  # long_part filtered
            ],
        )
        data = json.loads(config.DISCOVERED_FILE.read_text())
        signals = data["activities"][0]["sample_signals"]
        assert "ab" not in signals
        assert long_part not in signals
        assert "VS Code" in signals
        assert "Terminal" in signals


# ── Scenario: cap enforcement (non-promoted) ─────────────────────────────────

def _seed_activities(n, *, promoted=False, promoted_index=None):
    acts = []
    for i in range(n):
        ts = f"2026-04-{1 + (i // 24):02d}T{i % 24:02d}:00:00"
        acts.append({
            "name": f"seed-{i:02d}",
            "first_seen": ts,
            "last_seen": ts,
            "count": 1,
            "sample_signals": [],
            "promoted": (
                promoted if promoted_index is None
                else (i == promoted_index)
            ),
        })
    return {"activities": acts}


class TestCapEviction:

    def test_non_promoted_oldest_evicted_at_cap(self, tmp_home):
        config.DISCOVERED_FILE.write_text(json.dumps(_seed_activities(50)))
        tasks.update_discovered_activities(
            ["new-over-cap"], ["new-over-cap — VS Code"]
        )
        data = json.loads(config.DISCOVERED_FILE.read_text())
        names = [a["name"] for a in data["activities"]]
        assert len(data["activities"]) == 50
        assert "new-over-cap" in names
        assert "seed-00" not in names

    def test_promoted_protected_at_cap(self, tmp_home):
        config.DISCOVERED_FILE.write_text(
            json.dumps(_seed_activities(50, promoted_index=0))
        )
        tasks.update_discovered_activities(
            ["new-entry"], ["new-entry — VS Code"]
        )
        data = json.loads(config.DISCOVERED_FILE.read_text())
        names = [a["name"] for a in data["activities"]]
        assert len(data["activities"]) == 50
        assert "seed-00" in names      # promoted — protected
        assert "seed-01" not in names  # next-oldest non-promoted — evicted
        assert "new-entry" in names

    def test_all_promoted_still_evicts_oldest(self, tmp_home):
        config.DISCOVERED_FILE.write_text(
            json.dumps(_seed_activities(50, promoted=True))
        )
        tasks.update_discovered_activities(
            ["new-all-promoted"], ["new-all-promoted — VS Code"]
        )
        data = json.loads(config.DISCOVERED_FILE.read_text())
        names = [a["name"] for a in data["activities"]]
        assert len(data["activities"]) == 50
        assert "seed-00" not in names
        assert "new-all-promoted" in names


# ── Scenario: promoted flag preserved across upserts ─────────────────────────

class TestPromotedFlagPreservation:

    def test_flag_survives_upsert(self, tmp_home):
        seeded = {"activities": [{
            "name": "sticky",
            "first_seen": "2026-04-01T10:00:00",
            "last_seen": "2026-04-01T10:00:00",
            "count": 1,
            "sample_signals": ["Chrome"],
            "promoted": True,
        }]}
        config.DISCOVERED_FILE.write_text(json.dumps(seeded))
        tasks.update_discovered_activities(["sticky"], ["sticky — VS Code"])
        data = json.loads(config.DISCOVERED_FILE.read_text())
        entry = [a for a in data["activities"] if a["name"] == "sticky"][0]
        assert entry["promoted"] is True
        assert entry["count"] == 2
        assert "VS Code" in entry["sample_signals"]


# ── Scenario: planned-task filtering ─────────────────────────────────────────
# openspec change: filter-planned-tasks-from-discoveries

class TestPlannedTaskFiltering:

    PLAN = [{"name": "Focus Monitor", "signals": [], "apps": [], "notes": ""}]

    def test_exact_name_match_dropped_other_kept(self, tmp_home):
        tasks.update_discovered_activities(
            ["Focus Monitor", "Sanskrit Tool"],
            ["Focus Monitor — VS Code"],
            planned_tasks=self.PLAN,
        )
        data = json.loads(config.DISCOVERED_FILE.read_text())
        names = [a["name"] for a in data["activities"]]
        assert "Focus Monitor" not in names
        assert "Sanskrit Tool" in names

    def test_case_insensitive_match_dropped(self, tmp_home):
        tasks.update_discovered_activities(
            ["focus monitor"],
            ["focus monitor"],
            planned_tasks=self.PLAN,
        )
        assert not config.DISCOVERED_FILE.exists()

    def test_substring_is_not_a_match(self, tmp_home):
        tasks.update_discovered_activities(
            ["Sanskrit Tooling Dashboard"],
            ["Sanskrit Tooling Dashboard"],
            planned_tasks=[{"name": "Sanskrit", "signals": [], "apps": [], "notes": ""}],
        )
        data = json.loads(config.DISCOVERED_FILE.read_text())
        assert any(
            a["name"] == "Sanskrit Tooling Dashboard" for a in data["activities"]
        )

    def test_none_planned_tasks_disables_filtering(self, tmp_home):
        tasks.update_discovered_activities(
            ["Focus Monitor"], ["Focus Monitor"]
        )
        data = json.loads(config.DISCOVERED_FILE.read_text())
        assert any(a["name"] == "Focus Monitor" for a in data["activities"])

    def test_empty_planned_tasks_disables_filtering(self, tmp_home):
        tasks.update_discovered_activities(
            ["Focus Monitor"], ["Focus Monitor"], planned_tasks=[]
        )
        data = json.loads(config.DISCOVERED_FILE.read_text())
        assert any(a["name"] == "Focus Monitor" for a in data["activities"])

    def test_all_projects_match_plan_is_noop(self, tmp_home):
        seeded = {"activities": [{
            "name": "preexisting",
            "first_seen": "2026-04-01T10:00:00",
            "last_seen": "2026-04-01T10:00:00",
            "count": 1,
            "sample_signals": ["Chrome"],
            "promoted": False,
        }]}
        config.DISCOVERED_FILE.write_text(json.dumps(seeded))
        before = config.DISCOVERED_FILE.read_text()
        tasks.update_discovered_activities(
            ["Focus Monitor"], ["Focus Monitor"], planned_tasks=self.PLAN
        )
        after = config.DISCOVERED_FILE.read_text()
        assert before == after

    def test_upsert_with_filter_increments_non_matching(self, tmp_home):
        config.DISCOVERED_FILE.write_text(json.dumps({"activities": [{
            "name": "Sanskrit Tool",
            "first_seen": "2026-04-01T10:00:00",
            "last_seen": "2026-04-01T10:00:00",
            "count": 3,
            "sample_signals": ["Chrome"],
            "promoted": False,
        }]}))
        tasks.update_discovered_activities(
            ["Focus Monitor", "Sanskrit Tool"],
            ["Sanskrit Tool — VS Code"],
            planned_tasks=self.PLAN,
        )
        data = json.loads(config.DISCOVERED_FILE.read_text())
        entry = [a for a in data["activities"] if a["name"] == "Sanskrit Tool"][0]
        assert entry["count"] == 4
        assert "VS Code" in entry["sample_signals"]
        assert not any(a["name"] == "Focus Monitor" for a in data["activities"])
