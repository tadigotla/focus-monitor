"""Tests for `focusmonitor.service` and `cli.py service install`.

Covers:
- Deterministic plist generation (no hardcoded python path, shim path
  present, loopback-only bindings, both labels written).
- Legacy `com.focusmonitor.agent` plist detection and the upgrade
  warning.
- `service install` writes both plists into a redirected agents dir.
"""

from __future__ import annotations

import io
import plistlib
import sys
from pathlib import Path

import pytest

import cli
from focusmonitor import service


# ── Plist generation ─────────────────────────────────────────────────────


def test_build_plist_pulse_is_deterministic(tmp_path):
    shim = tmp_path / "bin" / "focusmonitor-service"
    shim.parent.mkdir()
    shim.touch()
    logs = tmp_path / "logs"
    logs.mkdir()

    a = service.build_plist(service.PULSE_LABEL, "pulse", shim, logs)
    b = service.build_plist(service.PULSE_LABEL, "pulse", shim, logs)
    assert a == b, "plist bytes must be deterministic"


def test_build_plist_targets_shim_not_python(tmp_path):
    shim = tmp_path / "bin" / "focusmonitor-service"
    shim.parent.mkdir()
    shim.touch()
    logs = tmp_path / "logs"
    logs.mkdir()

    raw = service.build_plist(service.PULSE_LABEL, "pulse", shim, logs)
    data = plistlib.loads(raw)

    assert data["Label"] == service.PULSE_LABEL
    assert data["ProgramArguments"][0] == str(shim)
    assert data["ProgramArguments"][1:] == ["start", "pulse"]
    assert data["RunAtLoad"] is True
    assert data["KeepAlive"] is True
    assert data["StandardOutPath"].endswith("pulse.out.log")
    assert data["StandardErrorPath"].endswith("pulse.err.log")

    # The plist must NOT contain a literal python interpreter path. The
    # shim's whole purpose is to re-resolve python on every invocation.
    text = raw.decode()
    assert "/python3" not in text
    assert "/bin/python" not in text


def test_build_plist_scope(tmp_path):
    shim = tmp_path / "bin" / "focusmonitor-service"
    shim.parent.mkdir()
    shim.touch()
    logs = tmp_path / "logs"
    logs.mkdir()

    raw = service.build_plist(service.SCOPE_LABEL, "scope", shim, logs)
    data = plistlib.loads(raw)

    assert data["Label"] == service.SCOPE_LABEL
    assert data["ProgramArguments"] == [str(shim), "start", "scope"]
    assert data["StandardOutPath"].endswith("scope.out.log")


def test_build_plist_has_no_non_loopback_bindings(tmp_path):
    """The plist must not contain environment variables or arguments
    that would redirect a component to a non-loopback interface.

    The plistlib-generated header includes the Apple DTD identifier
    `http://www.apple.com/DTDs/PropertyList-1.0.dtd`; that's an XML
    DOCTYPE reference, not a runtime network call, so we strip it
    before the http/https audit.
    """
    shim = tmp_path / "bin" / "focusmonitor-service"
    shim.parent.mkdir()
    shim.touch()
    logs = tmp_path / "logs"
    logs.mkdir()

    for label, comp in ((service.PULSE_LABEL, "pulse"),
                        (service.SCOPE_LABEL, "scope")):
        raw = service.build_plist(label, comp, shim, logs)
        text = raw.decode()
        # Strip the DOCTYPE line before the scheme audit.
        body = "\n".join(
            line for line in text.splitlines() if "DOCTYPE plist" not in line
        )
        assert "0.0.0.0" not in body
        assert "http://" not in body
        assert "https://" not in body


def test_build_plist_rejects_unknown_component(tmp_path):
    shim = tmp_path / "bin" / "focusmonitor-service"
    shim.parent.mkdir()
    shim.touch()
    with pytest.raises(ValueError, match="unknown component"):
        service.build_plist("com.focusmonitor.bogus", "bogus", shim, tmp_path)


# ── write_plists ─────────────────────────────────────────────────────────


