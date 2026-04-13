"""Dashboard HTML generation and HTTP server.

Single-screen, Rize-inspired visual layout. Light-theme-first with dark via
`prefers-color-scheme`. All design tokens are CSS custom properties declared
in one place. Templating via `string.Template` (stdlib only — no new deps).
Card-level rendering is split into `render_*` helpers so a future change can
swap individual cards for write-enabled variants without rewriting the
orchestrator.
"""

import html
import json
import os
import re
import secrets
import sqlite3
import string
import threading
import time
import urllib.parse
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from focusmonitor.config import DB_PATH, DISCOVERED_FILE


# ═════════════════════════════════════════════════════════════════════════════
#  Static-file serving (vendored htmx) + CSRF token store.
# ═════════════════════════════════════════════════════════════════════════════

STATIC_DIR = Path(__file__).parent / "static"
STATIC_ALLOWLIST = {"htmx.min.js"}

CSRF_TTL_SECONDS = 3600
_csrf_tokens: "dict[str, float]" = {}  # token → expiry epoch seconds
_csrf_lock = threading.Lock()


def _prune_expired_tokens_locked():
    """Remove expired entries from _csrf_tokens. Caller must hold _csrf_lock."""
    now = time.time()
    dead = [tok for tok, exp in _csrf_tokens.items() if exp <= now]
    for tok in dead:
        _csrf_tokens.pop(tok, None)


def _issue_csrf_token():
    """Generate a fresh single-use CSRF token with a 1-hour TTL."""
    token = secrets.token_urlsafe(32)
    with _csrf_lock:
        _prune_expired_tokens_locked()
        _csrf_tokens[token] = time.time() + CSRF_TTL_SECONDS
    return token


def _consume_csrf_token(token):
    """Return True if `token` is present and not expired; remove it atomically."""
    if not token or not isinstance(token, str):
        return False
    with _csrf_lock:
        _prune_expired_tokens_locked()
        expiry = _csrf_tokens.pop(token, None)
        if expiry is None:
            return False
        if expiry <= time.time():
            return False
    return True


def _validate_csrf_token(token):
    """Return True if `token` is present and not expired; do NOT remove it.

    Used by endpoints whose mutation step might fail in transient ways
    (e.g. the DB lock / OperationalError path in session corrections).
    If we consumed the token up-front, a failed mutation would burn
    the user's only valid token and cascade into a 403 on their next
    click. Validate-only lets a retry use the same token within the
    existing 1-hour TTL.
    """
    if not token or not isinstance(token, str):
        return False
    with _csrf_lock:
        _prune_expired_tokens_locked()
        expiry = _csrf_tokens.get(token)
        if expiry is None:
            return False
        if expiry <= time.time():
            _csrf_tokens.pop(token, None)
            return False
    return True


# ═════════════════════════════════════════════════════════════════════════════
#  Design tokens — one place to change the whole look.
# ═════════════════════════════════════════════════════════════════════════════

