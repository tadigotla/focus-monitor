"""Tests for the plan-management write endpoints, CSRF, and data-layer helpers.

Coverage:
  - `_write_json_atomic` — happy path + failure cleanup
  - Data-layer helpers: add/update/delete planned tasks; hide/promote
    discoveries
  - `_issue_csrf_token` / `_consume_csrf_token` — lifecycle, replay, expiry
  - `_mutate` choke-point: Host / Origin / CSRF / required field validation
  - End-to-end via a real `ThreadingHTTPServer` on an ephemeral port: the
    full /static, GET /, POST pipeline with XSS canary.

End-to-end HTTP tests bind to `127.0.0.1` on an ephemeral port and speak
http via `http.client.HTTPConnection`, which goes through the allowed
loopback hosts under `pytest-socket`.
"""

from __future__ import annotations

import http.client
import io
import json
import re
import sqlite3
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from focusmonitor import config, dashboard as dash, tasks as t_mod
from focusmonitor.db import init_db


# ── _write_json_atomic ───────────────────────────────────────────────────────

class TestWriteJsonAtomic:

    def test_creates_file_with_content(self, tmp_path):
        target = tmp_path / "atomic.json"
        t_mod._write_json_atomic(target, {"a": 1})
        assert target.exists()
        assert json.loads(target.read_text()) == {"a": 1}

    def test_failure_leaves_original_untouched_and_no_tmp_file(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / "atomic.json"
        target.write_text(json.dumps({"original": True}))

        def boom(*a, **kw):
            raise RuntimeError("simulated")

        monkeypatch.setattr(json, "dumps", boom)
        with pytest.raises(RuntimeError):
            t_mod._write_json_atomic(target, {"new": True})

        assert json.loads(target.read_text()) == {"original": True}
        assert list(tmp_path.glob("atomic.json.tmp")) == []


# ── hide/promote discoveries ─────────────────────────────────────────────────

class TestHidePromoteDiscoveries:

    def _seed_discoveries(self, entries):
        config.DISCOVERED_FILE.write_text(json.dumps({"activities": entries}))

    def test_hide_existing_entry(self, tmp_home):
        self._seed_discoveries([{
            "name": "Sanskrit Tool", "first_seen": "2026-04-10T09:00:00",
            "last_seen": "2026-04-12T10:00:00", "count": 5,
            "sample_signals": [], "promoted": False,
        }])
        assert t_mod.hide_discovered("Sanskrit Tool") is True
        data = json.loads(config.DISCOVERED_FILE.read_text())
        assert data["activities"][0].get("hidden") is True

    def test_hide_case_insensitive(self, tmp_home):
        self._seed_discoveries([{
            "name": "Other Thing", "first_seen": "2026-04-10T09:00:00",
            "last_seen": "2026-04-12T10:00:00", "count": 2,
            "sample_signals": [], "promoted": False,
        }])
        assert t_mod.hide_discovered("other thing") is True

    def test_hide_unknown_rejected(self, tmp_home):
        self._seed_discoveries([])
        assert t_mod.hide_discovered("Nothing") is False

    def test_promote_creates_planned_task(self, tmp_home):
        self._seed_discoveries([{
            "name": "Sanskrit Tool", "first_seen": "2026-04-10T09:00:00",
            "last_seen": "2026-04-12T10:00:00", "count": 5,
            "sample_signals": ["devanagari", "panini"], "promoted": False,
        }])
        assert t_mod.promote_discovered("Sanskrit Tool") is True
        tasks_raw = json.loads(config.TASKS_JSON_FILE.read_text())
        assert len(tasks_raw) == 1
        assert tasks_raw[0]["name"] == "Sanskrit Tool"
        assert tasks_raw[0]["signals"] == ["devanagari", "panini"]
        disc = json.loads(config.DISCOVERED_FILE.read_text())
        assert disc["activities"][0].get("promoted") is True

    def test_promote_duplicate_rejected(self, tmp_home):
        self._seed_discoveries([{
            "name": "X", "first_seen": "2026-04-10T09:00:00",
            "last_seen": "2026-04-10T09:00:00", "count": 1,
            "sample_signals": [], "promoted": False,
        }])
        t_mod.promote_discovered("X")
        assert t_mod.promote_discovered("X") is False

    def test_promote_unknown_rejected(self, tmp_home):
        self._seed_discoveries([])
        assert t_mod.promote_discovered("Nothing") is False


# ── CSRF token lifecycle ─────────────────────────────────────────────────────

@pytest.fixture
def clean_csrf_store():
    """Clear the global CSRF store before and after each test."""
    with dash._csrf_lock:
        dash._csrf_tokens.clear()
    yield
    with dash._csrf_lock:
        dash._csrf_tokens.clear()


class TestCsrfLifecycle:

    def test_issued_tokens_are_distinct(self, clean_csrf_store):
        t1 = dash._issue_csrf_token()
        t2 = dash._issue_csrf_token()
        assert t1 != t2
        assert t1 in dash._csrf_tokens
        assert t2 in dash._csrf_tokens

    def test_consume_valid_token_returns_true_and_removes(self, clean_csrf_store):
        tok = dash._issue_csrf_token()
        assert dash._consume_csrf_token(tok) is True
        assert tok not in dash._csrf_tokens

    def test_replay_returns_false(self, clean_csrf_store):
        tok = dash._issue_csrf_token()
        dash._consume_csrf_token(tok)
        assert dash._consume_csrf_token(tok) is False

    def test_unknown_token_returns_false(self, clean_csrf_store):
        assert dash._consume_csrf_token("totally-fake") is False

    def test_empty_or_none_token_returns_false(self, clean_csrf_store):
        assert dash._consume_csrf_token("") is False
        assert dash._consume_csrf_token(None) is False

    def test_expired_token_rejected(self, clean_csrf_store):
        tok = dash._issue_csrf_token()
        with dash._csrf_lock:
            dash._csrf_tokens[tok] = time.time() - 1
        assert dash._consume_csrf_token(tok) is False


# ── _mutate choke-point with a fake handler ─────────────────────────────────

class _FakeServer:
    def __init__(self, port=9876):
        self.server_address = ("127.0.0.1", port)


class _FakeHandler:
    """Stand-in for BaseHTTPRequestHandler that captures responses."""
    def __init__(self, headers, body, port=9876):
        self.headers = headers
        self.rfile = io.BytesIO(body)
        self.server = _FakeServer(port)
        self.response_code = None
        self.response_headers = []
        self.response_body = b""

    def send_response(self, code):
        self.response_code = code

    def send_header(self, k, v):
        self.response_headers.append((k, v))

    def end_headers(self):
        pass

    @property
    def wfile(self):
        return _Collector(self)


class _Collector:
    def __init__(self, h):
        self.h = h

    def write(self, data):
        self.h.response_body += data


def _make_request(host="localhost:9876", origin=None, csrf=None,
                  form_fields=None, x_csrf_header=None):
    fields = dict(form_fields or {})
    if csrf is not None:
        fields["csrf"] = csrf
    body = "&".join(f"{k}={v}" for k, v in fields.items()).encode()
    headers = {"Host": host, "Content-Length": str(len(body))}
    if origin is not None:
        headers["Origin"] = origin
    if x_csrf_header is not None:
        headers["X-CSRF-Token"] = x_csrf_header
    return _FakeHandler(headers, body)


class TestMutateChokepoint:

    def test_happy_path_consumes_token(self, clean_csrf_store):
        tok = dash._issue_csrf_token()
        h = _make_request(csrf=tok, form_fields={"name": "Foo"})
        result = dash._mutate(h, required_fields=("name",))
        assert result is not None and result.get("name") == "Foo"
        assert tok not in dash._csrf_tokens

    def test_wrong_host_is_rejected_and_does_not_consume(self, clean_csrf_store):
        tok = dash._issue_csrf_token()
        h = _make_request(host="evil.example.com:1234", csrf=tok,
                          form_fields={"name": "Foo"})
        assert dash._mutate(h, required_fields=("name",)) is None
        assert h.response_code == 403
        assert tok in dash._csrf_tokens

    def test_127_loopback_host_accepted(self, clean_csrf_store):
        tok = dash._issue_csrf_token()
        h = _make_request(host="127.0.0.1:9876", csrf=tok,
                          form_fields={"name": "Foo"})
        assert dash._mutate(h, required_fields=("name",)) is not None

    def test_wrong_origin_is_rejected(self, clean_csrf_store):
        tok = dash._issue_csrf_token()
        h = _make_request(origin="https://evil.example.com", csrf=tok,
                          form_fields={"name": "Foo"})
        assert dash._mutate(h, required_fields=("name",)) is None
        assert h.response_code == 403

    def test_missing_origin_is_allowed(self, clean_csrf_store):
        tok = dash._issue_csrf_token()
        h = _make_request(origin=None, csrf=tok, form_fields={"name": "Foo"})
        assert dash._mutate(h, required_fields=("name",)) is not None

    def test_matching_origin_accepted(self, clean_csrf_store):
        tok = dash._issue_csrf_token()
        h = _make_request(origin="http://localhost:9876", csrf=tok,
                          form_fields={"name": "Foo"})
        assert dash._mutate(h, required_fields=("name",)) is not None

    def test_missing_csrf_rejected(self, clean_csrf_store):
        h = _make_request(csrf=None, form_fields={"name": "Foo"})
        assert dash._mutate(h, required_fields=("name",)) is None
        assert h.response_code == 403

    def test_expired_csrf_rejected(self, clean_csrf_store):
        tok = dash._issue_csrf_token()
        with dash._csrf_lock:
            dash._csrf_tokens[tok] = time.time() - 1
        h = _make_request(csrf=tok, form_fields={"name": "Foo"})
        assert dash._mutate(h, required_fields=("name",)) is None
        assert h.response_code == 403

    def test_replay_is_rejected(self, clean_csrf_store):
        tok = dash._issue_csrf_token()
        dash._mutate(_make_request(csrf=tok, form_fields={"name": "Foo"}),
                     required_fields=("name",))
        h2 = _make_request(csrf=tok, form_fields={"name": "Foo"})
        assert dash._mutate(h2, required_fields=("name",)) is None
        assert h2.response_code == 403

    def test_header_based_csrf_accepted(self, clean_csrf_store):
        tok = dash._issue_csrf_token()
        h = _make_request(csrf=None, x_csrf_header=tok, form_fields={"name": "Foo"})
        assert dash._mutate(h, required_fields=("name",)) is not None

    def test_missing_required_field_rejected(self, clean_csrf_store):
        tok = dash._issue_csrf_token()
        h = _make_request(csrf=tok, form_fields={})
        assert dash._mutate(h, required_fields=("name",)) is None
        assert h.response_code == 400


# ── End-to-end via real ThreadingHTTPServer on an ephemeral port ────────────

@pytest.fixture
def live_server(tmp_home, clean_csrf_store):
    """Start a real dashboard server on 127.0.0.1:<ephemeral>.

    Yields a tuple `(host_header, http_get, http_post, scrape_csrf)` where
    the helpers speak to the running server via `http.client`. Shuts the
    server down on fixture teardown.
    """
    # Seed a minimal DB so build_dashboard doesn't short-circuit to None.
    db = init_db()
    db.close()

    server = ThreadingHTTPServer(("127.0.0.1", 0), dash.DashboardHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = f"127.0.0.1:{port}"

    def http_get(path, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("GET", path, headers=headers or {"Host": host})
            resp = conn.getresponse()
            return (
                resp.status,
                dict(resp.getheaders()),
                resp.read().decode("utf-8", errors="replace"),
            )
        finally:
            conn.close()

    def http_post(path, form_fields, headers=None):
        import urllib.parse as _u
        body = _u.urlencode(form_fields)
        req_headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": host,
        }
        if headers:
            req_headers.update(headers)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("POST", path, body=body, headers=req_headers)
            resp = conn.getresponse()
            return (
                resp.status,
                dict(resp.getheaders()),
                resp.read().decode("utf-8", errors="replace"),
            )
        finally:
            conn.close()

    def scrape_csrf():
        _, _, page = http_get("/")
        m = re.search(r'name="csrf"\s+value="([^"]+)"', page)
        if not m:
            m = re.search(r'"X-CSRF-Token":\s*"([^"]+)"', page)
        return m.group(1) if m else None

    try:
        yield host, http_get, http_post, scrape_csrf
    finally:
        server.shutdown()
        server.server_close()


class TestStaticAllowlist:

    def test_htmx_is_served(self, live_server):
        _, http_get, _, _ = live_server
        status, headers, body = http_get("/static/htmx.min.js")
        assert status == 200
        assert "javascript" in (headers.get("Content-Type") or "")
        assert len(body) > 1000

    def test_non_allowlisted_file_rejected(self, live_server):
        _, http_get, _, _ = live_server
        status, _, _ = http_get("/static/secrets.txt")
        assert status == 404

    def test_path_traversal_encoded(self, live_server):
        _, http_get, _, _ = live_server
        status, _, _ = http_get("/static/..%2Fconfig.py")
        assert status == 404

    def test_path_traversal_literal(self, live_server):
        _, http_get, _, _ = live_server
        status, _, _ = http_get("/static/../config.py")
        assert status == 404


class TestDashboardGet:

    def test_embeds_csrf_and_htmx(self, live_server):
        _, http_get, _, _ = live_server
        status, _, page = http_get("/")
        assert status == 200
        assert 'name="csrf"' in page
        assert "X-CSRF-Token" in page
        assert '<script src="/static/htmx.min.js"' in page


class TestPlannedTaskEndpoints:

    def test_create_returns_planned_card(self, live_server):
        _, _, http_post, scrape_csrf = live_server
        csrf = scrape_csrf()
        status, _, body = http_post("/api/planned-tasks", {
            "name": "Test Task", "signals": "a,b",
            "notes": "hello", "csrf": csrf,
        })
        assert status == 200
        assert 'id="planned-card"' in body
        assert "Test Task" in body
        raw = json.loads(config.TASKS_JSON_FILE.read_text())
        assert raw[0]["name"] == "Test Task"
        assert raw[0]["signals"] == ["a", "b"]

    def test_duplicate_create_returns_409(self, live_server):
        _, _, http_post, scrape_csrf = live_server
        http_post("/api/planned-tasks", {"name": "Test", "csrf": scrape_csrf()})
        status, _, _ = http_post("/api/planned-tasks", {
            "name": "Test", "csrf": scrape_csrf(),
        })
        assert status == 409

    def test_update_changes_fields(self, live_server):
        _, _, http_post, scrape_csrf = live_server
        http_post("/api/planned-tasks", {
            "name": "Test", "signals": "a", "csrf": scrape_csrf(),
        })
        status, _, _ = http_post("/api/planned-tasks/Test", {
            "signals": "x,y,z", "notes": "updated", "csrf": scrape_csrf(),
        })
        assert status == 200
        raw = json.loads(config.TASKS_JSON_FILE.read_text())
        assert raw[0]["signals"] == ["x", "y", "z"]
        assert raw[0]["notes"] == "updated"

    def test_delete_removes_task(self, live_server):
        _, _, http_post, scrape_csrf = live_server
        http_post("/api/planned-tasks", {"name": "Test", "csrf": scrape_csrf()})
        status, _, _ = http_post("/api/planned-tasks/Test/delete", {
            "csrf": scrape_csrf(),
        })
        assert status == 200
        assert json.loads(config.TASKS_JSON_FILE.read_text()) == []

    def test_delete_unknown_returns_404(self, live_server):
        _, _, http_post, scrape_csrf = live_server
        status, _, _ = http_post("/api/planned-tasks/NoSuch/delete", {
            "csrf": scrape_csrf(),
        })
        assert status == 404


class TestDiscoveryEndpoints:

    def test_promote_creates_task_and_marks_discovery(self, live_server):
        host, _, http_post, scrape_csrf = live_server
        config.DISCOVERED_FILE.write_text(json.dumps({"activities": [{
            "name": "Sanskrit Tool",
            "first_seen": "2026-04-10T09:00:00",
            "last_seen": "2026-04-12T10:00:00",
            "count": 5,
            "sample_signals": ["devanagari"],
            "promoted": False,
        }]}))
        status, _, body = http_post(
            "/api/discoveries/Sanskrit%20Tool/promote",
            {"csrf": scrape_csrf()},
        )
        assert status == 200
        assert 'id="discovered-card"' in body
        assert 'id="planned-card"' in body and 'hx-swap-oob="true"' in body
        raw = json.loads(config.TASKS_JSON_FILE.read_text())
        assert raw[0]["name"] == "Sanskrit Tool"
        assert raw[0]["signals"] == ["devanagari"]
        disc = json.loads(config.DISCOVERED_FILE.read_text())
        assert disc["activities"][0]["promoted"] is True

    def test_hide_sets_hidden_flag(self, live_server):
        _, _, http_post, scrape_csrf = live_server
        config.DISCOVERED_FILE.write_text(json.dumps({"activities": [{
            "name": "Noisy", "first_seen": "2026-04-10T09:00:00",
            "last_seen": "2026-04-12T10:00:00", "count": 1,
            "sample_signals": [], "promoted": False,
        }]}))
        status, _, _ = http_post("/api/discoveries/Noisy/hide", {
            "csrf": scrape_csrf(),
        })
        assert status == 200
        disc = json.loads(config.DISCOVERED_FILE.read_text())
        assert disc["activities"][0].get("hidden") is True


class TestCsrfEnforcement:

    def test_missing_csrf_on_post_403(self, live_server):
        _, _, http_post, _ = live_server
        status, _, _ = http_post("/api/planned-tasks", {"name": "NoCSRF"})
        assert status == 403

    def test_wrong_host_on_post_403(self, live_server):
        _, _, http_post, scrape_csrf = live_server
        csrf = scrape_csrf()
        status, _, _ = http_post(
            "/api/planned-tasks",
            {"name": "WrongHost", "csrf": csrf},
            headers={"Host": "evil.example.com:1234"},
        )
        assert status == 403


class TestXssCanary:

    def test_task_name_is_escaped_in_response(self, live_server):
        _, _, http_post, scrape_csrf = live_server
        status, _, body = http_post("/api/planned-tasks", {
            "name": "<script>alert(1)</script>",
            "csrf": scrape_csrf(),
        })
        assert status == 200
        assert "&lt;script&gt;" in body
        assert "<script>alert(1)</script>" not in body


class TestUnknownRoute:

    def test_unknown_post_route_404(self, live_server):
        _, _, http_post, scrape_csrf = live_server
        status, _, _ = http_post("/api/no-such-route", {"csrf": scrape_csrf()})
        assert status == 404


# ── Session timeline + correction/confirm endpoints ─────────────────────────

def _seed_session_row(db, task="auth refactor", kind="session"):
    cur = db.execute(
        """INSERT INTO sessions (
            start, end, task, task_name_confidence, boundary_confidence,
            cycle_count, dip_count, evidence_json, kind
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "2026-04-12T10:00:00",
            "2026-04-12T10:30:00",
            task,
            "high",
            "high",
            3,
            0,
            json.dumps([{"signal": "workspace", "weight": "strong"}]),
            kind,
        ),
    )
    db.commit()
    return cur.lastrowid


class TestRenderSessionTimeline:
    """Unit tests for the session timeline renderer — no HTTP."""

    def test_empty_state(self):
        html = dash.render_session_timeline([], csrf_token="t")
        assert "No sessions yet today" in html
        assert "session-list" not in html

    def test_normal_session(self):
        html = dash.render_session_timeline([{
            "id": 7, "start": "2026-04-12T10:00:00",
            "end": "2026-04-12T10:30:00", "task": "auth refactor",
            "task_name_confidence": "high", "boundary_confidence": "high",
            "cycle_count": 3, "dip_count": 0,
            "evidence": [{"signal": "workspace", "weight": "strong"}],
            "kind": "session",
        }], csrf_token="t")
        assert 'id="session-7"' in html
        assert "auth refactor" in html
        assert "10:00" in html and "10:30" in html
        assert "conf-high" in html
        # Evidence drawer rendered.
        assert "Why we think so" in html
        assert "workspace" in html
        # Confirm and correct controls are visible.
        assert "hx-post=\"/api/sessions/7/confirm\"" in html
        assert "hx-post=\"/api/sessions/7/correct\"" in html

    def test_unclear_session(self):
        html = dash.render_session_timeline([{
            "id": 1, "start": "2026-04-12T10:00:00",
            "end": "2026-04-12T10:05:00", "task": None,
            "task_name_confidence": "low", "boundary_confidence": "low",
            "cycle_count": 1, "dip_count": 0, "evidence": [],
            "kind": "unclear",
        }], csrf_token="t")
        assert "kind-unclear" in html
        assert ">Unclear<" in html
        # Unclear rows have the correct button but NO confirm button.
        assert "hx-post=\"/api/sessions/1/correct\"" in html
        assert "hx-post=\"/api/sessions/1/confirm\"" not in html

    def test_away_entry(self):
        html = dash.render_session_timeline([{
            "id": 2, "start": "2026-04-12T12:00:00",
            "end": "2026-04-12T13:00:00", "task": None,
            "task_name_confidence": "low", "boundary_confidence": "high",
            "cycle_count": 1, "dip_count": 0, "evidence": [],
            "kind": "away",
        }], csrf_token="t")
        assert "kind-away" in html
        assert ">Away<" in html
        # Away entries have NO correction OR confirm controls.
        assert "/api/sessions/2/correct" not in html
        assert "/api/sessions/2/confirm" not in html

    def test_session_with_dips(self):
        html = dash.render_session_timeline([{
            "id": 3, "start": "2026-04-12T10:00:00",
            "end": "2026-04-12T11:00:00", "task": "auth",
            "task_name_confidence": "high", "boundary_confidence": "high",
            "cycle_count": 9, "dip_count": 1, "evidence": [],
            "kind": "session",
        }], csrf_token="t")
        assert "9 cycles" in html
        assert "1 dip" in html

    def test_html_escapes_untrusted_task_name(self):
        html = dash.render_session_timeline([{
            "id": 4, "start": "2026-04-12T10:00:00",
            "end": "2026-04-12T10:30:00",
            "task": "<script>alert(1)</script>",
            "task_name_confidence": "high", "boundary_confidence": "high",
            "cycle_count": 1, "dip_count": 0, "evidence": [],
            "kind": "session",
        }], csrf_token="t")
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
        assert "<script>alert(1)</script>" not in html

    def test_correction_form_has_five_user_kind_options(self):
        html = dash.render_session_timeline([{
            "id": 5, "start": "2026-04-12T10:00:00",
            "end": "2026-04-12T10:30:00", "task": "t",
            "task_name_confidence": "high", "boundary_confidence": "high",
            "cycle_count": 1, "dip_count": 0, "evidence": [],
            "kind": "session",
        }], csrf_token="t")
        assert 'value="on_planned_task"' in html
        assert 'value="thinking_offline"' in html
        assert 'value="meeting"' in html
        assert 'value="break"' in html
        assert 'value="other"' in html
        # Human labels.
        assert "Working on a task" in html
        assert "Thinking / reading offline" in html
        assert "Meeting (no screenshare)" in html
        assert "Break / lunch" in html
        assert "Something else" in html

    def test_correction_form_uses_form_level_hx_post(self):
        """The correction form uses the proven `<form hx-post>` +
        `<button type="submit">` pattern — same as render_planned_card.
        This pins the shape so a future refactor doesn't silently
        regress to a button-driven variant that didn't serialize
        form fields correctly in the browser."""
        html = dash.render_session_timeline([{
            "id": 9, "start": "2026-04-12T10:00:00",
            "end": "2026-04-12T10:30:00", "task": "t",
            "task_name_confidence": "high", "boundary_confidence": "high",
            "cycle_count": 1, "dip_count": 0, "evidence": [],
            "kind": "session",
        }], csrf_token="t")
        import re
        # hx-post lives on the <form> tag itself.
        m = re.search(
            r'<form class="correct-form"\s+hx-post="/api/sessions/9/correct"',
            html,
        )
        assert m is not None, "hx-post must be on the <form> element"
        # Save is a regular submit button inside that form.
        assert '<button type="submit" class="btn btn-primary">Save</button>' in html

    def test_correction_form_is_outside_session_actions_container(self):
        """Regression: the correction form must NOT be a child of
        `session-actions`. Nesting it there put Save inside a flex
        container alongside Confirm/Correct, and browser click
        events didn't fire reliably on the Save button in that
        layout (keyboard Enter still worked). Lifting the form to
        be a sibling of session-actions sidesteps the issue."""
        html_out = dash.render_session_timeline([{
            "id": 11, "start": "2026-04-12T10:00:00",
            "end": "2026-04-12T10:30:00", "task": "t",
            "task_name_confidence": "high", "boundary_confidence": "high",
            "cycle_count": 1, "dip_count": 0, "evidence": [],
            "kind": "session",
        }], csrf_token="t")
        # session-actions opens, then closes, THEN the form opens.
        # The form's opening tag must NOT be inside session-actions.
        actions_start = html_out.find('<div class="session-actions">')
        actions_end = html_out.find('</div>', actions_start)
        form_start = html_out.find('<form class="correct-form"')
        assert actions_start != -1
        assert actions_end != -1
        assert form_start != -1
        assert form_start > actions_end, (
            "correction form must be a SIBLING of session-actions, "
            "not a descendant — nesting it inside the flex row caused "
            "clicks on Save to be swallowed in the browser"
        )


class TestSessionEndpoints:

    def _seed_db_session(self):
        db = init_db()
        try:
            return _seed_session_row(db)
        finally:
            db.close()

    def test_correct_happy_path(self, live_server):
        sid = self._seed_db_session()
        _, _, http_post, scrape_csrf = live_server
        status, _, body = http_post(
            f"/api/sessions/{sid}/correct",
            {
                "csrf": scrape_csrf(),
                "user_kind": "on_planned_task",
                "user_task": "auth refactor",
                "user_note": "yes, this is right",
            },
        )
        assert status == 200
        # Response is the re-rendered row.
        assert f'id="session-{sid}"' in body
        # DB got the correction.
        db = sqlite3.connect(str(config.DB_PATH))
        rows = db.execute(
            "SELECT user_verdict, user_task, user_kind, user_note "
            "FROM corrections WHERE entry_kind='session' AND entry_id=?",
            (sid,),
        ).fetchall()
        db.close()
        assert len(rows) == 1
        assert rows[0] == (
            "corrected", "auth refactor", "on_planned_task", "yes, this is right",
        )

    def test_confirm_happy_path(self, live_server):
        sid = self._seed_db_session()
        _, _, http_post, scrape_csrf = live_server
        status, _, body = http_post(
            f"/api/sessions/{sid}/confirm",
            {"csrf": scrape_csrf()},
        )
        assert status == 200
        assert f'id="session-{sid}"' in body
        db = sqlite3.connect(str(config.DB_PATH))
        rows = db.execute(
            "SELECT user_verdict FROM corrections WHERE entry_id=?", (sid,),
        ).fetchall()
        db.close()
        assert len(rows) == 1
        assert rows[0][0] == "confirmed"

    def test_correct_rejects_invalid_user_kind(self, live_server):
        sid = self._seed_db_session()
        _, _, http_post, scrape_csrf = live_server
        status, _, _ = http_post(
            f"/api/sessions/{sid}/correct",
            {"csrf": scrape_csrf(), "user_kind": "bogus"},
        )
        assert status == 400
        db = sqlite3.connect(str(config.DB_PATH))
        count = db.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]
        db.close()
        assert count == 0

    def test_correct_404_on_unknown_session(self, live_server):
        self._seed_db_session()  # exists but id != 9999
        _, _, http_post, scrape_csrf = live_server
        status, _, _ = http_post(
            "/api/sessions/9999/correct",
            {"csrf": scrape_csrf(), "user_kind": "on_planned_task"},
        )
        assert status == 404

    def test_correct_without_csrf_is_403(self, live_server):
        sid = self._seed_db_session()
        _, _, http_post, _ = live_server
        status, _, _ = http_post(
            f"/api/sessions/{sid}/correct",
            {"user_kind": "on_planned_task"},
        )
        assert status == 403

    def test_correct_with_wrong_host_is_403(self, live_server):
        sid = self._seed_db_session()
        _, _, http_post, scrape_csrf = live_server
        status, _, _ = http_post(
            f"/api/sessions/{sid}/correct",
            {"csrf": scrape_csrf(), "user_kind": "on_planned_task"},
            headers={"Host": "evil.example.com:1234"},
        )
        assert status == 403

    def test_confirm_without_csrf_is_403(self, live_server):
        sid = self._seed_db_session()
        _, _, http_post, _ = live_server
        status, _, _ = http_post(
            f"/api/sessions/{sid}/confirm", {},
        )
        assert status == 403

    def test_correct_missing_user_kind_is_400(self, live_server):
        sid = self._seed_db_session()
        _, _, http_post, scrape_csrf = live_server
        # user_kind required but missing entirely → 400 via _mutate
        status, _, _ = http_post(
            f"/api/sessions/{sid}/correct",
            {"csrf": scrape_csrf()},
        )
        assert status == 400

    def test_operational_error_returns_503_not_crash(
        self, live_server, monkeypatch
    ):
        """If the SQLite INSERT hits OperationalError (e.g. database
        locked, disk I/O), the handler must return HTTP 503, NOT
        crash the worker thread. A crashed thread leaves htmx
        dangling and the inline correction form stays open on the
        user's screen — the symptom we hit on 2026-04-12."""
        import sqlite3 as _sqlite3
        from focusmonitor import corrections as corr_mod

        sid = self._seed_db_session()
        _, _, http_post, scrape_csrf = live_server

        def boom(*a, **kw):
            raise _sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(corr_mod, "record_correction", boom)

        status, _, _ = http_post(
            f"/api/sessions/{sid}/correct",
            {"csrf": scrape_csrf(), "user_kind": "on_planned_task"},
        )
        assert status == 503

    def test_failed_mutation_does_not_burn_csrf_token(
        self, live_server, monkeypatch
    ):
        """When record_correction fails with OperationalError, the
        CSRF token must NOT be consumed. Otherwise the user's next
        click on a different row fails with 403 even though nothing
        successful happened. Regression from 2026-04-12 where a 503
        on /confirm cascaded into a 403 on /correct.

        Two passes: first with record_correction patched to raise
        (503 expected, token preserved), then second with a stub
        that records a hit-count so we can assert the token is
        still accepted by `_mutate`.
        """
        import sqlite3 as _sqlite3
        from focusmonitor import corrections as corr_mod

        sid = self._seed_db_session()
        _, _, http_post, scrape_csrf = live_server

        calls = {"n": 0}

        def flaky(*a, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                # First call fails — simulates a locked DB.
                raise _sqlite3.OperationalError("database is locked")
            # Later calls: noop, mimic a successful insert. The handler
            # doesn't inspect return value of record_correction, so
            # returning None is fine.
            return 42

        monkeypatch.setattr(corr_mod, "record_correction", flaky)

        csrf = scrape_csrf()
        # First request: all three retries hit `flaky` and fail,
        # returning 503. The token must NOT be consumed.
        # (flaky always raises on call 1; retries make calls 2 and 3
        # succeed, but let's make flaky always fail for simplicity.)
        def always_fail(*a, **kw):
            raise _sqlite3.OperationalError("database is locked")
        monkeypatch.setattr(corr_mod, "record_correction", always_fail)

        status1, _, _ = http_post(
            f"/api/sessions/{sid}/correct",
            {"csrf": csrf, "user_kind": "on_planned_task"},
        )
        assert status1 == 503

        # Swap in a passing stub for the retry.
        def ok(*a, **kw):
            return 7
        monkeypatch.setattr(corr_mod, "record_correction", ok)

        status2, _, body2 = http_post(
            f"/api/sessions/{sid}/correct",
            {"csrf": csrf, "user_kind": "on_planned_task"},
        )
        assert status2 == 200, (
            f"expected retry with the same token to succeed, got {status2}: "
            f"{body2[:200]}"
        )

    def test_successful_mutation_consumes_csrf_token(self, live_server):
        """On success, the token IS consumed (same guarantee as the
        other write endpoints). A replay with the same token after
        success returns 403."""
        sid = self._seed_db_session()
        _, _, http_post, scrape_csrf = live_server

        csrf = scrape_csrf()
        status1, _, _ = http_post(
            f"/api/sessions/{sid}/correct",
            {"csrf": csrf, "user_kind": "on_planned_task"},
        )
        assert status1 == 200
        status2, _, _ = http_post(
            f"/api/sessions/{sid}/correct",
            {"csrf": csrf, "user_kind": "on_planned_task"},
        )
        assert status2 == 403

    def test_successive_corrections_use_refreshed_csrf(self, live_server):
        """Two corrections back-to-back without a page reload.

        The HX-Trigger header carries the fresh CSRF token. A real
        browser's htmx listener would update ``hx-headers`` on
        ``<body>``; here we parse the header manually and use the
        fresh token for the second POST. Both must return 200.
        """
        sid = self._seed_db_session()
        # Create a second session for the second correction.
        db = init_db()
        try:
            sid2 = _seed_session_row(db)
        finally:
            db.close()
        _, _, http_post, scrape_csrf = live_server

        csrf1 = scrape_csrf()
        status1, headers1, _ = http_post(
            f"/api/sessions/{sid}/correct",
            {"csrf": csrf1, "user_kind": "on_planned_task"},
        )
        assert status1 == 200

        # Extract fresh CSRF from HX-Trigger header.
        hx_trigger = headers1.get("HX-Trigger")
        assert hx_trigger is not None, "expected HX-Trigger header in response"
        trigger_data = json.loads(hx_trigger)
        csrf2 = trigger_data["csrf-refreshed"]["token"]
        assert csrf2 != csrf1, "fresh token must differ from consumed token"

        status2, _, body2 = http_post(
            f"/api/sessions/{sid2}/correct",
            {"csrf": csrf2, "user_kind": "meeting", "user_note": "standup"},
        )
        assert status2 == 200, (
            f"second correction with refreshed CSRF should succeed, "
            f"got {status2}: {body2[:200]}"
        )

        # Verify both corrections persisted.
        db = sqlite3.connect(str(config.DB_PATH))
        rows = db.execute(
            "SELECT entry_id, user_verdict FROM corrections "
            "ORDER BY created_at",
        ).fetchall()
        db.close()
        assert len(rows) == 2
        assert {r[0] for r in rows} == {sid, sid2}


class TestLegacyView:

    def test_default_view_renders_session_timeline_zone(self, live_server):
        _, http_get, _, _ = live_server
        status, _, body = http_get("/")
        assert status == 200
        assert 'zone-sessions' in body
        assert "Today's sessions" in body

    def test_legacy_view_hides_session_timeline(self, live_server):
        _, http_get, _, _ = live_server
        status, _, body = http_get("/?view=legacy")
        assert status == 200
        # Legacy marker present; the session list markup is absent
        # ("session-list" appears in the embedded stylesheet so we look
        # for the list opener instead of the bare string).
        assert "legacy view" in body
        assert '<ul class="session-list">' not in body
