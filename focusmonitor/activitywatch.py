"""ActivityWatch event fetching and summarization."""

import json
from datetime import datetime, timedelta, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError

_afk_warning_printed = False


def _warn_afk_once(msg):
    global _afk_warning_printed
    if not _afk_warning_printed:
        print(f"⚠️  AFK gating inactive: {msg}")
        _afk_warning_printed = True


def get_aw_events(cfg, minutes=30):
    """Fetch recent events from ActivityWatch's aw-watcher-window bucket."""
    base = cfg["activitywatch_url"]
    try:
        resp = urlopen(f"{base}/api/0/buckets")
        buckets = json.loads(resp.read())
        watcher = None
        for name in buckets:
            if "aw-watcher-window" in name:
                watcher = name
                break
        if not watcher:
            print("⚠️  No aw-watcher-window bucket found. Is ActivityWatch running?")
            return []

        now = datetime.now(timezone.utc)
        start = (now - timedelta(minutes=minutes)).isoformat()
        end = now.isoformat()

        query = json.dumps({
            "query": [
                f'events = query_bucket("{watcher}");',
                "RETURN = events;"
            ],
            "timeperiods": [f"{start}/{end}"]
        }).encode()

        req = Request(f"{base}/api/0/query/", data=query,
                      headers={"Content-Type": "application/json"})
        resp = urlopen(req)
        results = json.loads(resp.read())
        if results and len(results) > 0:
            return results[0]
        return []
    except (URLError, Exception) as e:
        print(f"⚠️  ActivityWatch fetch failed: {e}")
        return []


def summarize_aw_events(events):
    """Condense raw AW events into a readable summary."""
    apps = {}
    titles = []
    for ev in events:
        d = ev.get("data", {})
        app = d.get("app", "unknown")
        title = d.get("title", "")
        dur = ev.get("duration", 0)
        apps[app] = apps.get(app, 0) + dur
        if title and title not in titles:
            titles.append(title)

    top_apps = sorted(apps.items(), key=lambda x: -x[1])[:10]
    top_titles = titles[:20]
    return top_apps, top_titles


def _parse_aw_ts(ts):
    # AW returns ISO timestamps with a trailing Z or +00:00; normalize both.
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def get_afk_state(cfg):
    """Return current AFK state from aw-watcher-afk.

    Returns {"status": "afk" | "not-afk" | "unknown", "since": datetime | None}.
    "since" is the start timestamp of the current AFK stretch (only set when
    status == "afk"). On any failure the helper returns "unknown" and logs a
    one-shot warning so ticks fall through to normal capture (fail-open).
    """
    base = cfg["activitywatch_url"]
    try:
        resp = urlopen(f"{base}/api/0/buckets")
        buckets = json.loads(resp.read())
    except (URLError, Exception) as e:
        _warn_afk_once(f"buckets fetch failed ({e})")
        return {"status": "unknown", "since": None}

    watcher = None
    for name in buckets:
        if name.startswith("aw-watcher-afk"):
            watcher = name
            break
    if not watcher:
        _warn_afk_once("no aw-watcher-afk bucket found")
        return {"status": "unknown", "since": None}

    try:
        now = datetime.now(timezone.utc)
        start = (now - timedelta(minutes=10)).isoformat()
        end = now.isoformat()
        query = json.dumps({
            "query": [
                f'events = query_bucket("{watcher}");',
                "RETURN = events;"
            ],
            "timeperiods": [f"{start}/{end}"]
        }).encode()
        req = Request(f"{base}/api/0/query/", data=query,
                      headers={"Content-Type": "application/json"})
        resp = urlopen(req)
        results = json.loads(resp.read())
        events = results[0] if results and len(results) > 0 else []
    except (URLError, Exception) as e:
        _warn_afk_once(f"AFK query failed ({e})")
        return {"status": "unknown", "since": None}

    if not events:
        return {"status": "unknown", "since": None}

    # AW returns events newest-first in this query shape; sort defensively.
    latest = max(events, key=lambda ev: ev.get("timestamp", ""))
    status = (latest.get("data") or {}).get("status")
    if status not in ("afk", "not-afk"):
        return {"status": "unknown", "since": None}

    if status == "not-afk":
        return {"status": "not-afk", "since": None}

    try:
        since = _parse_aw_ts(latest["timestamp"])
    except (KeyError, ValueError):
        return {"status": "unknown", "since": None}
    return {"status": "afk", "since": since}
