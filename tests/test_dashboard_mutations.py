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