STYLE = r"""
:root {
  /* Colors — light palette (default) */
  --color-bg: #f7f8f9;
  --color-surface: #ffffff;
  --color-surface-raised: #ffffff;
  --color-border: #e4e6ea;
  --color-text: #1d2026;
  --color-text-muted: #596172;
  --color-text-subtle: #8b93a4;
  --color-accent: #4a9b8e;
  --color-accent-hover: #3d837a;
  --color-score-good: #4a9b8e;
  --color-score-mid: #d69e2e;
  --color-score-bad: #c85450;
  --color-distraction: #c85450;
  --color-planned: #4a9b8e;

  /* Spacing — 4px base unit, geometric */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-7: 48px;
  --space-8: 64px;

  /* Radii */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;

  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 1px rgba(15, 23, 42, 0.03);
  --shadow-md: 0 4px 8px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04);

  /* Type scale */
  --font-size-xs: 0.72rem;
  --font-size-sm: 0.82rem;
  --font-size-base: 0.95rem;
  --font-size-lg: 1.1rem;
  --font-size-xl: 1.35rem;
  --font-size-2xl: 1.8rem;
  --font-size-5xl: 3.5rem;

  --font-weight-regular: 400;
  --font-weight-medium: 500;
  --font-weight-semibold: 600;

  --font-family-sans: -apple-system, "SF Pro Text", "Inter", system-ui, "Segoe UI", Roboto, sans-serif;
}

@media (prefers-color-scheme: dark) {
  :root {
    --color-bg: #1a1d23;
    --color-surface: #22262e;
    --color-surface-raised: #2a2f38;
    --color-border: #343944;
    --color-text: #e6e8ec;
    --color-text-muted: #9aa3b2;
    --color-text-subtle: #6d7584;
    --color-accent: #5cb5a6;
    --color-accent-hover: #72c4b7;
    --color-score-good: #5cb5a6;
    --color-score-mid: #e6b050;
    --color-score-bad: #e07a75;
    --color-distraction: #e07a75;
    --color-planned: #5cb5a6;
  }
}

* { margin: 0; padding: 0; box-sizing: border-box; }

html, body {
  background: var(--color-bg);
  color: var(--color-text);
  font-family: var(--font-family-sans);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-regular);
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}

.tabular { font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; }

.container {
  max-width: 1100px;
  margin: 0 auto;
  padding: var(--space-6) var(--space-5) var(--space-8);
}

/* ── Header ─────────────────────────────────────────────────────────────── */

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: var(--space-6);
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--color-border);
}

.brand {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
}

.brand-name {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
  letter-spacing: -0.01em;
}

.brand-date {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.range-toggle {
  display: flex;
  gap: var(--space-1);
  font-size: var(--font-size-sm);
}

.range-toggle a {
  color: var(--color-text-muted);
  text-decoration: none;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  transition: background 0.15s ease, color 0.15s ease;
}

.range-toggle a:hover {
  color: var(--color-text);
  background: var(--color-surface);
}

.range-toggle a.current {
  color: var(--color-text);
  background: var(--color-surface);
  font-weight: var(--font-weight-medium);
  box-shadow: var(--shadow-sm);
}

.range-toggle a:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

/* ── Zones ──────────────────────────────────────────────────────────────── */

.zone {
  display: grid;
  gap: var(--space-5);
  margin-bottom: var(--space-5);
}

.zone-hero { grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); }
.zone-primary,
.zone-secondary { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }

@media (max-width: 900px) {
  .zone-hero,
  .zone-primary,
  .zone-secondary { grid-template-columns: minmax(0, 1fr); }
}

/* ── Card ───────────────────────────────────────────────────────────────── */

.card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  box-shadow: var(--shadow-sm);
}

.card-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-muted);
  margin-bottom: var(--space-4);
}

/* ── Score card ─────────────────────────────────────────────────────────── */

.score {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  height: 100%;
}

.score-big {
  font-size: var(--font-size-5xl);
  font-weight: var(--font-weight-semibold);
  line-height: 1;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
  color: var(--color-text);
  margin: var(--space-3) 0 var(--space-2);
}

.score-big.good { color: var(--color-score-good); }
.score-big.mid  { color: var(--color-score-mid); }
.score-big.bad  { color: var(--color-score-bad); }

.score-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-subtle);
}

.score-meta {
  display: flex;
  gap: var(--space-5);
  margin-top: var(--space-4);
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.score-meta strong {
  display: block;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
  font-variant-numeric: tabular-nums;
}

/* ── Timeline card ──────────────────────────────────────────────────────── */

.timeline-card { min-height: 100%; display: flex; flex-direction: column; }

.timeline-svg-wrap {
  flex: 1;
  display: flex;
  align-items: center;
}

.timeline-svg {
  width: 100%;
  height: 140px;
  display: block;
}

.timeline-svg .tl-axis {
  stroke: var(--color-border);
  stroke-width: 1;
}

.timeline-svg .tl-label {
  fill: var(--color-text-subtle);
  font-size: 11px;
  font-family: var(--font-family-sans);
}

/* ── List rows (planned / discovered / apps / nudges) ──────────────────── */

.list { list-style: none; }

.list li {
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--color-border);
  display: grid;
  gap: var(--space-1);
}

.list li:last-child { border-bottom: none; padding-bottom: 0; }
.list li:first-child { padding-top: 0; }

.row-main {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: var(--space-3);
}

.row-name {
  color: var(--color-text);
  font-weight: var(--font-weight-medium);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-meta {
  font-size: var(--font-size-sm);
  color: var(--color-text-subtle);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.bar {
  height: 4px;
  background: var(--color-border);
  border-radius: 2px;
  overflow: hidden;
  margin-top: var(--space-2);
}

.bar-fill {
  height: 100%;
  background: var(--color-planned);
  border-radius: 2px;
}

.row-seen {
  font-size: var(--font-size-xs);
  color: var(--color-text-subtle);
}

.row-signals {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin-top: var(--space-2);
}

.pill {
  display: inline-block;
  padding: 2px 8px;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 100px;
}

.pill.promoted {
  color: var(--color-accent);
  border-color: var(--color-accent);
  background: transparent;
}

.empty {
  font-style: italic;
  color: var(--color-text-subtle);
  font-size: var(--font-size-sm);
  padding: var(--space-4) 0;
  text-align: center;
}

.footer-note {
  font-size: var(--font-size-xs);
  color: var(--color-text-subtle);
  text-align: center;
  margin-top: var(--space-6);
}

/* ── Plan-management buttons & forms ────────────────────────────────────── */

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-3);
  font-size: var(--font-size-xs);
  font-family: var(--font-family-sans);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-muted);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  text-decoration: none;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.btn:hover {
  color: var(--color-text);
  border-color: var(--color-text-subtle);
}

.btn:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

.btn-primary {
  color: #ffffff;
  background: var(--color-accent);
  border-color: var(--color-accent);
}

.btn-primary:hover {
  background: var(--color-accent-hover);
  border-color: var(--color-accent-hover);
  color: #ffffff;
}

.row-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-2);
  opacity: 0.55;
  transition: opacity 0.15s ease;
}

.list li:hover .row-actions,
.list li:focus-within .row-actions { opacity: 1; }

.inline-form {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
}

/* CSS-only toggle for inline edit / add forms. A hidden checkbox holds the
   state; its :checked state reveals the row-edit sibling and hides row-view. */

.edit-toggle {
  position: absolute;
  opacity: 0;
  pointer-events: none;
  width: 1px;
  height: 1px;
}

.row-edit {
  display: none;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3) 0;
}

.edit-toggle:checked + .row-view { display: none; }
.edit-toggle:checked + .row-view + .row-edit { display: flex; }

.row-edit input[type="text"],
.row-edit input:not([type="hidden"]) {
  padding: var(--space-2) var(--space-3);
  font-family: var(--font-family-sans);
  font-size: var(--font-size-sm);
  color: var(--color-text);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}

.row-edit input:focus {
  outline: 2px solid var(--color-accent);
  outline-offset: 1px;
  border-color: var(--color-accent);
}

.form-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-1);
}

.add-task-row {
  border-bottom: none !important;
  padding-top: var(--space-3) !important;
}

.add-task-row .row-view {
  text-align: left;
}

/* ── Session timeline ───────────────────────────────────────────────────── */

.sessions-card {
  padding: 0;
}

.sessions-card .card-title {
  padding: var(--space-5) var(--space-5) 0;
}

.session-list {
  list-style: none;
  margin: var(--space-4) 0 0;
  padding: 0;
}

.session-row {
  padding: var(--space-4) var(--space-5);
  border-top: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.session-row:first-child {
  border-top: none;
}

.session-row.kind-away {
  background: var(--color-bg);
  color: var(--color-text-muted);
}

.session-row.kind-unclear .session-label {
  font-style: italic;
  color: var(--color-text-muted);
}

.session-head {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.session-time {
  font-variant-numeric: tabular-nums;
  font-size: var(--font-size-sm);
  color: var(--color-text-subtle);
  min-width: 9em;
}

.session-label {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-text);
}

.session-meta {
  font-size: var(--font-size-xs);
  color: var(--color-text-subtle);
  margin-left: auto;
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.conf-pair {
  display: inline-flex;
  gap: var(--space-2);
  align-items: center;
}

.conf-badge {
  display: inline-block;
  font-size: var(--font-size-xs);
  padding: 0 var(--space-2);
  border-radius: 100px;
  border: 1px solid var(--color-border);
}

.conf-badge.conf-high { color: var(--color-score-good); border-color: var(--color-score-good); }
.conf-badge.conf-medium { color: var(--color-score-mid); border-color: var(--color-score-mid); }
.conf-badge.conf-low { color: var(--color-text-subtle); }

.session-evidence {
  margin: 0;
  padding: var(--space-2) 0 0 var(--space-4);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.session-evidence summary {
  cursor: pointer;
  color: var(--color-text-subtle);
  list-style: none;
  margin-left: calc(var(--space-4) * -1);
}

.session-evidence summary::-webkit-details-marker { display: none; }

.session-evidence ul {
  list-style: disc;
  padding-left: var(--space-4);
  margin: var(--space-2) 0 0;
}

.session-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-1);
}

.correct-form {
  display: none;
  flex-direction: column;
  gap: var(--space-2);
  margin-top: var(--space-2);
  padding: var(--space-3);
  background: var(--color-bg);
  border-radius: var(--radius-sm);
}

.correct-form select,
.correct-form input[type="text"] {
  padding: var(--space-2) var(--space-3);
  font-family: var(--font-family-sans);
  font-size: var(--font-size-sm);
  color: var(--color-text);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}

.correct-toggle {
  position: absolute;
  opacity: 0;
  pointer-events: none;
  width: 1px;
  height: 1px;
}

.correct-toggle:checked ~ .correct-form { display: flex; }

.verdict-badge {
  font-size: var(--font-size-xs);
  padding: 1px var(--space-1);
  border-radius: var(--radius-sm);
  vertical-align: middle;
}
.verdict-badge.confirmed {
  background: var(--color-score-good);
  color: #fff;
}
.verdict-badge.corrected {
  background: var(--color-accent);
  color: #fff;
}
"""


# ═════════════════════════════════════════════════════════════════════════════
#  Shell template — string.Template with named placeholders.
# ═════════════════════════════════════════════════════════════════════════════

