"""Pytest fixtures for `focusmonitor.activitywatch` tests.

Same shape as `tests/fixtures/ollama.py`: configure vcrpy for replay-only
against cassettes under `tests/cassettes/activitywatch/`, and hand tests a
config dict pointing at the real localhost URL so recorded requests
match production shape byte-for-byte.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from focusmonitor.config import DEFAULT_CONFIG


CASSETTE_DIR = (
    Path(__file__).resolve().parent.parent / "cassettes" / "activitywatch"
)


@pytest.fixture
def aw_cfg():
    return DEFAULT_CONFIG.copy()


@pytest.fixture
def aw_vcr_config():
    return {
        "record_mode": "none",
        "filter_headers": ["authorization", "cookie", "set-cookie"],
        "decode_compressed_response": True,
        "cassette_library_dir": str(CASSETTE_DIR),
    }
