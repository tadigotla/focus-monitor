"""Dashboard HTML generation and HTTP server."""

import re
import sqlite3
import json
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from focusmonitor.config import DB_PATH

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Focus Monitor — Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'DM Sans', sans-serif;
    background: #0e0e12;
    color: #d4d4d8;
    padding: 2rem;
    min-height: 100vh;
  }
  h1 {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.4rem;
    color: #a1a1aa;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 0.3rem;
  }
  .subtitle { color: #52525b; font-size: 0.85rem; margin-bottom: 2rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.2rem; margin-bottom: 2rem; }
  .card {
    background: #18181b;
    border: 1px solid #27272a;
    border-radius: 12px;
    padding: 1.4rem;
  }
  .card h2 {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: #71717a;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 1rem;
  }
  .big-number { font-size: 2.8rem; font-weight: 700; color: #fafafa; }
  .big-number.good { color: #34d399; }
  .big-number.mid { color: #fbbf24; }
  .big-number.bad { color: #f87171; }
  .label { font-size: 0.8rem; color: #52525b; margin-top: 0.2rem; }
  .timeline { margin-top: 2rem; }
  .entry {
    background: #18181b;
    border: 1px solid #27272a;
    border-radius: 10px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 0.8rem;
    display: grid;
    grid-template-columns: 80px 1fr auto;
    gap: 1rem;
    align-items: start;
  }
  .entry-time {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    color: #71717a;
    padding-top: 0.15rem;
  }
  .entry-summary { font-size: 0.9rem; line-height: 1.5; }
  .entry-score {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.3rem;
    font-weight: 700;
    min-width: 50px;
    text-align: right;
  }
  .tags { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.5rem; }
  .tag {
    font-size: 0.7rem;
    padding: 0.2rem 0.6rem;
    border-radius: 100px;
    font-family: 'JetBrains Mono', monospace;
  }
  .tag.project { background: #1e3a5f; color: #60a5fa; }
  .tag.distraction { background: #4a1c1c; color: #f87171; }
  .tag.planned { background: #1a3a2a; color: #34d399; }
  .nudge-list { list-style: none; }
  .nudge-list li {
    padding: 0.5rem 0;
    border-bottom: 1px solid #27272a;
    font-size: 0.85rem;
  }
  .nudge-list li:last-child { border: none; }
  .nudge-time { font-family: 'JetBrains Mono', monospace; color: #71717a; font-size: 0.75rem; }
  .empty { color: #52525b; font-style: italic; font-size: 0.85rem; }
</style>
</head>
<body>
  <h1>Focus Monitor</h1>
  <div class="subtitle">GENERATED_AT</div>

  <div class="grid">
    <div class="card">
      <h2>Avg Focus Score (today)</h2>
      <div class="big-number SCORE_CLASS">SCORE_VALUE</div>
      <div class="label">out of 100</div>
    </div>
    <div class="card">
      <h2>Analyses Today</h2>
      <div class="big-number" style="color:#fafafa">ANALYSIS_COUNT</div>
      <div class="label">sessions tracked</div>
    </div>
    <div class="card">
      <h2>Nudges Sent</h2>
      <div class="big-number" style="color:#fbbf24">NUDGE_COUNT</div>
      <div class="label">reminders today</div>
    </div>
    <div class="card">
      <h2>Top Apps</h2>
      TOP_APPS_HTML
    </div>
  </div>

  <h1 style="margin-bottom:1rem;">Timeline</h1>
  <div class="timeline">
    TIMELINE_HTML
  </div>

  <h1 style="margin-top:2rem; margin-bottom:1rem;">Recent Nudges</h1>
  <div class="card">
    NUDGES_HTML
  </div>
</body>
</html>
"""


def score_class(s):
    if s >= 70: return "good"
    if s >= 40: return "mid"
    return "bad"


def _try_parse_json(text):
    """Try to extract a JSON object from text, handling common model quirks."""
    if not text:
        return None
    r = text.strip()
    if r.startswith("```"):
        r = "\n".join(r.split("\n")[1:])
    if r.rstrip().endswith("```"):
        r = r.rstrip().rsplit("```", 1)[0]
    r = r.replace("\\_", "_")
    r = r.strip()
    try:
        return json.loads(r)
    except Exception:
        pass
    start = r.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(r)):
            if r[i] == "{": depth += 1
            elif r[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(r[start:i + 1])
                    except Exception:
                        break
    result = {}
    m = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', r)
    if m:
        result["summary"] = m.group(1).replace('\\"', '"')
    m = re.search(r'"focus_score"\s*:\s*(\d+)', r)
    if m:
        result["focus_score"] = int(m.group(1))
    for field in ("projects", "planned_match", "planned_tasks", "distractions"):
        m = re.search(r'"' + field + r'"\s*:\s*\[([^\]]*)\]', r)
        if m:
            items = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))
            result[field] = items
    if "planned_tasks" in result and "planned_match" not in result:
        result["planned_match"] = result.pop("planned_tasks")
    return result if result else None


def build_dashboard(refresh_sec=0):
    """Build dashboard HTML and return it as a string."""
    if not DB_PATH.exists():
        return None

    db = sqlite3.connect(str(DB_PATH))
    today = datetime.now().strftime("%Y-%m-%d")

    rows = db.execute(
        "SELECT summary, raw_response, timestamp, apps_used, project_detected FROM activity_log WHERE timestamp LIKE ?",
        (f"{today}%",)
    ).fetchall()

    scores = []
    entries_html = []
    all_apps = {}

    for summary, raw, ts, apps_json, projects_json in rows:
        score = -1
        projects = []
        distractions = []
        planned = []
        display_summary = summary

        parsed = _try_parse_json(raw)
        if parsed:
            score = parsed.get("focus_score", -1)
            projects = parsed.get("projects", [])
            distractions = parsed.get("distractions", [])
            planned = parsed.get("planned_match", parsed.get("planned_tasks", []))
            if parsed.get("summary"):
                display_summary = parsed["summary"]

        if display_summary and display_summary.strip()[:1] in ("{", "`"):
            fallback = _try_parse_json(display_summary)
            if fallback and fallback.get("summary"):
                display_summary = fallback["summary"]

        if score >= 0:
            scores.append(score)

        try:
            for app in json.loads(apps_json or "[]"):
                all_apps[app] = all_apps.get(app, 0) + 1
        except Exception:
            pass

        try:
            t = datetime.fromisoformat(ts).strftime("%H:%M")
        except Exception:
            t = "?"

        tags = ""
        for p in projects:
            tags += f'<span class="tag project">{p}</span>'
        for p in planned:
            tags += f'<span class="tag planned">✓ {p}</span>'
        for d in distractions:
            tags += f'<span class="tag distraction">{d}</span>'

        sc_class = score_class(score) if score >= 0 else ""
        sc_display = str(score) if score >= 0 else "—"

        entries_html.append(f"""
        <div class="entry">
          <div class="entry-time">{t}</div>
          <div>
            <div class="entry-summary">{display_summary or 'No summary'}</div>
            <div class="tags">{tags}</div>
          </div>
          <div class="entry-score {sc_class}">{sc_display}</div>
        </div>""")

    avg = int(sum(scores) / len(scores)) if scores else 0

    top = sorted(all_apps.items(), key=lambda x: -x[1])[:6]
    if top:
        apps_html = "<br>".join(f'<span style="color:#fafafa">{a}</span> <span style="color:#52525b">({c}x)</span>' for a, c in top)
    else:
        apps_html = '<span class="empty">No data yet</span>'

    nudge_rows = db.execute(
        "SELECT timestamp, task, message FROM nudges WHERE timestamp LIKE ? ORDER BY timestamp DESC",
        (f"{today}%",)
    ).fetchall()

    if nudge_rows:
        nudge_items = ""
        for ts, task, msg in nudge_rows:
            try:
                t = datetime.fromisoformat(ts).strftime("%H:%M")
            except Exception:
                t = "?"
            nudge_items += f'<li><span class="nudge-time">{t}</span> — {task}</li>'
        nudges_html = f'<ul class="nudge-list">{nudge_items}</ul>'
    else:
        nudges_html = '<span class="empty">No nudges sent today</span>'

    timeline = "\n".join(reversed(entries_html)) if entries_html else '<div class="empty">No activity logged yet. Run monitor.py and check back.</div>'

    html = HTML_TEMPLATE
    if refresh_sec > 0:
        refresh_tag = f'<meta http-equiv="refresh" content="{refresh_sec}">'
        html = html.replace('<meta charset="UTF-8">',
                            f'<meta charset="UTF-8">\n{refresh_tag}')
    html = html.replace("GENERATED_AT", datetime.now().strftime("%A, %B %d %Y — %H:%M"))
    html = html.replace("SCORE_VALUE", str(avg))
    html = html.replace("SCORE_CLASS", score_class(avg))
    html = html.replace("ANALYSIS_COUNT", str(len(rows)))
    html = html.replace("NUDGE_COUNT", str(len(nudge_rows)))
    html = html.replace("TOP_APPS_HTML", apps_html)
    html = html.replace("TIMELINE_HTML", timeline)
    html = html.replace("NUDGES_HTML", nudges_html)

    db.close()
    return html


_server_refresh_sec = 60


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        html = build_dashboard(refresh_sec=_server_refresh_sec)
        if html is None:
            self.send_response(503)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"No activity database found yet. Run the monitor first.")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass


def start_dashboard_server(port=9876, refresh_sec=60):
    """Start the dashboard HTTP server on a daemon thread."""
    global _server_refresh_sec
    _server_refresh_sec = refresh_sec

    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
    except OSError as e:
        print(f"⚠️  Dashboard server failed to start on port {port}: {e}")
        print(f"   Change 'dashboard_port' in ~/.focus-monitor/config.json")
        return None

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread
