"""Scope API server — read-only JSON API for the Scope companion.

Binds to 127.0.0.1 only. Opens the DB with PRAGMA query_only = ON.
All endpoints are GET. No CSRF needed (no mutations).
"""

import json
import os
import re
import sqlite3
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from scope.api import queries


# ── Response helpers ────────────────────────────────────────────────────────

_CORS_ORIGIN = "http://localhost:5173"


def _send_json(handler, data, status=200):
    body = json.dumps(data, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", _CORS_ORIGIN)
    handler.end_headers()
    handler.wfile.write(body)


def _send_error(handler, status, message):
    _send_json(handler, {"error": message}, status=status)


# ── Route patterns ──────────────────────────────────────────────────────────

_ROUTES = [
    (re.compile(r"^/api/health$"), "handle_health"),
    (re.compile(r"^/api/cycles$"), "handle_cycles"),
    (re.compile(r"^/api/cycles/(\d+)/trace$"), "handle_cycle_trace"),
    (re.compile(r"^/api/cycles/(\d+)/corrections$"), "handle_cycle_corrections"),
    (re.compile(r"^/api/cycles/(\d+)$"), "handle_cycle"),
    (re.compile(r"^/api/corrections$"), "handle_corrections"),
    (re.compile(r"^/api/sessions/(\d+)$"), "handle_session"),
    (re.compile(r"^/api/sessions$"), "handle_sessions"),
    (re.compile(r"^/api/stats/correction-rate$"), "handle_stats_correction_rate"),
    (re.compile(r"^/api/stats/confidence-calibration$"), "handle_stats_calibration"),
    (re.compile(r"^/api/stats/per-task-accuracy$"), "handle_stats_task_accuracy"),
    (re.compile(r"^/api/stats/few-shot-impact$"), "handle_stats_few_shot_impact"),
]

# Module-level DB path set by start_scope_server. Each request opens
# its own connection — SQLite connections are not thread-safe and
# ThreadingHTTPServer dispatches to worker threads.
_db_path = None
_screenshot_dir = None  # resolved Path to ~/.focus-monitor/screenshots/


def _open_db():
    db = sqlite3.connect(str(_db_path))
    db.execute("PRAGMA query_only = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    return db


class ScopeHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        # Screenshot serving — /api/screenshot?path=...
        if parsed.path == "/api/screenshot":
            self._serve_screenshot(qs)
            return

        for pattern, method_name in _ROUTES:
            m = pattern.match(parsed.path)
            if m:
                db = _open_db()
                try:
                    method = getattr(self, method_name)
                    method(db, qs, *m.groups())
                finally:
                    db.close()
                return
        _send_error(self, 404, "not found")

    def _serve_screenshot(self, qs):
        """Serve a screenshot PNG from the screenshots directory.

        Validates that the resolved path is under _screenshot_dir to
        prevent path traversal attacks.
        """
        raw_path = (qs.get("path") or [None])[0]
        if not raw_path or not _screenshot_dir:
            _send_error(self, 400, "path parameter required")
            return

        requested = Path(raw_path).resolve()
        screenshots_resolved = _screenshot_dir.resolve()

        # Path traversal guard
        if not str(requested).startswith(str(screenshots_resolved)):
            _send_error(self, 403, "path outside screenshots directory")
            return

        if not requested.exists() or not requested.is_file():
            _send_error(self, 404, "screenshot not found (may have been cleaned up)")
            return

        try:
            data = requested.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", _CORS_ORIGIN)
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            _send_error(self, 500, "failed to read screenshot")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", _CORS_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "3600")
        self.end_headers()

    def log_message(self, format, *args):
        pass

    # ── Handlers ────────────────────────────────────────────────────────

    def handle_health(self, db, qs):
        _send_json(self, {"status": "ok"})

    def handle_cycles(self, db, qs):
        date = (qs.get("date") or [None])[0]
        limit = _int_param(qs, "limit", 50)
        offset = _int_param(qs, "offset", 0)
        data = queries.get_cycles(db, date, limit, offset)
        _send_json(self, data)

    def handle_cycle(self, db, qs, cycle_id):
        data = queries.get_cycle(db, int(cycle_id))
        if data is None:
            _send_error(self, 404, f"cycle {cycle_id} not found")
            return
        _send_json(self, data)

    def handle_cycle_trace(self, db, qs, cycle_id):
        data = queries.get_cycle_trace(db, int(cycle_id))
        if data is None:
            _send_error(self, 404, f"trace for cycle {cycle_id} not found")
            return
        _send_json(self, data)

    def handle_cycle_corrections(self, db, qs, cycle_id):
        data = queries.get_cycle_corrections(db, int(cycle_id))
        _send_json(self, data)

    def handle_corrections(self, db, qs):
        limit = _int_param(qs, "limit", 50)
        offset = _int_param(qs, "offset", 0)
        data = queries.get_corrections(db, limit, offset)
        _send_json(self, data)

    def handle_sessions(self, db, qs):
        date = (qs.get("date") or [None])[0]
        data = queries.get_sessions(db, date)
        _send_json(self, data)

    def handle_session(self, db, qs, session_id):
        data = queries.get_session(db, int(session_id))
        if data is None:
            _send_error(self, 404, f"session {session_id} not found")
            return
        _send_json(self, data)

    def handle_stats_correction_rate(self, db, qs):
        days = _int_param(qs, "days", 30)
        data = queries.get_correction_rate(db, days)
        _send_json(self, data)

    def handle_stats_calibration(self, db, qs):
        data = queries.get_confidence_calibration(db)
        _send_json(self, data)

    def handle_stats_task_accuracy(self, db, qs):
        data = queries.get_per_task_accuracy(db)
        _send_json(self, data)

    def handle_stats_few_shot_impact(self, db, qs):
        cid = _int_param(qs, "correction_id", None)
        if cid is None:
            _send_error(self, 400, "correction_id query param required")
            return
        data = queries.get_few_shot_impact(db, cid)
        if data is None:
            _send_error(self, 404, f"correction {cid} not found")
            return
        _send_json(self, data)


def _int_param(qs, key, default):
    val = (qs.get(key) or [None])[0]
    if val is None:
        return default
    try:
        return max(0, int(val))
    except (ValueError, TypeError):
        return default


def start_scope_server(port, db_path):
    """Start the Scope API server. Blocks until interrupted."""
    global _db_path, _screenshot_dir
    _db_path = db_path
    _screenshot_dir = Path(db_path).parent / "screenshots"

    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), ScopeHandler)
    except OSError as e:
        print(f"⚠️  Scope API server failed to start on port {port}: {e}")
        print(f"   Change 'scope_api_port' in ~/.focus-monitor/config.json")
        return None

    print(f"🔬 Scope API running at http://127.0.0.1:{port}/api/health")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🔬 Scope API server stopped.")
    finally:
        server.server_close()
