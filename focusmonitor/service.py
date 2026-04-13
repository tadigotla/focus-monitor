"""launchd service management for Pulse and Scope.

Two plists, one per component, sharing a shell shim that re-resolves
python at every invocation. See openspec/changes/consolidate-entrypoints/
for the design rationale.
"""

import os
import plistlib
import subprocess
from pathlib import Path

from focusmonitor.config import LOG_DIR

PULSE_LABEL = "com.focusmonitor.pulse"
SCOPE_LABEL = "com.focusmonitor.scope"
LEGACY_LABEL = "com.focusmonitor.agent"

LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def shim_path() -> Path:
    return repo_root() / "bin" / "focusmonitor-service"


def plist_path(label: str, agents_dir: Path | None = None) -> Path:
    if agents_dir is None:
        agents_dir = LAUNCH_AGENTS_DIR
    return agents_dir / f"{label}.plist"


def build_plist(label: str, component: str, shim: Path, log_dir: Path) -> bytes:
    """Return deterministic plist bytes for a component.

    component must be 'pulse' or 'scope'. The plist targets the shim
    rather than a hardcoded python path so brew/pyenv upgrades do not
    strand the service.
    """
    if component not in ("pulse", "scope"):
        raise ValueError(f"unknown component: {component}")

    data = {
        "Label": label,
        "ProgramArguments": [str(shim), "start", component],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(log_dir / f"{component}.out.log"),
        "StandardErrorPath": str(log_dir / f"{component}.err.log"),
        "WorkingDirectory": str(shim.parent.parent),
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
    }
    return plistlib.dumps(data, sort_keys=True)


def write_plists(agents_dir: Path | None = None,
                 log_dir: Path | None = None,
                 shim: Path | None = None) -> list[Path]:
    """Write both Pulse and Scope plists. Returns list of written paths.

    Defaults resolve at call-time so tests can redirect module globals
    with monkeypatch without rebinding the function.
    """
    if agents_dir is None:
        agents_dir = LAUNCH_AGENTS_DIR
    if log_dir is None:
        # Re-import so tests that patch focusmonitor.config.LOG_DIR
        # via monkeypatch are honored at call-time.
        from focusmonitor.config import LOG_DIR as _LOG_DIR
        log_dir = _LOG_DIR
    if shim is None:
        shim = shim_path()
    agents_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for label, component in ((PULSE_LABEL, "pulse"), (SCOPE_LABEL, "scope")):
        path = plist_path(label, agents_dir)
        path.write_bytes(build_plist(label, component, shim, log_dir))
        written.append(path)
    return written


def legacy_plist_warning(agents_dir: Path | None = None) -> str | None:
    """If the legacy com.focusmonitor.agent plist exists, return the
    multi-line warning text the user should see. Returns None otherwise.
    """
    if agents_dir is None:
        agents_dir = LAUNCH_AGENTS_DIR
    legacy = plist_path(LEGACY_LABEL, agents_dir)
    if not legacy.exists():
        return None
    uid = os.getuid()
    return (
        "\n"
        "⚠️  Legacy launchd agent detected: com.focusmonitor.agent\n"
        f"    at {legacy}\n"
        "\n"
        "    This plist points at monitor.py, which has been deleted.\n"
        "    launchd will respawn-loop it until you remove it. Run:\n"
        "\n"
        f"      launchctl bootout gui/{uid}/{LEGACY_LABEL} 2>/dev/null || \\\n"
        f"        launchctl unload {legacy}\n"
        f"      rm {legacy}\n"
        "      python3 cli.py service start\n"
        "\n"
    )


# ── launchctl wrappers ─────────────────────────────────────────────────────


def _uid() -> int:
    return os.getuid()


def _domain() -> str:
    return f"gui/{_uid()}"


def _launchctl(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["launchctl", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def bootstrap(plist: Path) -> subprocess.CompletedProcess:
    """Load a plist into the user domain. Falls back to `load` on older
    macOS if `bootstrap` is unavailable or returns an error.
    """
    result = _launchctl("bootstrap", _domain(), str(plist))
    if result.returncode != 0:
        result = _launchctl("load", str(plist))
    return result


def bootout(label: str) -> subprocess.CompletedProcess:
    result = _launchctl("bootout", f"{_domain()}/{label}")
    if result.returncode != 0:
        plist = plist_path(label)
        if plist.exists():
            result = _launchctl("unload", str(plist))
    return result


def print_service(label: str) -> subprocess.CompletedProcess:
    return _launchctl("print", f"{_domain()}/{label}")


def service_state(label: str, agents_dir: Path | None = None) -> str:
    """Return one of: not-installed, installed-but-not-loaded,
    loaded-and-running, loaded-but-crashing.
    """
    if agents_dir is None:
        agents_dir = LAUNCH_AGENTS_DIR
    if not plist_path(label, agents_dir).exists():
        return "not-installed"
    result = print_service(label)
    if result.returncode != 0:
        return "installed-but-not-loaded"
    out = result.stdout
    # `launchctl print` reports `state = running` for healthy services;
    # a non-zero `last exit code` (or `pid = 0` combined with recent
    # spawn activity) indicates crashing behaviour.
    if "state = running" in out:
        return "loaded-and-running"
    return "loaded-but-crashing"
