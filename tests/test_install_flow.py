"""Unit tests for `focusmonitor.install` preflight probes.

These tests are deliberately NOT cassette-backed — the probe logic is
deterministic unit plumbing (given a specific HTTP response shape or
a specific exception, return a specific state), and unit tests are the
right tool. The real Ollama / ActivityWatch HTTP shapes are already
covered by cassette-backed tests in `tests/test_ollama.py` and
`tests/test_activitywatch.py`.

Every network call is intercepted via `monkeypatch` on
`focusmonitor.install.urllib.request.urlopen`; no socket is ever opened,
which is important because `pytest-socket` would block non-loopback
connections anyway and we never want a real service dependency for
these tests.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from focusmonitor import install as inst


# ── setup.py no longer writes the launchd plist ──────────────────────────────

def test_setup_py_does_not_define_create_plist():
    """Regression guard: plist writing moved to `cli.py service install`."""
    import importlib
    setup = importlib.import_module("setup")
    assert not hasattr(setup, "create_plist"), \
        "setup.py must not expose create_plist; plist writing belongs to cli.py service install"
    assert not hasattr(setup, "MONITOR_SCRIPT"), \
        "setup.py must not reference monitor.py"
    assert not hasattr(setup, "PLIST_PATH"), \
        "setup.py must not reference a launchd plist path"


# ── Helpers ──────────────────────────────────────────────────────────────────

class _FakeResp:
    """Minimal `urlopen` return-value stand-in: supports context manager + `read()`."""

    def __init__(self, body):
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def _patch_urlopen(monkeypatch, behavior):
    """Replace `install`'s urlopen with a callable implementing `behavior`.

    `behavior` receives `(url, timeout)` and returns a `_FakeResp` or
    raises an exception.
    """
    def fake(url_or_req, *args, **kwargs):
        url = url_or_req if isinstance(url_or_req, str) else url_or_req.full_url
        return behavior(url, kwargs.get("timeout"))

    monkeypatch.setattr(inst.urllib.request, "urlopen", fake)


# ── probe_ollama ─────────────────────────────────────────────────────────────

class TestProbeOllama:

    def test_missing_when_binary_not_on_path(self, monkeypatch):
        monkeypatch.setattr(inst, "_ollama_binary_present", lambda: False)
        result = inst.probe_ollama()
        assert result.state == "missing"
        assert "brew install ollama" in result.next_command

    def test_daemon_down_when_urlopen_raises_urlerror(self, monkeypatch):
        monkeypatch.setattr(inst, "_ollama_binary_present", lambda: True)

        def boom(url, timeout):
            raise urllib.error.URLError("connection refused")

        _patch_urlopen(monkeypatch, boom)
        result = inst.probe_ollama()
        assert result.state == "daemon_down"
        assert "ollama serve" in result.next_command

    def test_wrong_state_when_model_not_pulled(self, monkeypatch):
        monkeypatch.setattr(inst, "_ollama_binary_present", lambda: True)

        def fake(url, timeout):
            return _FakeResp({"models": [{"name": "llava:latest"}]})

        _patch_urlopen(monkeypatch, fake)
        result = inst.probe_ollama()
        assert result.state == "wrong_state"
        assert "llama3.2-vision" in result.next_command

    def test_ok_when_model_pulled_exact_name(self, monkeypatch):
        monkeypatch.setattr(inst, "_ollama_binary_present", lambda: True)

        def fake(url, timeout):
            return _FakeResp({"models": [{"name": "llama3.2-vision"}]})

        _patch_urlopen(monkeypatch, fake)
        result = inst.probe_ollama()
        assert result.state == "ok"
        assert result.next_command == ""

    def test_ok_when_model_pulled_with_tag_suffix(self, monkeypatch):
        """Ollama's /api/tags returns "llama3.2-vision:latest" — the probe
        should match on the bare-name prefix."""
        monkeypatch.setattr(inst, "_ollama_binary_present", lambda: True)

        def fake(url, timeout):
            return _FakeResp({"models": [
                {"name": "some-other-model:latest"},
                {"name": "llama3.2-vision:latest"},
            ]})

        _patch_urlopen(monkeypatch, fake)
        result = inst.probe_ollama()
        assert result.state == "ok"

    def test_unknown_when_response_is_html_not_json(self, monkeypatch):
        monkeypatch.setattr(inst, "_ollama_binary_present", lambda: True)

        def fake(url, timeout):
            return _FakeResp(b"<!doctype html><title>404</title>")

        _patch_urlopen(monkeypatch, fake)
        result = inst.probe_ollama()
        assert result.state == "unknown"
        assert result.next_command == ""  # fail-open, no prescription

    def test_unknown_when_response_shape_is_wrong(self, monkeypatch):
        """Valid JSON but doesn't look like a /api/tags response."""
        monkeypatch.setattr(inst, "_ollama_binary_present", lambda: True)

        def fake(url, timeout):
            return _FakeResp(b"null")

        _patch_urlopen(monkeypatch, fake)
        result = inst.probe_ollama()
        # null → data.get("models", []) would fail because data is None
        assert result.state == "unknown"

    def test_custom_expected_model(self, monkeypatch):
        """User can override expected_model when passing the arg explicitly."""
        monkeypatch.setattr(inst, "_ollama_binary_present", lambda: True)

        def fake(url, timeout):
            return _FakeResp({"models": [{"name": "llava:latest"}]})

        _patch_urlopen(monkeypatch, fake)
        result = inst.probe_ollama(expected_model="llava")
        assert result.state == "ok"


