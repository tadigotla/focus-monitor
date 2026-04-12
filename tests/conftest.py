"""Global pytest configuration for focus-monitor.

Three responsibilities:

1. Redirect every `focusmonitor.config` path (and every module-level
   re-import of those paths) into a per-test `tmp_path`, so no test ever
   reads from or writes to the developer's real `~/.focus-monitor/`.
2. Provide a deterministic clock fixture via freezegun for tests that
   depend on `datetime.now()`.
3. Assert at session start that `pytest-socket` is active, so an
   accidental `--disable-socket` removal shows up as a loud failure
   instead of a silent policy regression.

Fixture modules are pulled in via `pytest_plugins` so individual test
files don't need to import them.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest


pytest_plugins = [
    "tests.fixtures.db",
    "tests.fixtures.ollama",
    "tests.fixtures.activitywatch",
]


# ── session guard: pytest-socket must be engaged ─────────────────────────────

def pytest_configure(config):
    """Fail loudly if pytest-socket is not engaged.

    We rely on `addopts = ["--disable-socket", ...]` in pyproject.toml. If
    someone removes that flag, or pytest-socket is missing from the venv,
    we want the next test run to fail before executing anything — not to
    silently regain network access.

    pytest-socket registers a `--disable-socket` option on the config
    object only when the plugin is loaded AND the flag is active, so
    `getoption` with a default is the robust check.
    """
    try:
        disabled = config.getoption("--disable-socket", default=False)
    except ValueError:
        disabled = False
    if not disabled:
        raise pytest.UsageError(
            "pytest-socket is not active. The offline-at-runtime invariant "
            "requires --disable-socket. Install requirements-dev.txt and "
            "ensure --disable-socket is in pyproject.toml addopts."
        )


# ── tmp_home: isolate ~/.focus-monitor/ per test ─────────────────────────────

# Every attribute in focusmonitor.config that points at a path under
# CONFIG_DIR must be rewritten to live under tmp_path. Any module that
# did `from focusmonitor.config import FOO` captured its own binding
# at import time — we have to rewrite those too.
_CONFIG_PATH_NAMES = (
    "CONFIG_DIR",
    "DB_PATH",
    "SCREENSHOT_DIR",
    "TASKS_FILE",
    "TASKS_JSON_FILE",
    "DISCOVERED_FILE",
    "CONFIG_FILE",
    "LOG_DIR",
)

# (module_dotted_path, attribute_name) pairs for every re-import we know
# about. Keep this list in sync with:
#   rg "from focusmonitor.config import" focusmonitor
_REBIND_TARGETS = (
    ("focusmonitor.config", "CONFIG_DIR"),
    ("focusmonitor.config", "DB_PATH"),
    ("focusmonitor.config", "SCREENSHOT_DIR"),
    ("focusmonitor.config", "TASKS_FILE"),
    ("focusmonitor.config", "TASKS_JSON_FILE"),
    ("focusmonitor.config", "DISCOVERED_FILE"),
    ("focusmonitor.config", "CONFIG_FILE"),
    ("focusmonitor.config", "LOG_DIR"),
    ("focusmonitor.screenshots", "SCREENSHOT_DIR"),
    ("focusmonitor.cleanup", "LOG_DIR"),
    ("focusmonitor.db", "DB_PATH"),
    ("focusmonitor.dashboard", "DB_PATH"),
    ("focusmonitor.dashboard", "DISCOVERED_FILE"),
    ("focusmonitor.main", "TASKS_JSON_FILE"),
    ("focusmonitor.main", "DISCOVERED_FILE"),
    ("focusmonitor.tasks", "TASKS_JSON_FILE"),
    ("focusmonitor.tasks", "DISCOVERED_FILE"),
)


@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    """Redirect every CONFIG_DIR-derived path into a per-test tmp_path.

    After this fixture runs:
      - focusmonitor.config.DB_PATH (etc.) all live under tmp_path
      - every module that imported those names by value has been rebound
      - sub-directories (screenshots, logs) exist and are writable

    Tests that need a DB or discovered-activities file can just use the
    normal APIs without manually patching anything.
    """
    import importlib

    config_mod = importlib.import_module("focusmonitor.config")

    home = tmp_path / ".focus-monitor"
    home.mkdir(parents=True, exist_ok=True)

    new_values = {
        "CONFIG_DIR": home,
        "DB_PATH": home / "activity.db",
        "SCREENSHOT_DIR": home / "screenshots",
        "TASKS_FILE": home / "planned_tasks.txt",
        "TASKS_JSON_FILE": home / "planned_tasks.json",
        "DISCOVERED_FILE": home / "discovered_activities.json",
        "CONFIG_FILE": home / "config.json",
        "LOG_DIR": home / "logs",
    }

    # Create directories that consumer code expects to already exist.
    new_values["SCREENSHOT_DIR"].mkdir(parents=True, exist_ok=True)
    new_values["LOG_DIR"].mkdir(parents=True, exist_ok=True)

    # 1. Patch focusmonitor.config itself.
    for name, value in new_values.items():
        monkeypatch.setattr(config_mod, name, value, raising=True)

    # 2. Rebind every captured import. importlib guarantees the target
    # module has already been loaded if any test imported it; if it
    # hasn't, monkeypatch.setattr will trigger the import via getattr.
    for module_path, attr in _REBIND_TARGETS:
        if module_path == "focusmonitor.config":
            continue  # handled above
        mod = importlib.import_module(module_path)
        if hasattr(mod, attr):
            monkeypatch.setattr(mod, attr, new_values[attr], raising=True)

    yield home


# ── freeze_clock: deterministic time for snapshot tests ──────────────────────

FROZEN_TIMESTAMP = "2026-04-12T15:00:00"


@pytest.fixture
def freeze_clock():
    """Pin `datetime.now()` to a fixed timestamp for the duration of a test.

    Opt-in: tests that need real time simply don't request this fixture.
    Used primarily by dashboard snapshot tests so the rendered HTML is
    byte-stable across runs.
    """
    from freezegun import freeze_time

    with freeze_time(FROZEN_TIMESTAMP) as frozen:
        yield frozen


# ── smoke test helper: socket blocking is engaged ────────────────────────────

@pytest.fixture
def assert_socket_blocked():
    """Sanity helper: confirm pytest-socket blocks non-loopback connects.

    Tests that want to be defensive about the offline invariant can use
    this; day-to-day tests rely on the session-level guard in
    `pytest_configure` instead.
    """
    def _probe():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.1)
            s.connect(("203.0.113.1", 80))  # TEST-NET-3, never routable
            s.close()
            return False
        except Exception:
            return True

    return _probe
