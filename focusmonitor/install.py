"""Install-time preflight probes.

Health-checks for the external services focus-monitor depends on
(Ollama and ActivityWatch). Used by `setup.py` to surface a concrete
fix-it command when something is missing or down, and by
`tests/test_install_flow.py` for unit testing without real services.

Stdlib-only on purpose: `setup.py` runs before the dev venv exists, so
this module MUST NOT import anything from `requirements-dev.txt` or any
third-party package.
"""

from __future__ import annotations

import json
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


# ── Public constants (monkeypatchable in tests) ──────────────────────────────

OLLAMA_URL = "http://127.0.0.1:11434"
ACTIVITYWATCH_URL = "http://127.0.0.1:5600"
EXPECTED_OLLAMA_MODEL = "llama3.2-vision"
PROBE_TIMEOUT_SEC = 2.0

# Candidate install paths for the ActivityWatch app bundle.
_AW_APP_CANDIDATES = (
    Path("/Applications/ActivityWatch.app"),
    Path.home() / "Applications" / "ActivityWatch.app",
)


ProbeState = Literal["missing", "daemon_down", "wrong_state", "ok", "unknown"]


@dataclass(frozen=True)
class ProbeResult:
    """Outcome of a single health probe.

    `state` is the primary signal. `message` is a one-line human summary.
    `next_command` is the exact command the user should run to fix the
    current state (empty string when `state == "ok"`).
    """
    state: ProbeState
    message: str
    next_command: str = ""


# ── Binary-presence helpers ──────────────────────────────────────────────────

def _ollama_binary_present() -> bool:
    return shutil.which("ollama") is not None


def _aw_app_present() -> bool:
    return any(p.exists() for p in _AW_APP_CANDIDATES)


# ── Probes ───────────────────────────────────────────────────────────────────

def probe_ollama(
    url: str = OLLAMA_URL,
    expected_model: str = EXPECTED_OLLAMA_MODEL,
    timeout: float = PROBE_TIMEOUT_SEC,
) -> ProbeResult:
    """Check whether Ollama is installed, running, and has the expected model.

    Returns a ProbeResult with one of five states:
      - "missing"      : binary not on PATH
      - "daemon_down"  : binary present but /api/tags is unreachable
      - "wrong_state"  : daemon up but model not pulled
      - "ok"           : daemon up and model pulled
      - "unknown"      : probe threw something unexpected (fail-open)
    """
    if not _ollama_binary_present():
        return ProbeResult(
            state="missing",
            message="Ollama not found.",
            next_command="brew install ollama",
        )

    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.URLError:
        return ProbeResult(
            state="daemon_down",
            message="Ollama binary present but daemon is not responding.",
            next_command="ollama serve   # or: brew services start ollama",
        )
    except Exception as exc:  # pragma: no cover - fail-open guardrail
        return ProbeResult(
            state="unknown",
            message=f"Ollama probe failed unexpectedly: {exc}",
            next_command="",
        )

    try:
        data = json.loads(body)
        models = data.get("models", [])
        names = [m.get("name", "") for m in models if isinstance(m, dict)]
    except (json.JSONDecodeError, TypeError, AttributeError) as exc:
        return ProbeResult(
            state="unknown",
            message=f"Ollama returned an unparseable response: {exc}",
            next_command="",
        )

    # Match on prefix so "llama3.2-vision:latest" counts as "llama3.2-vision".
    if not any(name == expected_model or name.startswith(f"{expected_model}:")
               for name in names):
        return ProbeResult(
            state="wrong_state",
            message=f"Ollama daemon healthy but model '{expected_model}' not pulled.",
            next_command=f"ollama pull {expected_model}",
        )

    return ProbeResult(
        state="ok",
        message=f"Ollama daemon healthy, model '{expected_model}' available.",
        next_command="",
    )


def probe_activitywatch(
    url: str = ACTIVITYWATCH_URL,
    timeout: float = PROBE_TIMEOUT_SEC,
) -> ProbeResult:
    """Check whether ActivityWatch is installed and responding.

    Returns a ProbeResult with one of four states:
      - "missing"      : ActivityWatch.app not found in either candidate path
      - "daemon_down"  : app present but /api/0/info is unreachable
      - "ok"           : /api/0/info returns a 2xx (bucket existence is NOT
                         checked — that's a runtime concern, not setup's)
      - "unknown"      : probe threw something unexpected (fail-open)
    """
    if not _aw_app_present():
        return ProbeResult(
            state="missing",
            message="ActivityWatch.app not found.",
            next_command="brew install --cask activitywatch   # or: https://activitywatch.net/",
        )

    try:
        with urllib.request.urlopen(f"{url}/api/0/info", timeout=timeout) as resp:
            # Any 2xx is fine; we don't inspect the body beyond confirming
            # the connection completed cleanly.
            _ = resp.read()
    except urllib.error.URLError:
        return ProbeResult(
            state="daemon_down",
            message="ActivityWatch installed but not running.",
            next_command="open /Applications/ActivityWatch.app",
        )
    except Exception as exc:  # pragma: no cover - fail-open guardrail
        return ProbeResult(
            state="unknown",
            message=f"ActivityWatch probe failed unexpectedly: {exc}",
            next_command="",
        )

    return ProbeResult(
        state="ok",
        message="ActivityWatch daemon healthy.",
        next_command="",
    )
