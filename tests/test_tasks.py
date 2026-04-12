"""Tests for `focusmonitor.tasks` — planned task CRUD, discovery helpers,
signal-based matching. Discovery scenarios that map to
`openspec/specs/activity-discovery/spec.md` live in
`tests/test_discovered_activities.py` instead; this file covers the
simpler surface.
"""

from __future__ import annotations

import json

import pytest

from focusmonitor import config, tasks


# NOTE: Do NOT import paths as `from focusmonitor.config import X` at module
# level — the binding captures the production value before tmp_home runs.
# Access paths via `config.X` so every read sees the monkeypatched value.


# ── load_planned_tasks ───────────────────────────────────────────────────────

class TestLoadPlannedTasks:

    def test_loads_full_tasks(self, tmp_home):
        data = [
            {
                "name": "Sanskrit Tool",
                "signals": ["panini", "dhatu"],
                "apps": ["VS Code"],
                "notes": "MCP server",
            },
            {
                "name": "Focus Monitor",
                "signals": ["monitor.py", "dashboard.py"],
                "apps": [],
                "notes": "",
            },
        ]
        config.TASKS_JSON_FILE.write_text(json.dumps(data))
        loaded = tasks.load_planned_tasks()
        assert len(loaded) == 2
        assert loaded[0]["name"] == "Sanskrit Tool"
        assert loaded[0]["signals"] == ["panini", "dhatu"]
        assert loaded[0]["apps"] == ["VS Code"]
        assert loaded[0]["notes"] == "MCP server"

    def test_minimal_task_gets_defaults(self, tmp_home):
        config.TASKS_JSON_FILE.write_text(json.dumps([{"name": "Simple"}]))
        loaded = tasks.load_planned_tasks()
        assert len(loaded) == 1
        assert loaded[0]["signals"] == []
        assert loaded[0]["apps"] == []
        assert loaded[0]["notes"] == ""

    def test_missing_file_returns_empty(self, tmp_home):
        assert tasks.load_planned_tasks() == []

    def test_invalid_json_returns_empty(self, tmp_home):
        config.TASKS_JSON_FILE.write_text("not json")
        assert tasks.load_planned_tasks() == []


# ── add/update/delete_planned_task ───────────────────────────────────────────

class TestPlannedTaskCrud:

    def test_add_creates_new_task(self, tmp_home):
        assert tasks.add_planned_task("Foo", signals=["a", "b"], notes="hello") is True
        raw = json.loads(config.TASKS_JSON_FILE.read_text())
        assert len(raw) == 1
        assert raw[0]["name"] == "Foo"
        assert raw[0]["signals"] == ["a", "b"]
        assert raw[0]["notes"] == "hello"
        assert raw[0]["apps"] == []

    def test_duplicate_name_rejected(self, tmp_home):
        tasks.add_planned_task("Foo")
        assert tasks.add_planned_task("Foo") is False

    def test_duplicate_case_insensitive_rejected(self, tmp_home):
        tasks.add_planned_task("Foo")
        assert tasks.add_planned_task("foo") is False

    def test_update_changes_signals_but_preserves_notes(self, tmp_home):
        tasks.add_planned_task("Foo", signals=["a"], notes="original")
        assert tasks.update_planned_task("Foo", signals=["x"]) is True
        raw = json.loads(config.TASKS_JSON_FILE.read_text())
        assert raw[0]["signals"] == ["x"]
        assert raw[0]["notes"] == "original"

    def test_update_unknown_rejected(self, tmp_home):
        assert tasks.update_planned_task("Nothing") is False

    def test_update_case_insensitive(self, tmp_home):
        tasks.add_planned_task("Foo")
        assert tasks.update_planned_task("foo", notes="world") is True
        raw = json.loads(config.TASKS_JSON_FILE.read_text())
        assert raw[0]["notes"] == "world"

    def test_delete_existing_task(self, tmp_home):
        tasks.add_planned_task("Foo")
        assert tasks.delete_planned_task("Foo") is True
        assert json.loads(config.TASKS_JSON_FILE.read_text()) == []

    def test_delete_unknown_rejected(self, tmp_home):
        assert tasks.delete_planned_task("Nothing") is False


# ── Signal-based matching ────────────────────────────────────────────────────

class TestTaskMatchesProjects:

    def test_match_via_signal(self):
        task = {
            "name": "Sanskrit Tool",
            "signals": ["panini", "dhatu", "sanskrit"],
            "apps": [],
            "notes": "",
        }
        assert tasks._task_matches_projects(task, {"building panini grammar engine"})

    def test_match_via_task_name(self):
        task = {
            "name": "Sanskrit Tool",
            "signals": ["panini"],
            "apps": [],
            "notes": "",
        }
        assert tasks._task_matches_projects(task, {"sanskrit tool development"})

    def test_no_match(self):
        task = {
            "name": "Sanskrit Tool",
            "signals": ["panini", "dhatu"],
            "apps": [],
            "notes": "",
        }
        assert not tasks._task_matches_projects(task, {"unrelated project", "web"})

    def test_name_only_fallback_matches(self):
        task = {"name": "Focus Monitor", "signals": [], "apps": [], "notes": ""}
        assert tasks._task_matches_projects(task, {"working on focus monitor"})

    def test_name_only_no_match(self):
        task = {"name": "Focus Monitor", "signals": [], "apps": [], "notes": ""}
        assert not tasks._task_matches_projects(task, {"completely unrelated"})


# ── Migration from planned_tasks.txt ─────────────────────────────────────────

class TestMigrationFromTxt:
    """The code currently migrates in-place during `load_config`. We exercise
    the migration logic directly to avoid coupling to `load_config`'s side
    effects (which write a config.json, print, etc)."""

    def test_txt_migration_preserves_names(self, tmp_home):
        config.TASKS_FILE.write_text(
            "# Header\nBuild Sanskrit Tool\n\n# Another comment\nFix bugs\n"
        )
        assert not config.TASKS_JSON_FILE.exists()

        lines = config.TASKS_FILE.read_text().strip().splitlines()
        entries = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
        migrated = [
            {"name": name, "signals": [], "apps": [], "notes": ""}
            for name in entries
        ]
        config.TASKS_JSON_FILE.write_text(json.dumps(migrated, indent=2))
        config.TASKS_FILE.rename(config.TASKS_FILE.with_suffix(".txt.bak"))

        assert config.TASKS_JSON_FILE.exists()
        assert (config.TASKS_FILE.with_suffix(".txt.bak")).exists()
        assert not config.TASKS_FILE.exists()

        loaded = tasks.load_planned_tasks()
        assert len(loaded) == 2
        assert loaded[0]["name"] == "Build Sanskrit Tool"
        assert loaded[0]["signals"] == []
