#!/usr/bin/env python3
"""Tests for AFK gating in the main loop.

Covers:
  - activitywatch.get_afk_state parsing under fake urlopen responses.
  - main.should_skip_tick decision across grace-window edges.
  - Fail-open: status="unknown" must never cause a skip.
"""

import io
import json
import sys
from datetime import datetime, timedelta, timezone

import focusmonitor.activitywatch as aw
# focusmonitor/__init__.py does `from focusmonitor.main import main`, which
# rebinds `focusmonitor.main` to the function. Grab the real module from
# sys.modules so we can patch module-level attributes.
import focusmonitor.main  # ensures the submodule is in sys.modules
fm_main = sys.modules["focusmonitor.main"]
from focusmonitor.config import DEFAULT_CONFIG

passed = 0
failed = 0


def test(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}")


class FakeResp:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode()

    def read(self):
        return self._data


def install_fake_urlopen(buckets, events, fail_on=None):
    calls = {"buckets": 0, "query": 0}

    def fake_urlopen(req_or_url, *args, **kwargs):
        url = req_or_url if isinstance(req_or_url, str) else req_or_url.full_url
        if "/api/0/buckets" in url:
            calls["buckets"] += 1
            if fail_on == "buckets":
                raise URLError("boom")
            return FakeResp(buckets)
        if "/api/0/query" in url:
            calls["query"] += 1
            if fail_on == "query":
                raise URLError("boom")
            return FakeResp([events])
        raise AssertionError(f"unexpected URL: {url}")

    aw.urlopen = fake_urlopen
    return calls


def reset_warning_flag():
    aw._afk_warning_printed = False


# Make URLError importable via aw module so fake_urlopen can raise it.
from urllib.error import URLError
aw.URLError = URLError


CFG = {"activitywatch_url": "http://localhost:5600", "idle_skip_grace_sec": 60}


# ── get_afk_state parsing ────────────────────────────────────────────────────

print("\n== get_afk_state ==")

# not-afk
reset_warning_flag()
install_fake_urlopen(
    buckets={"aw-watcher-afk_host": {}},
    events=[{"timestamp": "2026-04-12T10:00:00Z", "duration": 30,
             "data": {"status": "not-afk"}}],
)
state = aw.get_afk_state(CFG)
test("not-afk returns not-afk", state["status"] == "not-afk" and state["since"] is None)

# afk with since
reset_warning_flag()
install_fake_urlopen(
    buckets={"aw-watcher-afk_host": {}},
    events=[{"timestamp": "2026-04-12T10:00:00+00:00", "duration": 30,
             "data": {"status": "afk"}}],
)
state = aw.get_afk_state(CFG)
test("afk returns afk with since", state["status"] == "afk" and state["since"] is not None)
test("afk since parsed correctly",
     state["since"] == datetime(2026, 4, 12, 10, 0, 0, tzinfo=timezone.utc))

# Z-suffix timestamp
reset_warning_flag()
install_fake_urlopen(
    buckets={"aw-watcher-afk_host": {}},
    events=[{"timestamp": "2026-04-12T11:00:00Z", "duration": 30,
             "data": {"status": "afk"}}],
)
state = aw.get_afk_state(CFG)
test("Z-suffix timestamp parsed",
     state["since"] == datetime(2026, 4, 12, 11, 0, 0, tzinfo=timezone.utc))

# Newest-event picked when events are unordered
reset_warning_flag()
install_fake_urlopen(
    buckets={"aw-watcher-afk_host": {}},
    events=[
        {"timestamp": "2026-04-12T09:00:00Z", "duration": 30,
         "data": {"status": "not-afk"}},
        {"timestamp": "2026-04-12T10:00:00Z", "duration": 30,
         "data": {"status": "afk"}},
    ],
)
state = aw.get_afk_state(CFG)
test("latest event wins when unordered", state["status"] == "afk")

# No AFK bucket → unknown
reset_warning_flag()
install_fake_urlopen(
    buckets={"aw-watcher-window_host": {}},
    events=[],
)
state = aw.get_afk_state(CFG)
test("no AFK bucket → unknown", state["status"] == "unknown" and state["since"] is None)

# Empty events list → unknown
reset_warning_flag()
install_fake_urlopen(
    buckets={"aw-watcher-afk_host": {}},
    events=[],
)
state = aw.get_afk_state(CFG)
test("empty events → unknown", state["status"] == "unknown")

# Malformed status → unknown
reset_warning_flag()
install_fake_urlopen(
    buckets={"aw-watcher-afk_host": {}},
    events=[{"timestamp": "2026-04-12T10:00:00Z", "duration": 30,
             "data": {"status": "wat"}}],
)
state = aw.get_afk_state(CFG)
test("unrecognized status → unknown", state["status"] == "unknown")

# Missing data field → unknown
reset_warning_flag()
install_fake_urlopen(
    buckets={"aw-watcher-afk_host": {}},
    events=[{"timestamp": "2026-04-12T10:00:00Z", "duration": 30}],
)
state = aw.get_afk_state(CFG)
test("missing data → unknown", state["status"] == "unknown")

# buckets fetch fails → unknown
reset_warning_flag()
install_fake_urlopen(
    buckets={},
    events=[],
    fail_on="buckets",
)
state = aw.get_afk_state(CFG)
test("buckets failure → unknown", state["status"] == "unknown")

# query fetch fails → unknown
reset_warning_flag()
install_fake_urlopen(
    buckets={"aw-watcher-afk_host": {}},
    events=[],
    fail_on="query",
)
state = aw.get_afk_state(CFG)
test("query failure → unknown", state["status"] == "unknown")


# ── should_skip_tick ─────────────────────────────────────────────────────────

print("\n== should_skip_tick ==")

FIXED_NOW = datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc)


class FrozenDT(datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED_NOW if tz is None else FIXED_NOW.astimezone(tz)


# Monkey-patch datetime inside focusmonitor.main so elapsed math is deterministic.
fm_main.datetime = FrozenDT


def fake_state(status, since_delta_sec):
    since = None if since_delta_sec is None else FIXED_NOW - timedelta(seconds=since_delta_sec)
    return {"status": status, "since": since}


def run_skip(cfg, status, since_delta_sec):
    fm_main.get_afk_state = lambda _cfg: fake_state(status, since_delta_sec)
    return fm_main.should_skip_tick(cfg)


cfg60 = {"idle_skip_grace_sec": 60}

test("not-afk never skips", run_skip(cfg60, "not-afk", None) is False)
test("unknown never skips (fail-open)", run_skip(cfg60, "unknown", None) is False)
test("afk just under grace (59s) does not skip", run_skip(cfg60, "afk", 59) is False)
test("afk exactly at grace (60s) skips", run_skip(cfg60, "afk", 60) is True)
test("afk well past grace (600s) skips", run_skip(cfg60, "afk", 600) is True)

cfg0 = {"idle_skip_grace_sec": 0}
test("grace=0 skips immediately on afk", run_skip(cfg0, "afk", 1) is True)
test("grace=0 never skips on not-afk", run_skip(cfg0, "not-afk", None) is False)

cfg_huge = {"idle_skip_grace_sec": 86400}
test("huge grace suppresses skip for normal idle",
     run_skip(cfg_huge, "afk", 3600) is False)

# afk with since=None is a degenerate case — should NOT skip (fail-safe).
test("afk with no since does not skip", run_skip(cfg60, "afk", None) is False)


# ── summary ──────────────────────────────────────────────────────────────────

print(f"\n{passed} passed, {failed} failed")
if failed:
    import sys
    sys.exit(1)
