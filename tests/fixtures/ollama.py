"""Pytest fixtures for `focusmonitor.ollama` tests.

The real client in `focusmonitor/ollama.py` uses `urllib.request.urlopen`
against `cfg['ollama_url']`. vcrpy intercepts the HTTP call at the
`http.client.HTTPConnection` layer, so these tests hit vcrpy before any
socket is opened — meaning they coexist with `pytest-socket`'s default
block.

Cassettes live under `tests/cassettes/ollama/<test_name>.yaml` and are
replay-only by default. To re-record, pass `--record-mode=rewrite` on the
command line with real Ollama running on `localhost:11434`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from focusmonitor.config import DEFAULT_CONFIG


CASSETTE_DIR = Path(__file__).resolve().parent.parent / "cassettes" / "ollama"


@pytest.fixture
def ollama_cfg():
    """Minimal config dict sufficient for `query_ollama` calls.

    Pulls from DEFAULT_CONFIG so cassette captures match the real runtime
    model and URL. Tests that need a different model should override only
    the keys they care about instead of constructing a dict from scratch.
    """
    cfg = DEFAULT_CONFIG.copy()
    return cfg


@pytest.fixture
def vcr_config():
    """pytest-recording hook: configure cassette behaviour globally.

    - `record_mode` is intentionally NOT set here. pytest-recording
      defaults to "none" (replay-only) and `--record-mode=rewrite` on
      the CLI overrides it. If we pin it in the fixture, the fixture
      wins over the CLI flag, which is the opposite of what we want.
    - `filter_headers` strips any auth tokens that might leak in.
    - `decode_compressed_response` makes cassettes human-reviewable.
    """
    return {
        "filter_headers": ["authorization", "cookie", "set-cookie"],
        "decode_compressed_response": True,
        "cassette_library_dir": str(CASSETTE_DIR),
    }
