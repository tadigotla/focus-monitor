"""ActivityWatch event fetching and summarization."""

import json
from datetime import datetime, timedelta, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError


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
