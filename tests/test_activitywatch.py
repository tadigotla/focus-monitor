"""Tests for `focusmonitor.activitywatch`.

The public surface is three functions and one private helper:

  - `get_aw_events(cfg, minutes)`       ← primary watcher-window query
  - `summarize_aw_events(events)`       ← pure helper, no network
  - `get_afk_state(cfg)`                ← AFK query
  - `_parse_aw_ts(ts)`                  ← ISO timestamp normalizer

The cassette-backed tests were captured against the testing aw-server
instance (port 5666, `aw-server --testing`) seeded with the fixture
buckets defined in the `seed_aw_buckets.py` helper. No data from the
developer's production ActivityWatch touches any cassette — every
window title, app name, and AFK event is a string written by hand.

Test config overrides `activitywatch_url` to point at `:5666` so the
cassettes record against the isolated instance. Production code at
runtime uses `:5600` via `DEFAULT_CONFIG` — the port is configurable,
so this is a faithful exercise of the same code path.

`get_aw_events` and `get_afk_state` compute the query window from
`datetime.now()`, so `freeze_clock` is mandatory for cassette stability:
without it the recorded URL/body and the replayed URL/body would
disagree and vcrpy would fail to match.
"""

from __future__ import annotations

import pytest

from focusmonitor.activitywatch import (
    _parse_aw_ts,
    get_afk_state,
    get_aw_events,
    summarize_aw_events,
)
from focusmonitor.config import DEFAULT_CONFIG


TESTING_AW_URL = "http://localhost:5666"


@pytest.fixture
def aw_test_cfg():
    """Config pointing at the testing aw-server instance on :5666."""
    cfg = DEFAULT_CONFIG.copy()
    cfg["activitywatch_url"] = TESTING_AW_URL
    return cfg


# ── summarize_aw_events: pure function, no network ───────────────────────────

class TestSummarizeAwEvents:

    def test_empty_list(self):
        top_apps, top_titles = summarize_aw_events([])
        assert top_apps == []
        assert top_titles == []

    def test_aggregates_app_durations(self):
        events = [
            {"duration": 300, "data": {"app": "A", "title": "a1"}},
            {"duration": 200, "data": {"app": "B", "title": "b1"}},
            {"duration": 100, "data": {"app": "A", "title": "a2"}},
        ]
        top_apps, _ = summarize_aw_events(events)
        assert top_apps[0] == ("A", 400)  # 300 + 100
        assert top_apps[1] == ("B", 200)

    def test_preserves_unique_titles_in_order(self):
        events = [
            {"duration": 10, "data": {"app": "X", "title": "first"}},
            {"duration": 10, "data": {"app": "X", "title": "second"}},
            {"duration": 10, "data": {"app": "X", "title": "first"}},  # dup
            {"duration": 10, "data": {"app": "X", "title": "third"}},
        ]
        _, top_titles = summarize_aw_events(events)
        assert top_titles == ["first", "second", "third"]

    def test_missing_app_defaults_to_unknown(self):
        events = [{"duration": 50, "data": {}}]
        top_apps, top_titles = summarize_aw_events(events)
        assert top_apps == [("unknown", 50)]
        assert top_titles == []

    def test_top_apps_limited_to_10(self):
        events = [
            {"duration": 100 - i, "data": {"app": f"app{i}", "title": f"t{i}"}}
            for i in range(15)
        ]
        top_apps, _ = summarize_aw_events(events)
        assert len(top_apps) == 10

    def test_top_titles_limited_to_20(self):
        events = [
            {"duration": 10, "data": {"app": "X", "title": f"title{i}"}}
            for i in range(25)
        ]
        _, top_titles = summarize_aw_events(events)
        assert len(top_titles) == 20


# ── _parse_aw_ts: pure function, no network ──────────────────────────────────

class TestParseAwTs:

    def test_z_suffix(self):
        dt = _parse_aw_ts("2026-04-12T14:45:00Z")
        assert dt.year == 2026
        assert dt.hour == 14

    def test_offset_suffix(self):
        dt = _parse_aw_ts("2026-04-12T14:45:00+00:00")
        assert dt.year == 2026
        assert dt.hour == 14

    def test_microseconds_preserved(self):
        dt = _parse_aw_ts("2026-04-12T14:45:00.123456+00:00")
        assert dt.microsecond == 123456


# ── get_aw_events: cassette-backed against fixture buckets ───────────────────

@pytest.mark.vcr(cassette_library_dir="tests/cassettes/activitywatch")
class TestGetAwEvents:

    def test_returns_fixture_events(self, aw_test_cfg, freeze_clock):
        """Happy path: query the seeded aw-watcher-window_test-fixture bucket.

        Frozen at 2026-04-12T15:00:00 with minutes=30, window covers all
        four seeded fixture events (14:45, 14:50, 14:54, 14:57).
        """
        events = get_aw_events(aw_test_cfg, minutes=30)
        assert len(events) == 4
        apps = {ev["data"]["app"] for ev in events}
        assert apps == {"fixture-editor", "fixture-terminal", "fixture-browser"}
        titles = {ev["data"]["title"] for ev in events}
        assert titles == {
            "fixture-window-code.py",
            "fixture-shell",
            "fixture-window-notes.md",
            "fixture-local-docs",
        }

    def test_returned_events_have_duration_and_timestamp(
        self, aw_test_cfg, freeze_clock
    ):
        events = get_aw_events(aw_test_cfg, minutes=30)
        for ev in events:
            assert "timestamp" in ev
            assert "duration" in ev
            assert isinstance(ev["duration"], (int, float))


# ── get_afk_state: cassette-backed ───────────────────────────────────────────

@pytest.mark.vcr(cassette_library_dir="tests/cassettes/activitywatch")
class TestGetAfkState:

    def test_returns_afk_when_latest_event_is_afk(
        self, aw_test_cfg, freeze_clock
    ):
        """Seeded AFK bucket has not-afk at 14:45 and afk at 14:55.

        Latest within the 10-minute window (14:50-15:00) is the afk event,
        so `get_afk_state` returns `{"status": "afk", "since": <datetime>}`.
        """
        state = get_afk_state(aw_test_cfg)
        assert state["status"] == "afk"
        assert state["since"] is not None
        # The since timestamp must equal the afk event's start.
        assert state["since"].hour == 14
        assert state["since"].minute == 55


# ── Failure paths: no cassette, point at an unreachable localhost port ───────

class TestActivityWatchFailurePaths:

    def test_get_aw_events_unreachable_returns_empty(self):
        cfg = DEFAULT_CONFIG.copy()
        cfg["activitywatch_url"] = "http://127.0.0.1:1"
        assert get_aw_events(cfg, minutes=30) == []

    def test_get_afk_state_unreachable_returns_unknown(self):
        cfg = DEFAULT_CONFIG.copy()
        cfg["activitywatch_url"] = "http://127.0.0.1:1"
        state = get_afk_state(cfg)
        assert state == {"status": "unknown", "since": None}