def test_write_plists_creates_both(tmp_path):
    agents = tmp_path / "LaunchAgents"
    logs = tmp_path / "logs"
    shim = tmp_path / "bin" / "focusmonitor-service"
    shim.parent.mkdir()
    shim.touch()

    written = service.write_plists(agents_dir=agents, log_dir=logs, shim=shim)

    assert len(written) == 2
    assert (agents / "com.focusmonitor.pulse.plist").exists()
    assert (agents / "com.focusmonitor.scope.plist").exists()

    pulse = plistlib.loads((agents / "com.focusmonitor.pulse.plist").read_bytes())
    scope = plistlib.loads((agents / "com.focusmonitor.scope.plist").read_bytes())
    assert pulse["Label"] == service.PULSE_LABEL
    assert scope["Label"] == service.SCOPE_LABEL


def test_write_plists_overwrites_existing(tmp_path):
    agents = tmp_path / "LaunchAgents"
    logs = tmp_path / "logs"
    shim = tmp_path / "bin" / "focusmonitor-service"
    shim.parent.mkdir()
    shim.touch()

    service.write_plists(agents_dir=agents, log_dir=logs, shim=shim)
    first_pulse = (agents / "com.focusmonitor.pulse.plist").read_bytes()

    # Move the shim to a new path and re-run; plist contents must update.
    new_shim = tmp_path / "elsewhere" / "focusmonitor-service"
    new_shim.parent.mkdir()
    new_shim.touch()

    service.write_plists(agents_dir=agents, log_dir=logs, shim=new_shim)
    second_pulse = (agents / "com.focusmonitor.pulse.plist").read_bytes()

    assert first_pulse != second_pulse
    assert str(new_shim).encode() in second_pulse


# ── legacy plist detection ───────────────────────────────────────────────


def test_legacy_plist_warning_none_when_missing(tmp_path):
    assert service.legacy_plist_warning(agents_dir=tmp_path) is None


def test_legacy_plist_warning_present(tmp_path):
    legacy = tmp_path / "com.focusmonitor.agent.plist"
    legacy.write_text("<plist/>")
    warning = service.legacy_plist_warning(agents_dir=tmp_path)
    assert warning is not None
    assert "com.focusmonitor.agent" in warning
    assert "launchctl" in warning
    assert "rm " in warning
    assert str(legacy) in warning


# ── cli service install integration ──────────────────────────────────────


def test_cli_service_install_writes_plists(tmp_path, monkeypatch, capsys):
    agents = tmp_path / "LaunchAgents"
    logs = tmp_path / "logs"
    shim = tmp_path / "bin" / "focusmonitor-service"
    shim.parent.mkdir()
    shim.touch()

    monkeypatch.setattr(service, "LAUNCH_AGENTS_DIR", agents)
    monkeypatch.setattr(service, "LOG_DIR", logs, raising=False)
    # write_plists defaults its args at call-time from module globals,
    # so patching the module globals is enough.
    import focusmonitor.config as cfg
    monkeypatch.setattr(cfg, "LOG_DIR", logs)

    # Point the shim resolver at our fixture shim.
    monkeypatch.setattr(service, "shim_path", lambda: shim)

    args = type("A", (), {})()
    cli.cmd_service_install(args)

    assert (agents / "com.focusmonitor.pulse.plist").exists()
    assert (agents / "com.focusmonitor.scope.plist").exists()

    out = capsys.readouterr()
    assert "wrote" in out.out


def test_cli_service_install_warns_on_legacy_plist(tmp_path, monkeypatch, capsys):
    agents = tmp_path / "LaunchAgents"
    agents.mkdir()
    (agents / "com.focusmonitor.agent.plist").write_text("<plist/>")

    logs = tmp_path / "logs"
    shim = tmp_path / "bin" / "focusmonitor-service"
    shim.parent.mkdir()
    shim.touch()

    monkeypatch.setattr(service, "LAUNCH_AGENTS_DIR", agents)
    import focusmonitor.config as cfg
    monkeypatch.setattr(cfg, "LOG_DIR", logs)
    monkeypatch.setattr(service, "shim_path", lambda: shim)

    args = type("A", (), {})()
    cli.cmd_service_install(args)

    err = capsys.readouterr().err
    assert "Legacy launchd agent detected" in err
    assert "com.focusmonitor.agent" in err

    # New plists still written despite the legacy warning.
    assert (agents / "com.focusmonitor.pulse.plist").exists()
    assert (agents / "com.focusmonitor.scope.plist").exists()
    # Legacy file left untouched.
    assert (agents / "com.focusmonitor.agent.plist").exists()
