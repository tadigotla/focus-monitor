"""Tests for `bin/focusmonitor-service` — the Python-resolution shim.

These tests invoke the shim with a controlled PATH so the resolution
order is deterministic. The shim re-execs into `cli.py`, which we
short-circuit by pointing REPO_ROOT at a tmp_path that contains a
trivial `cli.py` that just prints argv and exits.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SHIM = REPO_ROOT / "bin" / "focusmonitor-service"


def _make_fake_python(path: Path, marker: str) -> Path:
    """Write a shell script that masquerades as python3 and echoes a marker."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        f"echo 'FAKE-PYTHON:{marker}'\n"
        "echo \"argv:\" \"$@\"\n"
        "exit 0\n"
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _make_fake_repo(tmp_path: Path, shim_src: Path) -> Path:
    """Copy the real shim into a scratch repo layout so REPO_ROOT
    resolves to tmp_path, not the real checkout. Also plants a
    placeholder `cli.py` that the fake python will be handed."""
    scratch = tmp_path / "repo"
    (scratch / "bin").mkdir(parents=True)
    (scratch / "cli.py").write_text("# stub\n")
    shim = scratch / "bin" / "focusmonitor-service"
    shim.write_text(shim_src.read_text())
    shim.chmod(0o755)
    return scratch


def test_shim_exists_and_is_executable():
    assert SHIM.exists(), f"shim not found at {SHIM}"
    assert os.access(SHIM, os.X_OK), f"shim not executable: {SHIM}"


def test_shim_uses_posix_sh_shebang():
    first_line = SHIM.read_text().splitlines()[0]
    assert first_line == "#!/bin/sh", f"unexpected shebang: {first_line}"


def test_shim_contains_no_network_calls():
    """Privacy invariant: the shim must not reach the network."""
    text = SHIM.read_text()
    forbidden = ("curl", "wget", " nc ", "ssh ", "http://", "https://")
    for pat in forbidden:
        assert pat not in text, f"shim contains forbidden token: {pat!r}"


def test_shim_prefers_venv_python(tmp_path):
    scratch = _make_fake_repo(tmp_path, SHIM)
    venv_py = _make_fake_python(scratch / ".venv" / "bin" / "python3", "venv")

    # Path also has another python3 — venv must still win.
    other = _make_fake_python(tmp_path / "elsewhere" / "python3", "path")

    env = {
        "PATH": f"{other.parent}:/usr/bin:/bin",
        "HOME": str(tmp_path),
    }
    result = subprocess.run(
        [str(scratch / "bin" / "focusmonitor-service"), "start", "pulse"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "FAKE-PYTHON:venv" in result.stdout
    assert "argv: " in result.stdout
    assert "start pulse" in result.stdout
    # Shim logs its resolution line to stderr.
    assert "resolved python=" in result.stderr
    assert str(venv_py) in result.stderr


def test_shim_falls_back_to_path_when_no_venv(tmp_path):
    scratch = _make_fake_repo(tmp_path, SHIM)
    # No .venv → fall through to PATH.
    path_py = _make_fake_python(tmp_path / "pathbin" / "python3", "path")

    env = {
        "PATH": f"{path_py.parent}",
        "HOME": str(tmp_path),
    }
    result = subprocess.run(
        [str(scratch / "bin" / "focusmonitor-service"), "start", "scope"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "FAKE-PYTHON:path" in result.stdout
    assert str(path_py) in result.stderr


def test_shim_logs_resolution_to_stderr_only(tmp_path):
    """The `resolved python=` line must go to stderr, not stdout, so it
    does not pollute any downstream consumers of cli.py's stdout."""
    scratch = _make_fake_repo(tmp_path, SHIM)
    _make_fake_python(scratch / ".venv" / "bin" / "python3", "venv")

    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    result = subprocess.run(
        [str(scratch / "bin" / "focusmonitor-service"), "start"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert "resolved python=" not in result.stdout
    assert "resolved python=" in result.stderr
