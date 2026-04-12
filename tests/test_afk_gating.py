"""AFK parser edge cases + `should_skip_tick` gating logic.

This file does two things:

1. Exercises `focusmonitor.activitywatch.get_afk_state` against a variety
   of hand-crafted HTTP response shapes using `monkeypatch.setattr` on
   `aw.urlopen`. This is *intentionally* not cassette-backed — the goal
   is parser robustness against unusual payloads, and the faithful
   cassette coverage of the happy/unreachable paths already lives in
   `tests/test_activitywatch.py`. Think of these as parser unit tests
   that complement the integration tests.

2. Exercises `focusmonitor.main.should_skip_tick` by replacing
   `fm_main.get_afk_state` with a canned function — the goal here is
   the decision logic, not AW parsing.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from urllib.error import URLError

import pytest

from focusmonitor import activitywatch as aw
# Grab the real submodule even though focusmonitor/__init__.py rebinds
# `focusmonitor.main` to the function.
import focusmonitor.main  # ensures submodule is in sys.modules
fm_main = sys.modules["focusmonitor.main"]


CFG = {"activitywatch_url": "http://localhost:5600", "idle_skip_grace_sec": 60}


class _FakeResp:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode()

    def read(self):
        return self._data


def _install_fake_urlopen(monkeypatch, *, buckets, events, fail_on=None):
    """Replace `aw.urlopen` with a routing stub."""
    def fake(req_or_url, *args, **kwargs):
        url = req_or_url if isinstance(req_or_url, str) else req_or_url.full_url
        if "/api/0/buckets" in url:
            if fail_on == "buckets":
                raise URLError("boom")
            return _FakeResp(buckets)
        if "/api/0/query" in url:
            if fail_on == "query":
                raise URLError("boom")
            return _FakeResp([events])
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(aw, "urlopen", fake)
    monkeypatch.setattr(aw, "URLError", URLError, raising=False)
    monkeypatch.setattr(aw, "_afk_warning_printed", False)


# ── get_afk_state parser edge cases ──────────────────────────────────────────

class TestGetAfkStateParser:

    def test_not_afk(self, monkeypatch):
        _install_fake_urlopen(monkeypatch,
            buckets={"aw-watcher-afk_host": {}},
            events=[{"timestamp": "2026-04-12T10:00:00Z", "duration": 30,
                     "data": {"status": "not-afk"}}],
        )
        state = aw.get_afk_state(CFG)
        assert state == {"status": "not-afk", "since": None}

    def test_afk_returns_afk_with_since(self, monkeypatch):
        _install_fake_urlopen(monkeypatch,
            buckets={"aw-watcher-afk_host": {}},
            events=[{"timestamp": "2026-04-12T10:00:00+00:00", "duration": 30,
                     "data": {"status": "afk"}}],
        )
        state = aw.get_afk_state(CFG)
        assert state["status"] == "afk"
        assert state["since"] == datetime(2026, 4, 12, 10, 0, 0, tzinfo=timezone.utc)

    def test_z_suffix_timestamp(self, monkeypatch):
        _install_fake_urlopen(monkeypatch,
            buckets={"aw-watcher-afk_host": {}},
            events=[{"timestamp": "2026-04-12T11:00:00Z", "duration": 30,
                     "data": {"status": "afk"}}],
        )
        state = aw.get_afk_state(CFG)
        assert state["since"] == datetime(2026, 4, 12, 11, 0, 0, tzinfo=timezone.utc)

    def test_latest_event_wins_when_unordered(self, monkeypatch):
        _install_fake_urlopen(monkeypatch,
            buckets={"aw-watcher-afk_host": {}},
            events=[
                {"timestamp": "2026-04-12T09:00:00Z", "duration": 30,
                 "data": {"status": "not-afk"}},
                {"timestamp": "2026-04-12T10:00:00Z", "duration": 30,
                 "data": {"status": "afk"}},
            ],
        )
        assert aw.get_afk_state(CFG)["status"] == "afk"

    def test_no_afk_bucket_returns_unknown(self, monkeypatch):
        _install_fake_urlopen(monkeypatch,
            buckets={"aw-watcher-window_host": {}},
            events=[],
        )
        assert aw.get_afk_state(CFG) == {"status": "unknown", "since": None}

    def test_empty_events_returns_unknown(self, monkeypatch):
        _install_fake_urlopen(monkeypatch,
            buckets={"aw-watcher-afk_host": {}},
            events=[],
        )
        assert aw.get_afk_state(CFG)["status"] == "unknown"

    def test_unrecognized_status_returns_unknown(self, monkeypatch):
        _install_fake_urlopen(monkeypatch,
            buckets={"aw-watcher-afk_host": {}},
            events=[{"timestamp": "2026-04-12T10:00:00Z", "duration": 30,
                     "data": {"status": "wat"}}],
        )
        assert aw.get_afk_state(CFG)["status"] == "unknown"

    def test_missing_data_field_returns_unknown(self, monkeypatch):
        _install_fake_urlopen(monkeypatch,
            buckets={"aw-watcher-afk_host": {}},
            events=[{"timestamp": "2026-04-12T10:00:00Z", "duration": 30}],
        )
        assert aw.get_afk_state(CFG)["status"] == "unknown"

    def test_buckets_failure_returns_unknown(self, monkeypatch):
        _install_fake_urlopen(monkeypatch,
            buckets={}, events=[], fail_on="buckets",
        )
        assert aw.get_afk_state(CFG)["status"] == "unknown"

    def test_query_failure_returns_unknown(self, monkeypatch):
        _install_fake_urlopen(monkeypatch,
            buckets={"aw-watcher-afk_host": {}},
            events=[], fail_on="query",
        )
        assert aw.get_afk_state(CFG)["status"] == "unknown"


# ── should_skip_tick decision logic ──────────────────────────────────────────

FIXED_NOW = datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc)


class _FrozenDT(datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED_NOW if tz is None else FIXED_NOW.astimezone(tz)


@pytest.fixture
def frozen_main_clock(monkeypatch):
    """Replace `datetime` inside focusmonitor.main with a frozen subclass."""
    monkeypatch.setattr(fm_main, "datetime", _FrozenDT)
    yield


def _fake_state(status, since_delta_sec):
    since = None if since_delta_sec is None else FIXED_NOW - timedelta(seconds=since_delta_sec)
    return {"status": status, "since": since}


def _run_skip(monkeypatch, cfg, status, since_delta_sec):
    monkeypatch.setattr(fm_main, "get_afk_state", lambda _cfg: _fake_state(status, since_delta_sec))
    return fm_main.should_skip_tick(cfg)


class TestShouldSkipTick:

    CFG60 = {"idle_skip_grace_sec": 60}
    CFG0 = {"idle_skip_grace_sec": 0}
    CFG_HUGE = {"idle_skip_grace_sec": 86400}

    def test_not_afk_never_skips(self, monkeypatch, frozen_main_clock):
        assert _run_skip(monkeypatch, self.CFG60, "not-afk", None) is False

    def test_unknown_never_skips_fail_open(self, monkeypatch, frozen_main_clock):
        assert _run_skip(monkeypatch, self.CFG60, "unknown", None) is False

    def test_afk_just_under_grace(self, monkeypatch, frozen_main_clock):
        assert _run_skip(monkeypatch, self.CFG60, "afk", 59) is False

    def test_afk_exactly_at_grace_skips(self, monkeypatch, frozen_main_clock):
        assert _run_skip(monkeypatch, self.CFG60, "afk", 60) is True

    def test_afk_well_past_grace_skips(self, monkeypatch, frozen_main_clock):
        assert _run_skip(monkeypatch, self.CFG60, "afk", 600) is True

    def test_grace_zero_skips_immediately(self, monkeypatch, frozen_main_clock):
        assert _run_skip(monkeypatch, self.CFG0, "afk", 1) is True

    def test_grace_zero_never_skips_on_not_afk(self, monkeypatch, frozen_main_clock):
        assert _run_skip(monkeypatch, self.CFG0, "not-afk", None) is False

    def test_huge_grace_suppresses_normal_idle(self, monkeypatch, frozen_main_clock):
        assert _run_skip(monkeypatch, self.CFG_HUGE, "afk", 3600) is False

    def test_afk_with_no_since_does_not_skip(self, monkeypatch, frozen_main_clock):
        assert _run_skip(monkeypatch, self.CFG60, "afk", None) is False