DASHBOARD_TEMPLATE = string.Template("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
$refresh_meta<title>Focus Monitor — Dashboard</title>
<style>$css</style>
<script src="/static/htmx.min.js" defer></script>
<script>
document.addEventListener("csrf-refreshed", function(e) {
  var t = (e.detail || {}).token;
  if (t) document.body.setAttribute("hx-headers", JSON.stringify({"X-CSRF-Token": t}));
});
</script>
</head>
<body hx-headers='{"X-CSRF-Token": "$csrf_token"}'>
<main class="container">
$header
<section class="zone zone-hero" aria-label="Today at a glance">
$score_card
$timeline_card
</section>
<section class="zone zone-sessions" aria-label="Session timeline">
$sessions_card
</section>
<section class="zone zone-primary" aria-label="Plan and discoveries">
$planned_card
$discovered_card
</section>
<section class="zone zone-secondary" aria-label="Apps and nudges">
$apps_card
$nudges_card
</section>
<p class="footer-note">Focus Monitor · local-only · all data stays on this Mac</p>
</main>
</body>
</html>
""")


# ═════════════════════════════════════════════════════════════════════════════
#  Data helpers (preserved from the previous version).
# ═════════════════════════════════════════════════════════════════════════════

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


def _load_discovered_activities():
    """Return activities from discovered_activities.json, newest last_seen first."""
    try:
        data = json.loads(DISCOVERED_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    activities = data.get("activities", []) if isinstance(data, dict) else []
    if not isinstance(activities, list):
        return []
    return sorted(activities, key=lambda a: a.get("last_seen", ""), reverse=True)


def _format_seen(ts):
    if not ts:
        return "?"
    try:
        return datetime.fromisoformat(ts).strftime("%b %d, %H:%M")
    except Exception:
        return ts


# ═════════════════════════════════════════════════════════════════════════════
#  Time range resolution.
# ═════════════════════════════════════════════════════════════════════════════

VALID_RANGES = ("today", "yesterday", "7d")


def resolve_range(range_key):
    """Return (range_key, start_date, end_date_exclusive, label, date_display).

    Unknown values fall back to today. `start_date` and `end_date_exclusive`
    are ISO-date strings (YYYY-MM-DD) suitable for string comparison against
    the `timestamp` column in activity_log.
    """
    if range_key not in VALID_RANGES:
        range_key = "today"

    today = datetime.now().date()
    if range_key == "today":
        start = today
        end = today + timedelta(days=1)
        label = "Today"
        date_display = today.strftime("%A, %B %-d")
    elif range_key == "yesterday":
        start = today - timedelta(days=1)
        end = today
        label = "Yesterday"
        date_display = start.strftime("%A, %B %-d")
    else:  # 7d
        start = today - timedelta(days=6)
        end = today + timedelta(days=1)
        label = "Last 7 days"
        date_display = f"{start.strftime('%b %-d')} – {today.strftime('%b %-d')}"

    return range_key, start.isoformat(), end.isoformat(), label, date_display


# ═════════════════════════════════════════════════════════════════════════════
#  Render helpers — each returns an HTML fragment. No DB access.
# ═════════════════════════════════════════════════════════════════════════════

def render_header(range_key, date_display):
    """Header with brand + date + three-option time-range toggle."""
    links = []
    for key, label in (("today", "Today"), ("yesterday", "Yesterday"), ("7d", "Last 7 days")):
        current_attrs = ' class="current" aria-current="page"' if key == range_key else ''
        links.append(
            f'<a href="/?range={key}"{current_attrs}>{html.escape(label)}</a>'
        )
    toggle = "".join(links)
    return f"""<header class="page-header">
  <div class="brand">
    <span class="brand-name">Focus Monitor</span>
    <span class="brand-date">{html.escape(date_display)}</span>
  </div>
  <nav class="range-toggle" aria-label="Time range">{toggle}</nav>
</header>"""


def render_score_card(score, analysis_count, nudge_count):
    """Big focus score + two small stats (analyses today, nudges)."""
    if score < 0 or analysis_count == 0:
        return """<div class="card score">
  <div class="card-title">Focus score</div>
  <div class="score-big" aria-label="Average focus score">—</div>
  <div class="score-label">no data yet</div>
</div>"""
    bucket = score_class(score)
    return f"""<div class="card score">
  <div class="card-title">Focus score</div>
  <div class="score-big {bucket}" aria-label="Average focus score">{int(score)}</div>
  <div class="score-label">out of 100</div>
  <div class="score-meta">
    <div><strong>{analysis_count}</strong>analyses</div>
    <div><strong>{nudge_count}</strong>nudges</div>
  </div>
</div>"""


def _timeline_svg_empty():
    return """<div class="card timeline-card">
  <div class="card-title">Timeline</div>
  <div class="empty">No activity recorded yet.</div>
</div>"""


def render_timeline(rows, range_key):
    """Inline SVG timeline strip.

    - today/yesterday → 288 five-minute buckets over 24 hours
    - 7d              → one bar per day, 7 days total

    Each `row` is (timestamp_iso, score). Negative scores are skipped (no data).
    """
    rows = [r for r in rows if r[1] is not None and r[1] >= 0]
    if not rows:
        return _timeline_svg_empty()

    VB_W = 1440
    VB_H = 120
    BAR_Y = 20
    BAR_H = 70
    LABEL_Y = 108

    rects = []
    labels = []

    if range_key == "7d":
        day_totals = {}
        day_counts = {}
        for ts, score in rows:
            try:
                d = datetime.fromisoformat(ts).date()
            except Exception:
                continue
            day_totals[d] = day_totals.get(d, 0) + score
            day_counts[d] = day_counts.get(d, 0) + 1

        today = datetime.now().date()
        days = [today - timedelta(days=i) for i in range(6, -1, -1)]
        bar_w = VB_W / 7
        gap = 4
        for i, d in enumerate(days):
            if d not in day_counts:
                continue
            avg = day_totals[d] / day_counts[d]
            cls = score_class(avg)
            x = i * bar_w + gap / 2
            w = bar_w - gap
            rects.append(
                f'<rect x="{x:.1f}" y="{BAR_Y}" width="{w:.1f}" height="{BAR_H}" '
                f'rx="3" fill="var(--color-score-{cls})"/>'
            )
            label_x = i * bar_w + bar_w / 2
            labels.append(
                f'<text class="tl-label" x="{label_x:.1f}" y="{LABEL_Y}" '
                f'text-anchor="middle">{d.strftime("%a")}</text>'
            )
    else:
        bucket_totals = [0.0] * 288  # 24h × 12 five-minute buckets
        bucket_counts = [0] * 288
        for ts, score in rows:
            try:
                dt = datetime.fromisoformat(ts)
            except Exception:
                continue
            bucket = (dt.hour * 60 + dt.minute) // 5
            if 0 <= bucket < 288:
                bucket_totals[bucket] += score
                bucket_counts[bucket] += 1
        bar_w = VB_W / 288  # = 5
        for i in range(288):
            if bucket_counts[i] == 0:
                continue
            avg = bucket_totals[i] / bucket_counts[i]
            cls = score_class(avg)
            x = i * bar_w
            rects.append(
                f'<rect x="{x:.1f}" y="{BAR_Y}" width="{bar_w:.1f}" height="{BAR_H}" '
                f'fill="var(--color-score-{cls})"/>'
            )
        for hour in (0, 6, 12, 18, 24):
            label_x = hour * 60  # minutes
            txt = "0" if hour == 0 else ("24" if hour == 24 else f"{hour}")
            anchor = "start" if hour == 0 else ("end" if hour == 24 else "middle")
            labels.append(
                f'<text class="tl-label" x="{label_x}" y="{LABEL_Y}" '
                f'text-anchor="{anchor}">{txt}:00</text>'
            )

    axis = (
        f'<line class="tl-axis" x1="0" y1="{BAR_Y + BAR_H + 1}" '
        f'x2="{VB_W}" y2="{BAR_Y + BAR_H + 1}"/>'
    )
    svg = (
        f'<svg class="timeline-svg" viewBox="0 0 {VB_W} {VB_H}" '
        f'preserveAspectRatio="none" role="img" '
        f'aria-label="Focus score timeline">'
        f'{"".join(rects)}{axis}{"".join(labels)}'
        f'</svg>'
    )
    return f"""<div class="card timeline-card">
  <div class="card-title">Timeline</div>
  <div class="timeline-svg-wrap">{svg}</div>
</div>"""


def _slug(text):
    """Stable, URL- and DOM-safe slug for use in checkbox ids."""
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "item"


def render_planned_card(planned_tasks, project_counts, csrf_token="", oob=False):
    """Planned Focus card with inline add/edit/delete forms (HTMX-driven).

    The card wraps itself in <div id="planned-card" class="card"> so htmx's
    hx-target="#planned-card" + hx-swap="outerHTML" replaces it in place.
    When `oob=True`, the wrapper gets hx-swap-oob="true" so the card can be
    swapped as an out-of-band update from an endpoint whose primary target is
    a different element (used by the promote endpoint).
    """
    oob_attr = ' hx-swap-oob="true"' if oob else ""
    title = '<div class="card-title">Planned focus</div>'
    csrf = html.escape(csrf_token)

    items = []
    if planned_tasks:
        max_count = max(project_counts.values()) if project_counts else 1
        for task in planned_tasks:
            raw_name = str(task.get("name", "?"))
            name = html.escape(raw_name)
            name_url = urllib.parse.quote(raw_name, safe="")
            slug = f"ptask-edit-{_slug(raw_name)}"
            count = project_counts.get(raw_name.lower(), 0)
            pct = int(round(100 * count / max_count)) if max_count else 0
            fill_width = max(pct, 2) if count else 0
            meta = f"{count} ticks" if count else "not seen"
            signals_csv = html.escape(", ".join(task.get("signals") or []))
            notes_val = html.escape(task.get("notes") or "")
            items.append(
                f'<li class="planned-row">'
                f'<input type="checkbox" id="{slug}" class="edit-toggle" aria-hidden="true">'
                f'<div class="row-view">'
                f'<div class="row-main">'
                f'<span class="row-name">{name}</span>'
                f'<span class="row-meta">{meta}</span>'
                f'</div>'
                f'<div class="bar"><div class="bar-fill" style="width:{fill_width}%"></div></div>'
                f'<div class="row-actions">'
                f'<label for="{slug}" class="btn">edit</label>'
                f'<form class="inline-form" hx-post="/api/planned-tasks/{name_url}/delete" '
                f'hx-target="#planned-card" hx-swap="outerHTML" '
                f'hx-confirm="Delete &quot;{name}&quot;?">'
                f'<input type="hidden" name="csrf" value="{csrf}">'
                f'<button type="submit" class="btn" aria-label="Delete {name}">delete</button>'
                f'</form>'
                f'</div>'
                f'</div>'
                f'<form class="row-edit" hx-post="/api/planned-tasks/{name_url}" '
                f'hx-target="#planned-card" hx-swap="outerHTML">'
                f'<input type="hidden" name="csrf" value="{csrf}">'
                f'<input name="signals" value="{signals_csv}" placeholder="signals, comma, separated" aria-label="Signals for {name}">'
                f'<input name="notes" value="{notes_val}" placeholder="notes" aria-label="Notes for {name}">'
                f'<div class="form-actions">'
                f'<button type="submit" class="btn btn-primary">save</button>'
                f'<label for="{slug}" class="btn">cancel</label>'
                f'</div>'
                f'</form>'
                f'</li>'
            )

    # "+ Add planned task" row — always present, regardless of whether
    # any tasks exist, so the user can always add their first task.
    add_slug = "ptask-add"
    add_row = (
        f'<li class="add-task-row">'
        f'<input type="checkbox" id="{add_slug}" class="edit-toggle" aria-hidden="true">'
        f'<div class="row-view">'
        f'<label for="{add_slug}" class="btn">+ Add planned task</label>'
        f'</div>'
        f'<form class="row-edit" hx-post="/api/planned-tasks" '
        f'hx-target="#planned-card" hx-swap="outerHTML">'
        f'<input type="hidden" name="csrf" value="{csrf}">'
        f'<input name="name" placeholder="task name" required aria-label="New task name">'
        f'<input name="signals" placeholder="signals, comma, separated" aria-label="New task signals">'
        f'<input name="notes" placeholder="notes" aria-label="New task notes">'
        f'<div class="form-actions">'
        f'<button type="submit" class="btn btn-primary">add</button>'
        f'<label for="{add_slug}" class="btn">cancel</label>'
        f'</div>'
        f'</form>'
        f'</li>'
    )

    if items:
        body = f'<ul class="list">{"".join(items)}{add_row}</ul>'
    else:
        body = (
            '<div class="empty">No planned tasks yet.</div>'
            f'<ul class="list">{add_row}</ul>'
        )
    return f'<div id="planned-card" class="card"{oob_attr}>{title}{body}</div>'


def render_discovered_card(activities, csrf_token="", oob=False):
    """Discovered Activities card with promote/hide buttons (HTMX-driven).

    Hidden entries are filtered out. When `oob=True`, the wrapper gets
    hx-swap-oob="true" for out-of-band swap (used after a promote action
    where the primary target is the planned card).
    """
    oob_attr = ' hx-swap-oob="true"' if oob else ""
    title = '<div class="card-title">Discovered activities</div>'
    visible = [a for a in activities if not a.get("hidden")]
    if not visible:
        return (
            f'<div id="discovered-card" class="card"{oob_attr}>{title}'
            f'<div class="empty">No activities discovered yet.</div></div>'
        )

    csrf = html.escape(csrf_token)
    items = []
    for act in visible[:8]:
        raw_name = str(act.get("name", "?"))
        name = html.escape(raw_name)
        name_url = urllib.parse.quote(raw_name, safe="")
        count = int(act.get("count", 0) or 0)
        last_seen = html.escape(_format_seen(act.get("last_seen")))
        promoted = '<span class="pill promoted">promoted</span>' if act.get("promoted") else ""
        signals = act.get("sample_signals", []) or []
        signal_pills = "".join(
            f'<span class="pill">{html.escape(str(s))}</span>' for s in signals[:4]
        )
        signals_row = f'<div class="row-signals">{signal_pills}</div>' if signal_pills else ""

        if act.get("promoted"):
            promote_btn = ""
        else:
            promote_btn = (
                f'<form class="inline-form" hx-post="/api/discoveries/{name_url}/promote" '
                f'hx-target="#discovered-card" hx-swap="outerHTML">'
                f'<input type="hidden" name="csrf" value="{csrf}">'
                f'<button type="submit" class="btn btn-primary" aria-label="Promote {name}">promote</button>'
                f'</form>'
            )
        hide_btn = (
            f'<form class="inline-form" hx-post="/api/discoveries/{name_url}/hide" '
            f'hx-target="#discovered-card" hx-swap="outerHTML">'
            f'<input type="hidden" name="csrf" value="{csrf}">'
            f'<button type="submit" class="btn" aria-label="Hide {name}">hide</button>'
            f'</form>'
        )
        items.append(
            f'<li>'
            f'<div class="row-main">'
            f'<span class="row-name">{name} {promoted}</span>'
            f'<span class="row-meta">seen {count}×</span>'
            f'</div>'
            f'<div class="row-seen">last {last_seen}</div>'
            f'{signals_row}'
            f'<div class="row-actions">{promote_btn}{hide_btn}</div>'
            f'</li>'
        )
    return (
        f'<div id="discovered-card" class="card"{oob_attr}>{title}'
        f'<ul class="list">{"".join(items)}</ul></div>'
    )


def render_apps_card(top_apps):
    """Top Apps card. `top_apps` is a list of (name, count) tuples."""
    title = '<div class="card-title">Top apps</div>'
    if not top_apps:
        return f'<div class="card">{title}<div class="empty">No app data yet.</div></div>'
    max_count = max(c for _, c in top_apps) if top_apps else 1
    items = []
    for name, count in top_apps:
        pct = int(round(100 * count / max_count)) if max_count else 0
        items.append(
            f'<li>'
            f'<div class="row-main">'
            f'<span class="row-name">{html.escape(str(name))}</span>'
            f'<span class="row-meta">{count}×</span>'
            f'</div>'
            f'<div class="bar"><div class="bar-fill" style="width:{pct}%"></div></div>'
            f'</li>'
        )
    return f'<div class="card">{title}<ul class="list">{"".join(items)}</ul></div>'


def render_nudges_card(nudge_rows):
    """Recent Nudges card. `nudge_rows` is [(timestamp_iso, task, message), ...]."""
    title = '<div class="card-title">Recent nudges</div>'
    if not nudge_rows:
        return f'<div class="card">{title}<div class="empty">No nudges sent.</div></div>'
    items = []
    for ts, task, msg in nudge_rows[:8]:
        try:
            t = datetime.fromisoformat(ts).strftime("%H:%M")
        except Exception:
            t = "?"
        items.append(
            f'<li>'
            f'<div class="row-main">'
            f'<span class="row-name">{html.escape(str(task or "—"))}</span>'
            f'<span class="row-meta">{t}</span>'
            f'</div>'
            f'<div class="row-seen">{html.escape(str(msg or ""))}</div>'
            f'</li>'
        )
    return f'<div class="card">{title}<ul class="list">{"".join(items)}</ul></div>'


# ═════════════════════════════════════════════════════════════════════════════
#  Session timeline card: renders the primary session list derived from
#  the `sessions` table (which the aggregator maintains). Each row shows
#  time range, task name (or Unclear / Away), confidence indicators,
#  evidence drawer, and inline correction/confirm controls.
# ═════════════════════════════════════════════════════════════════════════════

_USER_KIND_OPTIONS = (
    ("on_planned_task", "Working on a task"),
    ("thinking_offline", "Thinking / reading offline"),
    ("meeting", "Meeting (no screenshare)"),
    ("break", "Break / lunch"),
    ("other", "Something else"),
)

_USER_KIND_LABELS = dict(_USER_KIND_OPTIONS)


def _fmt_time_range(start_iso, end_iso):
    try:
        s = datetime.fromisoformat(start_iso).strftime("%H:%M")
    except (TypeError, ValueError):
        s = "--:--"
    try:
        e = datetime.fromisoformat(end_iso).strftime("%H:%M")
    except (TypeError, ValueError):
        e = "--:--"
    return f"{s} – {e}"


def _conf_badge(label, level):
    level = level if level in ("low", "medium", "high") else "low"
    return (
        f'<span class="conf-badge conf-{level}" '
        f'title="{html.escape(label)}: {level}">'
        f'{html.escape(label[0].upper())}{html.escape(level[0])}</span>'
    )


def _render_evidence_drawer(evidence):
    if not evidence:
        return ""
    items = []
    for e in evidence:
        if not isinstance(e, dict):
            continue
        sig = html.escape(str(e.get("signal", "")))
        weight = html.escape(str(e.get("weight", "")))
        items.append(f"<li>{sig} <em>({weight})</em></li>")
    if not items:
        return ""
    return (
        '<details class="session-evidence">'
        '<summary>Why we think so</summary>'
        f'<ul>{"".join(items)}</ul>'
        '</details>'
    )


def _render_correction_form(session_id, csrf_token):
    """Inline correction form — emitted as a sibling of the
    session-actions row, NOT nested inside its flex container.

    Uses the standard `<form hx-post>` + `<button type="submit">`
    pattern. The toggle checkbox that reveals this form lives
    upstream in `render_session_row`, a general sibling away via the
    `.correct-toggle:checked ~ .correct-form` CSS selector.
    """
    options = "".join(
        f'<option value="{html.escape(value)}">{html.escape(label)}</option>'
        for value, label in _USER_KIND_OPTIONS
    )
    return (
        f'<form class="correct-form" '
        f'hx-post="/api/sessions/{session_id}/correct" '
        f'hx-target="#session-{session_id}" hx-swap="outerHTML">'
        f'<input type="hidden" name="csrf" value="{html.escape(csrf_token)}">'
        f'<label>Actually I was:'
        f'<select name="user_kind">{options}</select>'
        f'</label>'
        f'<label>Task name (optional):'
        f'<input type="text" name="user_task" placeholder="e.g. auth refactor">'
        f'</label>'
        f'<label>Note (optional):'
        f'<input type="text" name="user_note">'
        f'</label>'
        f'<div class="form-actions">'
        f'<button type="submit" class="btn btn-primary">Save</button>'
        f'</div>'
        f'</form>'
    )


def render_session_row(session, csrf_token):
    """Render ONE session entry for the timeline. Used both by
    `render_session_timeline` and by the correction/confirm endpoint
    re-render path.

    `session` is a dict with the shape produced by
    `focusmonitor.sessions.aggregate()` or a row read back from the
    `sessions` table.
    """
    kind = session.get("kind", "session")
    session_id = session.get("id")
    time_range = _fmt_time_range(session.get("start"), session.get("end"))

    correction = session.get("user_correction")

    if correction:
        verdict = correction.get("verdict", "corrected")
        user_task = correction.get("user_task")
        user_kind = correction.get("user_kind", "other")
        if verdict == "confirmed":
            label = session.get("task") or "Dev work"
            verdict_badge = '<span class="verdict-badge confirmed" title="Confirmed">✓</span>'
        else:
            if user_task:
                label = user_task
            else:
                label = _USER_KIND_LABELS.get(user_kind, user_kind)
            verdict_badge = '<span class="verdict-badge corrected" title="Corrected">✏️</span>'
    elif kind == "away":
        label = "Away"
        verdict_badge = ""
    elif kind == "unclear":
        label = "Unclear"
        verdict_badge = ""
    else:
        task = session.get("task")
        label = task if task else "Dev work"
        verdict_badge = ""

    name_conf = session.get("task_name_confidence", "low")
    boundary_conf = session.get("boundary_confidence", "low")

    meta_parts = []
    cycle_count = int(session.get("cycle_count") or 0)
    if cycle_count:
        meta_parts.append(f"{cycle_count} cycle{'s' if cycle_count != 1 else ''}")
    dip_count = int(session.get("dip_count") or 0)
    if dip_count:
        meta_parts.append(f"{dip_count} dip{'s' if dip_count != 1 else ''}")
    meta = (
        f'<span class="session-meta">{" · ".join(html.escape(p) for p in meta_parts)}</span>'
        if meta_parts else ""
    )

    conf_block = (
        '<span class="conf-pair">'
        f'{_conf_badge("Boundary", boundary_conf)}'
        f'{_conf_badge("Name", name_conf)}'
        '</span>'
    )

    evidence_html = _render_evidence_drawer(session.get("evidence") or [])

    actions_html = ""
    if kind != "away" and session_id is not None and not correction:
        # The correction form lives OUTSIDE the session-actions flex
        # container. Keeping the form and the action buttons in the
        # same flex row caused click events on Save/Confirm to
        # disappear in certain browsers (Safari on macOS in
        # particular — keyboard Enter still submits, but mouse
        # clicks don't fire). Lifting the form to be a sibling of
        # the action row sidesteps this entirely.
        correction_form = _render_correction_form(session_id, csrf_token)
        confirm_btn = ""
        if kind == "session":
            confirm_btn = (
                f'<button type="button" class="btn" '
                f'hx-post="/api/sessions/{session_id}/confirm" '
                f'hx-target="#session-{session_id}" hx-swap="outerHTML" '
                f'hx-vals=\'{{"csrf": "{html.escape(csrf_token)}"}}\'>'
                f'✓ Confirm</button>'
            )
        # Bare toggle + label for the correction drawer (the form is
        # a sibling below via CSS general-sibling selector).
        correct_toggle_label = (
            f'<label for="corr-toggle-{session_id}" class="btn">'
            f'✏️ Correct</label>'
        )
        actions_html = (
            f'<input type="checkbox" id="corr-toggle-{session_id}" '
            f'class="correct-toggle">'
            f'<div class="session-actions">{confirm_btn}{correct_toggle_label}</div>'
            f'{correction_form}'
        )

    row_id = (
        f' id="session-{session_id}"' if session_id is not None else ""
    )

    return (
        f'<li class="session-row kind-{kind}"{row_id}>'
        f'<div class="session-head">'
        f'<span class="session-time">{html.escape(time_range)}</span>'
        f'<span class="session-label">{html.escape(label)}</span>'
        f'{verdict_badge}'
        f'{conf_block}'
        f'{meta}'
        f'</div>'
        f'{evidence_html}'
        f'{actions_html}'
        f'</li>'
    )


def render_session_timeline(sessions, csrf_token=""):
    """Render the entire session timeline card. Returns a full card
    fragment suitable for slotting into the dashboard template."""
    title = '<div class="card-title">Today\'s sessions</div>'
    if not sessions:
        return (
            '<div class="card sessions-card">'
            f'{title}'
            '<div class="empty">No sessions yet today. '
            'Run the monitor for a while and they will appear here.</div>'
            '</div>'
        )
    items = "".join(render_session_row(s, csrf_token) for s in sessions)
    return (
        '<div class="card sessions-card">'
        f'{title}'
        f'<ul class="session-list">{items}</ul>'
        '</div>'
    )


def _load_latest_corrections(db, session_ids):
    """Return a dict mapping session_id → latest correction dict.

    Only the most recent correction (by ``created_at``) per session is
    returned. Sessions without corrections are absent from the dict.
    """
    if not session_ids:
        return {}
    placeholders = ",".join("?" for _ in session_ids)
    rows = db.execute(
        "SELECT c.entry_id, c.user_verdict, c.user_task, c.user_kind "
        "FROM corrections c "
        "INNER JOIN ("
        "  SELECT entry_id, MAX(created_at) AS latest "
        "  FROM corrections "
        f"  WHERE entry_kind='session' AND entry_id IN ({placeholders}) "
        "  GROUP BY entry_id"
        ") sub ON c.entry_id = sub.entry_id AND c.created_at = sub.latest "
        "WHERE c.entry_kind='session'",
        list(session_ids),
    ).fetchall()
    result = {}
    for entry_id, verdict, user_task, user_kind in rows:
        result[entry_id] = {
            "verdict": verdict,
            "user_task": user_task,
            "user_kind": user_kind,
        }
    return result


def _load_sessions_for_range(start_iso, end_iso):
    """Read session rows from the DB and return dicts ready to render."""
    if not DB_PATH.exists():
        return []
    db = sqlite3.connect(str(DB_PATH))
    try:
        db.execute("PRAGMA busy_timeout = 10000")
        rows = db.execute(
            "SELECT id, start, end, task, task_name_confidence, "
            "boundary_confidence, cycle_count, dip_count, evidence_json, "
            "kind FROM sessions "
            "WHERE start >= ? AND start < ? ORDER BY start DESC",
            (start_iso, end_iso),
        ).fetchall()
        session_ids = [r[0] for r in rows]
        corrections = _load_latest_corrections(db, session_ids)
    finally:
        db.close()
    results = []
    for row in rows:
        (
            row_id, start, end, task, name_conf, bound_conf,
            cycle_count, dip_count, evidence_json, kind,
        ) = row
        try:
            evidence = json.loads(evidence_json) if evidence_json else []
        except (json.JSONDecodeError, TypeError):
            evidence = []
        sess = {
            "id": row_id,
            "start": start,
            "end": end,
            "task": task,
            "task_name_confidence": name_conf,
            "boundary_confidence": bound_conf,
            "cycle_count": cycle_count,
            "dip_count": dip_count,
            "evidence": evidence,
            "kind": kind,
        }
        if row_id in corrections:
            sess["user_correction"] = corrections[row_id]
        results.append(sess)
    return results


def _load_session_by_id(session_id):
    """Fetch a single session row, or return None if missing."""
    if not DB_PATH.exists():
        return None
    db = sqlite3.connect(str(DB_PATH))
    try:
        db.execute("PRAGMA busy_timeout = 10000")
        row = db.execute(
            "SELECT id, start, end, task, task_name_confidence, "
            "boundary_confidence, cycle_count, dip_count, evidence_json, "
            "kind FROM sessions WHERE id=?",
            (session_id,),
        ).fetchone()
    finally:
        db.close()
    if row is None:
        return None
    (
        row_id, start, end, task, name_conf, bound_conf,
        cycle_count, dip_count, evidence_json, kind,
    ) = row
    try:
        evidence = json.loads(evidence_json) if evidence_json else []
    except (json.JSONDecodeError, TypeError):
        evidence = []
    return {
        "id": row_id,
        "start": start,
        "end": end,
        "task": task,
        "task_name_confidence": name_conf,
        "boundary_confidence": bound_conf,
        "cycle_count": cycle_count,
        "dip_count": dip_count,
        "evidence": evidence,
        "kind": kind,
    }


# ═════════════════════════════════════════════════════════════════════════════
#  Planned task loader (for the planned card). Local import to avoid
#  circular dependency with focusmonitor.tasks during normal imports.
# ═════════════════════════════════════════════════════════════════════════════

def _load_planned_tasks():
    try:
        from focusmonitor.tasks import load_planned_tasks
        return load_planned_tasks()
    except Exception:
        return []


# ═════════════════════════════════════════════════════════════════════════════
#  Orchestrator.
# ═════════════════════════════════════════════════════════════════════════════

def build_dashboard(refresh_sec=0, range_key="today", view="default"):
    """Build dashboard HTML and return it as a string.

    Returns None if the database file does not exist yet (first-run state).

    `view="legacy"` renders a diagnostic variant that omits the
    session timeline zone entirely (the sessions card becomes an
    empty placeholder), so the developer can inspect the raw
    per-cycle activity_log view without aggregation side-effects.
    """
    if not DB_PATH.exists():
        return None

    range_key, start_iso, end_iso, _label, date_display = resolve_range(range_key)

    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA busy_timeout = 10000")

    rows = db.execute(
        "SELECT timestamp, summary, raw_response, apps_used, project_detected "
        "FROM activity_log WHERE timestamp >= ? AND timestamp < ? "
        "ORDER BY timestamp ASC",
        (start_iso, end_iso),
    ).fetchall()

    nudge_rows = db.execute(
        "SELECT timestamp, task, message FROM nudges "
        "WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp DESC",
        (start_iso, end_iso),
    ).fetchall()

    db.close()

    # Derive stats from rows. Each row is parsed via the LLM-output helper to
    # extract a focus score and a list of projects.
    scores = []
    app_counts = {}
    project_counts = {}  # lowercased name → tick count
    timeline_pts = []    # [(timestamp_iso, score_or_None), ...]

    for ts, _summary, raw, apps_json, projects_json in rows:
        score = -1
        parsed = _try_parse_json(raw)
        if parsed:
            score = parsed.get("focus_score", -1)

        if isinstance(score, (int, float)) and score >= 0:
            scores.append(int(score))
            timeline_pts.append((ts, int(score)))
        else:
            timeline_pts.append((ts, None))

        try:
            for app in json.loads(apps_json or "[]"):
                app_counts[app] = app_counts.get(app, 0) + 1
        except Exception:
            pass

        try:
            projects = json.loads(projects_json or "[]")
            for p in projects:
                if isinstance(p, str) and p:
                    key = p.strip().lower()
                    project_counts[key] = project_counts.get(key, 0) + 1
        except Exception:
            pass

    avg_score = int(sum(scores) / len(scores)) if scores else -1
    top_apps = sorted(app_counts.items(), key=lambda x: -x[1])[:6]

    planned_tasks = _load_planned_tasks()
    activities = _load_discovered_activities()

    refresh_meta = (
        f'<meta http-equiv="refresh" content="{int(refresh_sec)}">\n'
        if refresh_sec and refresh_sec > 0 else ""
    )

    csrf_token = _issue_csrf_token()

    if view == "legacy":
        sessions_card = (
            '<div class="card sessions-card">'
            '<div class="card-title">Sessions (legacy view — disabled)</div>'
            '<div class="empty">Legacy view: session aggregation is '
            'hidden. Use the default view to see the session timeline.</div>'
            '</div>'
        )
    else:
        sessions = _load_sessions_for_range(start_iso, end_iso)
        sessions_card = render_session_timeline(sessions, csrf_token)

    subs = {
        "refresh_meta": refresh_meta,
        "css": STYLE,
        "csrf_token": csrf_token,
        "header": render_header(range_key, date_display),
        "score_card": render_score_card(avg_score, len(rows), len(nudge_rows)),
        "timeline_card": render_timeline(timeline_pts, range_key),
        "sessions_card": sessions_card,
        "planned_card": render_planned_card(planned_tasks, project_counts, csrf_token),
        "discovered_card": render_discovered_card(activities, csrf_token),
        "apps_card": render_apps_card(top_apps),
        "nudges_card": render_nudges_card(nudge_rows),
    }
    return DASHBOARD_TEMPLATE.substitute(subs)


# ═════════════════════════════════════════════════════════════════════════════
#  Mutation choke-point (_mutate) + write-endpoint helpers.
#  Every POST handler MUST call _mutate() as its first operation. The helper
#  validates Host, Origin, the CSRF token, and required form fields. On any
#  failure it writes an error response and returns None; the caller returns
#  immediately without touching any files.
# ═════════════════════════════════════════════════════════════════════════════

def _server_origin_candidates(handler):
    """Return the set of acceptable Host / Origin values for this server."""
    port = handler.server.server_address[1]
    return {
        f"localhost:{port}",
        f"127.0.0.1:{port}",
    }


def _send_error(handler, code, body=""):
    """Send a plain-text error response."""
    handler.send_response(code)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body.encode("utf-8"))))
    handler.end_headers()
    if body:
        handler.wfile.write(body.encode("utf-8"))


def _send_html_fragment(handler, fragment, csrf_token=None):
    """Send an HTML fragment as a 200 response (for htmx swaps).

    When *csrf_token* is given, an ``HX-Trigger`` response header is
    emitted so the client-side listener can update the page-level
    ``hx-headers`` attribute with the fresh token.
    """
    body = fragment.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    if csrf_token:
        import json as _json
        handler.send_header(
            "HX-Trigger",
            _json.dumps({"csrf-refreshed": {"token": csrf_token}}),
        )
    handler.end_headers()
    handler.wfile.write(body)


def _mutate(handler, required_fields=(), consume_csrf=True):
    """Validate a mutation request and return a form-fields dict on success.

    On any failure, writes an error response to `handler` and returns None.
    The caller MUST check for None and return immediately on failure.

    When `consume_csrf=False`, the CSRF token is validated but NOT removed
    from the store. Use this for endpoints whose mutation step is
    potentially flaky (e.g. can return a transient DB error): the token
    stays valid so the user can retry without reloading the whole page.
    The 1-hour TTL still bounds the token's lifetime. The caller is
    responsible for eventually consuming the token on the success path
    (by calling `_consume_csrf_token` and re-issuing a fresh one for
    the re-rendered fragment).
    """
    valid_hosts = _server_origin_candidates(handler)

    host = (handler.headers.get("Host") or "").strip()
    if host not in valid_hosts:
        _send_error(handler, 403, "forbidden: host mismatch")
        return None

    origin = handler.headers.get("Origin")
    if origin:
        try:
            parsed = urllib.parse.urlsplit(origin)
        except ValueError:
            _send_error(handler, 403, "forbidden: origin unparseable")
            return None
        origin_host = parsed.netloc
        if origin_host not in valid_hosts:
            _send_error(handler, 403, "forbidden: origin mismatch")
            return None

    try:
        length = int(handler.headers.get("Content-Length") or "0")
    except (TypeError, ValueError):
        _send_error(handler, 400, "bad request: invalid Content-Length")
        return None

    body_bytes = handler.rfile.read(length) if length > 0 else b""
    try:
        body_text = body_bytes.decode("utf-8")
    except UnicodeDecodeError:
        _send_error(handler, 400, "bad request: body is not utf-8")
        return None

    parsed_form = urllib.parse.parse_qs(body_text, keep_blank_values=True)
    fields = {k: (v[0] if v else "") for k, v in parsed_form.items()}

    # CSRF token may arrive as a form field OR as an X-CSRF-Token header (htmx).
    # Prefer header when present.
    header_token = handler.headers.get("X-CSRF-Token") or ""
    token = header_token or fields.get("csrf") or ""
    if consume_csrf:
        if not _consume_csrf_token(token):
            _send_error(handler, 403, "forbidden: invalid or missing csrf token")
            return None
    else:
        if not _validate_csrf_token(token):
            _send_error(handler, 403, "forbidden: invalid or missing csrf token")
            return None

    for req in required_fields:
        if not fields.get(req, "").strip():
            _send_error(handler, 400, f"bad request: missing required field '{req}'")
            return None

    return fields


# ═════════════════════════════════════════════════════════════════════════════
#  Post-mutation re-render helpers.
#  These re-run the read paths used by build_dashboard() to produce fresh
#  card fragments for htmx-swap responses.
# ═════════════════════════════════════════════════════════════════════════════

def _rerender_planned_card(csrf_token, oob=False):
    """Rebuild the Planned Focus card fragment from current on-disk state.

    Re-queries today's activity_log to compute per-task tick counts so the bar
    widths are accurate after a mutation.
    """
    planned_tasks = _load_planned_tasks()
    project_counts = {}
    if DB_PATH.exists():
        _, start_iso, end_iso, _label, _disp = resolve_range("today")
        db = sqlite3.connect(str(DB_PATH))
        try:
            db.execute("PRAGMA busy_timeout = 10000")
            rows = db.execute(
                "SELECT project_detected FROM activity_log "
                "WHERE timestamp >= ? AND timestamp < ?",
                (start_iso, end_iso),
            ).fetchall()
        finally:
            db.close()
        for (projects_json,) in rows:
            try:
                for p in json.loads(projects_json or "[]"):
                    if isinstance(p, str) and p:
                        key = p.strip().lower()
                        project_counts[key] = project_counts.get(key, 0) + 1
            except Exception:
                pass
    return render_planned_card(planned_tasks, project_counts, csrf_token, oob=oob)


def _rerender_discovered_card(csrf_token, oob=False):
    return render_discovered_card(_load_discovered_activities(), csrf_token, oob=oob)


# ═════════════════════════════════════════════════════════════════════════════
#  HTTP handler + server.
# ═════════════════════════════════════════════════════════════════════════════

_server_refresh_sec = 60


_STATIC_PATH_RE = re.compile(r"^/static/([A-Za-z0-9._-]+)$")

# POST route patterns. Order matters: the delete route MUST come before the
# generic update route, otherwise "/api/planned-tasks/foo/delete" would match
# the update pattern with name="foo/delete".
_POST_ROUTES = [
    (re.compile(r"^/api/planned-tasks$"), "_handle_create_task"),
    (re.compile(r"^/api/planned-tasks/([^/]+)/delete$"), "_handle_delete_task"),
    (re.compile(r"^/api/planned-tasks/([^/]+)$"), "_handle_update_task"),
    (re.compile(r"^/api/discoveries/([^/]+)/promote$"), "_handle_promote_discovery"),
    (re.compile(r"^/api/discoveries/([^/]+)/hide$"), "_handle_hide_discovery"),
    (re.compile(r"^/api/sessions/([0-9]+)/correct$"), "_handle_correct_session"),
    (re.compile(r"^/api/sessions/([0-9]+)/confirm$"), "_handle_confirm_session"),
]


_VALID_USER_KINDS_SET = frozenset({
    "on_planned_task", "thinking_offline", "meeting", "break", "other",
})


def _static_content_type(filename):
    if filename.endswith(".js"):
        return "application/javascript; charset=utf-8"
    if filename.endswith(".css"):
        return "text/css; charset=utf-8"
    return "application/octet-stream"


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)

        # /static/<filename> — allowlisted static files only.
        static_match = _STATIC_PATH_RE.match(parsed.path)
        if static_match:
            filename = static_match.group(1)
            if filename not in STATIC_ALLOWLIST:
                _send_error(self, 404, "not found")
                return
            file_path = STATIC_DIR / filename
            try:
                data = file_path.read_bytes()
            except (FileNotFoundError, OSError):
                _send_error(self, 404, "not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", _static_content_type(filename))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)
            return

        # Only "/" is served as the dashboard page.
        if parsed.path not in ("/", ""):
            _send_error(self, 404, "not found")
            return

        qs = urllib.parse.parse_qs(parsed.query)
        range_key = (qs.get("range") or ["today"])[0]
        if range_key not in VALID_RANGES:
            range_key = "today"
        view = (qs.get("view") or ["default"])[0]
        if view not in ("default", "legacy"):
            view = "default"

        page = build_dashboard(
            refresh_sec=_server_refresh_sec, range_key=range_key, view=view,
        )
        if page is None:
            self.send_response(503)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"No activity database found yet. Run the monitor first.")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page.encode("utf-8"))

    def do_POST(self):
        parsed = urllib.parse.urlsplit(self.path)
        for pattern, method_name in _POST_ROUTES:
            m = pattern.match(parsed.path)
            if m:
                handler_method = getattr(self, method_name)
                handler_method(*m.groups())
                return
        _send_error(self, 404, "not found")

    # ── Mutation handlers — each calls _mutate() first, no exceptions. ──

    def _handle_create_task(self):
        from focusmonitor.tasks import add_planned_task
        fields = _mutate(self, required_fields=("name",))
        if fields is None:
            return
        name = fields["name"].strip()
        signals = [s.strip() for s in (fields.get("signals") or "").split(",") if s.strip()]
        notes = fields.get("notes", "").strip()
        if not add_planned_task(name, signals=signals, notes=notes):
            _send_error(self, 409, "conflict: task with that name already exists")
            return
        fresh_csrf = _issue_csrf_token()
        _send_html_fragment(self, _rerender_planned_card(fresh_csrf), csrf_token=fresh_csrf)

    def _handle_update_task(self, name_enc):
        from focusmonitor.tasks import update_planned_task
        fields = _mutate(self, required_fields=())
        if fields is None:
            return
        name = urllib.parse.unquote(name_enc)
        signals_raw = fields.get("signals")
        notes_raw = fields.get("notes")
        signals = (
            [s.strip() for s in signals_raw.split(",") if s.strip()]
            if signals_raw is not None else None
        )
        notes = notes_raw if notes_raw is not None else None
        if not update_planned_task(name, signals=signals, notes=notes):
            _send_error(self, 404, "not found: no task with that name")
            return
        fresh_csrf = _issue_csrf_token()
        _send_html_fragment(self, _rerender_planned_card(fresh_csrf), csrf_token=fresh_csrf)

    def _handle_delete_task(self, name_enc):
        from focusmonitor.tasks import delete_planned_task
        fields = _mutate(self, required_fields=())
        if fields is None:
            return
        name = urllib.parse.unquote(name_enc)
        if not delete_planned_task(name):
            _send_error(self, 404, "not found: no task with that name")
            return
        fresh_csrf = _issue_csrf_token()
        _send_html_fragment(self, _rerender_planned_card(fresh_csrf), csrf_token=fresh_csrf)

    def _handle_promote_discovery(self, name_enc):
        from focusmonitor.tasks import promote_discovered
        fields = _mutate(self, required_fields=())
        if fields is None:
            return
        name = urllib.parse.unquote(name_enc)
        if not promote_discovered(name):
            _send_error(
                self, 409,
                "conflict: discovery missing or planned task already exists",
            )
            return
        fresh_csrf = _issue_csrf_token()
        # Primary target is the Discovered card (where the promote button lived);
        # the Planned card comes back as an out-of-band swap.
        discovered_html = _rerender_discovered_card(fresh_csrf)
        planned_html = _rerender_planned_card(fresh_csrf, oob=True)
        _send_html_fragment(self, discovered_html + planned_html, csrf_token=fresh_csrf)

    def _handle_hide_discovery(self, name_enc):
        from focusmonitor.tasks import hide_discovered
        fields = _mutate(self, required_fields=())
        if fields is None:
            return
        name = urllib.parse.unquote(name_enc)
        if not hide_discovered(name):
            _send_error(self, 404, "not found: no discovered activity with that name")
            return
        fresh_csrf = _issue_csrf_token()
        _send_html_fragment(self, _rerender_discovered_card(fresh_csrf), csrf_token=fresh_csrf)

    def _handle_correct_session(self, session_id_str):
        import sys as _sys
        # Diagnostic: surface incoming fields to stderr so the
        # monitor's console shows exactly what the browser posted
        # when Save fails. Temporary until the 400/403 cascade is
        # pinned down.
        _raw_csrf_header = self.headers.get("X-CSRF-Token") or "<none>"
        _content_length = self.headers.get("Content-Length") or "<none>"
        print(
            f"[correct session={session_id_str}] "
            f"content-length={_content_length} "
            f"x-csrf-token={_raw_csrf_header[:10]}...",
            file=_sys.stderr,
        )
        fields = _mutate(self, required_fields=("user_kind",), consume_csrf=False)
        if fields is None:
            print(
                f"[correct session={session_id_str}] "
                f"_mutate returned None (sent 4xx)",
                file=_sys.stderr,
            )
            return
        print(
            f"[correct session={session_id_str}] fields keys="
            f"{sorted(fields.keys())} "
            f"user_kind={fields.get('user_kind')!r} "
            f"user_task={fields.get('user_task')!r}",
            file=_sys.stderr,
        )
        self._apply_session_verdict(session_id_str, fields, verdict="corrected")

    def _handle_confirm_session(self, session_id_str):
        import sys as _sys
        print(
            f"[confirm session={session_id_str}] "
            f"content-length={self.headers.get('Content-Length') or '<none>'}",
            file=_sys.stderr,
        )
        fields = _mutate(self, required_fields=(), consume_csrf=False)
        if fields is None:
            print(
                f"[confirm session={session_id_str}] _mutate returned None",
                file=_sys.stderr,
            )
            return
        # Confirmations don't ship a user_kind on the wire — default
        # to on_planned_task. The correction-loop schema requires a
        # valid user_kind either way.
        fields.setdefault("user_kind", "on_planned_task")
        self._apply_session_verdict(session_id_str, fields, verdict="confirmed")

    def _apply_session_verdict(self, session_id_str, fields, verdict):
        from focusmonitor.corrections import CorrectionError, record_correction

        try:
            session_id = int(session_id_str)
        except ValueError:
            _send_error(self, 400, "bad request: session id is not an integer")
            return

        user_kind = (fields.get("user_kind") or "").strip()
        if user_kind not in _VALID_USER_KINDS_SET:
            _send_error(self, 400, "bad request: invalid user_kind")
            return

        session = _load_session_by_id(session_id)
        if session is None:
            _send_error(self, 404, "not found: no session with that id")
            return

        user_task = (fields.get("user_task") or "").strip() or None
        user_note = (fields.get("user_note") or "").strip() or None

        model_state = {
            "range_start": session["start"],
            "range_end": session["end"],
            "task": session.get("task"),
            "evidence": session.get("evidence") or [],
            "boundary_confidence": session.get("boundary_confidence", "low"),
            "name_confidence": session.get("task_name_confidence", "low"),
            "signals": {},
        }
        user_state = {
            "verdict": verdict,
            "user_kind": user_kind,
            "user_task": user_task,
            "user_note": user_note,
        }

        # Retry OperationalError a few times with short sleeps. WAL
        # mode + busy_timeout already handle normal contention; this
        # is a belt-and-suspenders for the rare case where the
        # monitor's long-lived connection is in a pre-WAL state and
        # locks briefly. Total max delay: ~1.5s.
        last_error = None
        for attempt in range(3):
            db = sqlite3.connect(str(DB_PATH))
            try:
                db.execute("PRAGMA busy_timeout = 10000")
                try:
                    record_correction(
                        db, "session", session_id, model_state, user_state,
                    )
                    last_error = None
                    break
                except CorrectionError as e:
                    _send_error(self, 400, f"bad request: {e}")
                    return
                except sqlite3.OperationalError as e:
                    last_error = e
            finally:
                db.close()
            if attempt < 2:
                time.sleep(0.5)

        if last_error is not None:
            # Token was NOT consumed (we used validate-only mode), so
            # the user can retry with the same token. Surface the
            # underlying error so the cause is visible in the browser
            # console instead of a generic "Service Unavailable".
            _send_error(
                self, 503,
                f"service unavailable: {last_error}. "
                "Restart the monitor process if this persists.",
            )
            return

        # Success: now consume the CSRF token and re-render.
        header_token = self.headers.get("X-CSRF-Token") or ""
        form_token = fields.get("csrf") or ""
        _consume_csrf_token(header_token or form_token)

        fresh_csrf = _issue_csrf_token()
        # Attach the correction to the session dict so the re-rendered
        # row reflects the user's correction/confirmation immediately.
        session["user_correction"] = {
            "verdict": verdict,
            "user_task": user_task,
            "user_kind": user_kind,
        }
        _send_html_fragment(self, render_session_row(session, fresh_csrf), csrf_token=fresh_csrf)

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