# ── probe_activitywatch ──────────────────────────────────────────────────────

class TestProbeActivityWatch:

    def test_missing_when_app_absent(self, monkeypatch):
        monkeypatch.setattr(inst, "_aw_app_present", lambda: False)
        result = inst.probe_activitywatch()
        assert result.state == "missing"
        assert "activitywatch" in result.next_command.lower()

    def test_daemon_down_when_urlopen_raises(self, monkeypatch):
        monkeypatch.setattr(inst, "_aw_app_present", lambda: True)

        def boom(url, timeout):
            raise urllib.error.URLError("connection refused")

        _patch_urlopen(monkeypatch, boom)
        result = inst.probe_activitywatch()
        assert result.state == "daemon_down"
        assert "open /Applications/ActivityWatch.app" in result.next_command

    def test_ok_on_any_2xx_response(self, monkeypatch):
        monkeypatch.setattr(inst, "_aw_app_present", lambda: True)

        def fake(url, timeout):
            return _FakeResp(b'{"hostname":"test","version":"v0.13.2"}')

        _patch_urlopen(monkeypatch, fake)
        result = inst.probe_activitywatch()
        assert result.state == "ok"
        assert result.next_command == ""

    def test_ok_does_not_parse_body(self, monkeypatch):
        """AW probe deliberately doesn't inspect the response body beyond
        confirming the read completes. A garbage body from a 200 is fine."""
        monkeypatch.setattr(inst, "_aw_app_present", lambda: True)

        def fake(url, timeout):
            return _FakeResp(b"not-json-but-still-a-response")

        _patch_urlopen(monkeypatch, fake)
        result = inst.probe_activitywatch()
        assert result.state == "ok"

    def test_does_not_check_buckets(self, monkeypatch):
        """Freshly-launched AW returns /api/0/info but has no buckets yet.
        The probe must report healthy — bucket checks are runtime-only."""
        monkeypatch.setattr(inst, "_aw_app_present", lambda: True)

        probed_urls = []

        def fake(url, timeout):
            probed_urls.append(url)
            return _FakeResp(b'{"hostname":"fresh"}')

        _patch_urlopen(monkeypatch, fake)
        result = inst.probe_activitywatch()
        assert result.state == "ok"
        # Exactly one request was made, and it was /api/0/info — not /api/0/buckets
        assert len(probed_urls) == 1
        assert "/api/0/info" in probed_urls[0]
        assert "bucket" not in probed_urls[0]


# ── Invariants ───────────────────────────────────────────────────────────────

class TestInstallModuleInvariants:
    """Structural invariants documented in the spec."""

    def test_probes_use_loopback_urls_by_default(self):
        assert inst.OLLAMA_URL.startswith("http://127.0.0.1:") or inst.OLLAMA_URL.startswith("http://localhost:")
        assert inst.ACTIVITYWATCH_URL.startswith("http://127.0.0.1:") or inst.ACTIVITYWATCH_URL.startswith("http://localhost:")

    def test_module_imports_only_stdlib(self):
        """Every top-level import in `focusmonitor.install` must resolve
        to the Python standard library. If a future edit adds a third-
        party import, this test fails before the fresh-install flow
        breaks on a box that hasn't activated the dev venv yet."""
        import ast, importlib, sys
        from pathlib import Path

        source = Path(inst.__file__).read_text()
        tree = ast.parse(source)

        stdlib_names = set(sys.stdlib_module_names)
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top not in stdlib_names:
                        offenders.append(top)
            elif isinstance(node, ast.ImportFrom):
                if node.module is None:
                    continue
                top = node.module.split(".")[0]
                if top not in stdlib_names:
                    offenders.append(top)
        assert offenders == [], f"Non-stdlib imports in focusmonitor.install: {offenders}"
