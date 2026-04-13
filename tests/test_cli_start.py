"""Tests for `cli.py` foreground child supervision.

The real `_spawn` helper runs `python -m focusmonitor.main` and `python
-m scope.api`, both of which would talk to the real DB, bind loopback
ports, and take seconds to spin up. These tests drive `_supervise`
directly with trivial long-running `python -c` children so the
supervisor loop can be exercised deterministically.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time

import cli


def _sleeper(seconds: float = 15.0) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", f"import time; time.sleep({seconds})"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def _quick_exit(code: int = 0) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", f"import sys; sys.exit({code})"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def test_supervise_runs_until_shutdown(monkeypatch):
    monkeypatch.setattr(cli, "_SHUTDOWN_TIMEOUT_SEC", 2)

    children = {"pulse": _sleeper(10.0), "scope": _sleeper(10.0)}
    shutdown = threading.Event()

    result = {}

    def run():
        result["code"] = cli._supervise(children, shutdown)

    t = threading.Thread(target=run, daemon=True)
    t.start()

    # Confirm both children are alive before we signal shutdown.
    time.sleep(0.3)
    assert children["pulse"].poll() is None
    assert children["scope"].poll() is None

    shutdown.set()
    t.join(timeout=5)
    assert not t.is_alive(), "supervisor did not exit after shutdown event"
    assert result["code"] == 0

    # Both children must be reaped.
    for proc in children.values():
        assert proc.poll() is not None


def test_supervise_tears_down_survivor_on_child_crash(monkeypatch):
    monkeypatch.setattr(cli, "_SHUTDOWN_TIMEOUT_SEC", 2)

    crashing = _quick_exit(code=7)
    survivor = _sleeper(20.0)
    children = {"pulse": crashing, "scope": survivor}
    shutdown = threading.Event()

    result = {}

    def run():
        result["code"] = cli._supervise(children, shutdown)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=6)
    assert not t.is_alive(), "supervisor did not exit after child crash"

    assert result["code"] != 0, "supervisor should exit non-zero on crash"
    assert survivor.poll() is not None, "survivor was not torn down"


class _FakePopen:
    """Minimal Popen stand-in for _spawn argument-capture tests."""
    def __init__(self):
        self.stdout = None
    def poll(self):
        return 0
    def wait(self, timeout=None):
        return 0
    def terminate(self):
        pass
    def kill(self):
        pass


def test_spawn_sets_pythonunbuffered(monkeypatch):
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        captured["cwd"] = kwargs.get("cwd")
        return _FakePopen()

    monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)
    cli._spawn("pulse")

    assert captured["cmd"][0] == sys.executable
    assert "focusmonitor" in captured["cmd"]
    assert captured["env"]["PYTHONUNBUFFERED"] == "1"


def test_spawn_scope_targets_scope_api(monkeypatch):
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakePopen()

    monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)
    cli._spawn("scope")

    assert "scope.api" in captured["cmd"]
