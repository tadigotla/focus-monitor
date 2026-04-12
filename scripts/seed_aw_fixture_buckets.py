#!/usr/bin/env python3
"""Seed deterministic fixture buckets into a testing aw-server.

Usage:
    1. Start the testing aw-server in a separate terminal:
           /Applications/ActivityWatch.app/Contents/MacOS/aw-server --testing
       (binds localhost:5666, uses a separate testing database — production
       aw-server on :5600 is unaffected.)
    2. Run this script:
           python3 scripts/seed_aw_fixture_buckets.py
    3. Re-record ActivityWatch cassettes:
           .venv/bin/pytest --record-mode=rewrite tests/test_activitywatch.py

Everything posted by this script is hand-written fixture data. No real
window title, app name, or AFK event from the developer's live system
reaches the testing server. This keeps the resulting cassettes trivially
privacy-safe: the seed is the upper bound on what can be captured.

Re-run this script every time you re-record cassettes, because a fresh
`aw-server --testing` starts with an empty database.
"""

from __future__ import annotations

import json
import sys
from urllib.request import Request, urlopen


BASE = "http://localhost:5666/api/0"
HOSTNAME = "test-fixture"
WINDOW_BUCKET = f"aw-watcher-window_{HOSTNAME}"
AFK_BUCKET = f"aw-watcher-afk_{HOSTNAME}"


def _call(method: str, path: str, body=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    resp = urlopen(req)
    return resp.status, resp.read().decode()


def _delete_bucket(bucket_id: str) -> None:
    try:
        _call("DELETE", f"/buckets/{bucket_id}?force=1")
    except Exception:
        pass


def main() -> int:
    try:
        _, info = _call("GET", "/info")
    except Exception as exc:
        print(f"ERROR: cannot reach testing aw-server on :5666 ({exc})", file=sys.stderr)
        print("Start it first:  /Applications/ActivityWatch.app/Contents/MacOS/aw-server --testing", file=sys.stderr)
        return 1

    parsed = json.loads(info)
    if not parsed.get("testing"):
        print("ERROR: aw-server on :5666 reports testing=false. Refusing to seed a production instance.", file=sys.stderr)
        return 2

    # Clean slate — delete any existing fixture buckets from a prior run.
    _delete_bucket(WINDOW_BUCKET)
    _delete_bucket(AFK_BUCKET)

    # Create buckets.
    _call("POST", f"/buckets/{WINDOW_BUCKET}", {
        "client": "aw-watcher-window",
        "type": "currentwindow",
        "hostname": HOSTNAME,
    })
    _call("POST", f"/buckets/{AFK_BUCKET}", {
        "client": "aw-watcher-afk",
        "type": "afkstatus",
        "hostname": HOSTNAME,
    })

    # Window events — deterministic timestamps inside the 14:30-15:00 UTC
    # window that `freeze_clock` + `minutes=30` produces on 2026-04-12.
    window_events = [
        {
            "timestamp": "2026-04-12T14:45:00+00:00",
            "duration": 300.0,
            "data": {"app": "fixture-editor", "title": "fixture-window-code.py"},
        },
        {
            "timestamp": "2026-04-12T14:50:00+00:00",
            "duration": 240.0,
            "data": {"app": "fixture-terminal", "title": "fixture-shell"},
        },
        {
            "timestamp": "2026-04-12T14:54:00+00:00",
            "duration": 180.0,
            "data": {"app": "fixture-editor", "title": "fixture-window-notes.md"},
        },
        {
            "timestamp": "2026-04-12T14:57:00+00:00",
            "duration": 120.0,
            "data": {"app": "fixture-browser", "title": "fixture-local-docs"},
        },
    ]

    # AFK events — one active stretch followed by one idle stretch. The
    # "latest" event in the 10-minute window is the afk one, which is
    # what `test_returns_afk_when_latest_event_is_afk` asserts.
    afk_events = [
        {
            "timestamp": "2026-04-12T14:45:00+00:00",
            "duration": 600.0,
            "data": {"status": "not-afk"},
        },
        {
            "timestamp": "2026-04-12T14:55:00+00:00",
            "duration": 300.0,
            "data": {"status": "afk"},
        },
    ]

    _call("POST", f"/buckets/{WINDOW_BUCKET}/events", window_events)
    _call("POST", f"/buckets/{AFK_BUCKET}/events", afk_events)

    _, listing = _call("GET", "/buckets/")
    buckets = json.loads(listing)
    print(f"seeded {len(buckets)} bucket(s):")
    for name in buckets:
        print(f"  - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
