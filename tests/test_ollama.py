"""Tests for `focusmonitor.ollama`.

Coverage goals (from the spec's external-integration floor requirement):

  - `encode_image` — pure function, no network, real fixture PNG.
  - `query_ollama` text-only — cassette-backed against real
    llama3.2-vision responses.
  - `query_ollama` with images — cassette-backed.
  - `query_ollama` failure path — no cassette; point at an unreachable
    localhost port and confirm the client swallows the exception and
    returns None (the contract every caller relies on).

The cassettes live under `tests/cassettes/ollama/` and are replay-only by
default. See `tests/cassettes/README.md` for re-record workflow.

Why urllib + vcrpy works: `focusmonitor.ollama.query_ollama` uses
`urllib.request.urlopen`, which goes through `http.client.HTTPConnection`.
vcrpy patches that class, so the interception happens before any socket
is opened — pytest-socket doesn't see it.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from focusmonitor.config import DEFAULT_CONFIG
from focusmonitor.ollama import encode_image, query_ollama


FIXTURE_DIR = Path(__file__).parent / "data" / "screenshots"
RED_PIXEL = FIXTURE_DIR / "screen_20260412_100000.png"
GREEN_PIXEL = FIXTURE_DIR / "screen_20260412_100100.png"
BLUE_PIXEL = FIXTURE_DIR / "screen_20260412_100200.png"


# ── encode_image: pure function, no network ──────────────────────────────────

class TestEncodeImage:

    def test_returns_base64_string(self):
        result = encode_image(RED_PIXEL)
        assert isinstance(result, str)
        decoded = base64.b64decode(result)
        assert decoded[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic

    def test_deterministic_output(self):
        """Same bytes in → same base64 out. Load-bearing for cassette stability."""
        assert encode_image(RED_PIXEL) == encode_image(RED_PIXEL)

    def test_different_fixtures_produce_different_output(self):
        assert encode_image(RED_PIXEL) != encode_image(GREEN_PIXEL)
        assert encode_image(GREEN_PIXEL) != encode_image(BLUE_PIXEL)

    def test_missing_file_raises(self, tmp_path):
        missing = tmp_path / "nope.png"
        with pytest.raises(FileNotFoundError):
            encode_image(missing)


# ── query_ollama: cassette-backed success paths ──────────────────────────────

@pytest.mark.vcr
class TestQueryOllamaText:
    """Text-only prompts against llama3.2-vision.

    vcrpy cassette naming: `tests/cassettes/ollama/<class>.<test>.yaml`.
    """

    def test_returns_nonempty_text_response(self, ollama_cfg):
        result = query_ollama(
            ollama_cfg,
            "Respond with the single word: OK",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_text_for_arithmetic_prompt(self, ollama_cfg):
        result = query_ollama(
            ollama_cfg,
            "What is 2 + 2? Reply with the digit only.",
        )
        assert isinstance(result, str)
        assert len(result) > 0


@pytest.mark.vcr
class TestQueryOllamaWithImages:
    """Vision prompts with real 1x1 PNG fixtures."""

    def test_single_image_returns_response(self, ollama_cfg):
        result = query_ollama(
            ollama_cfg,
            "What color is this pixel? One word.",
            image_paths=[RED_PIXEL],
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_multiple_images_returns_none(self, ollama_cfg):
        """`llama3.2-vision` rejects multi-image requests with HTTP 400.

        This is a faithful negative test captured from the real service:
        the cassette records the server's actual error body ("this model
        only supports one image while more than one image requested"),
        and `query_ollama` is contractually required to swallow the
        HTTPError and return None. If the upstream ever starts accepting
        multi-image requests, this test will fail on the next re-record
        and the maintainer can convert it back to a positive test.
        """
        result = query_ollama(
            ollama_cfg,
            "How many images? Reply with the digit only.",
            image_paths=[RED_PIXEL, GREEN_PIXEL, BLUE_PIXEL],
        )
        assert result is None


# ── query_ollama: failure paths ──────────────────────────────────────────────

class TestQueryOllamaFailurePaths:
    """Exercise the Exception handler without a cassette.

    These tests do NOT use vcrpy — they point `query_ollama` at an
    unreachable localhost port so the real `urlopen` fails, the module's
    `except Exception` catches it, and `None` is returned. Every caller
    relies on that None contract.
    """

    def test_unreachable_localhost_returns_none(self):
        # Port 1 is privileged and nothing listens there by default.
        # The connection will be refused immediately; pytest-socket
        # allows localhost, so the attempt reaches the kernel and fails.
        cfg = DEFAULT_CONFIG.copy()
        cfg["ollama_url"] = "http://127.0.0.1:1"
        assert query_ollama(cfg, "anything") is None

    def test_unreachable_localhost_with_images_returns_none(self):
        cfg = DEFAULT_CONFIG.copy()
        cfg["ollama_url"] = "http://127.0.0.1:1"
        assert query_ollama(cfg, "describe", image_paths=[RED_PIXEL]) is None


# ── query_ollama: payload verification ───────────────────────────────────────

class TestQueryOllamaPayload:
    """Verify the request payload structure without hitting a real server."""

    def test_keep_alive_included_in_payload(self, monkeypatch):
        """The keep_alive field from config must appear in the API payload."""
        import focusmonitor.ollama as ollama_mod

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data)
            # Return a minimal valid response
            import io
            resp = io.BytesIO(json.dumps({"response": "ok"}).encode())
            return resp

        monkeypatch.setattr(ollama_mod, "urlopen", fake_urlopen)

        cfg = DEFAULT_CONFIG.copy()
        query_ollama(cfg, "test prompt")

        assert "body" in captured
        assert captured["body"]["keep_alive"] == "30s"

    def test_keep_alive_uses_custom_config_value(self, monkeypatch):
        """A user-provided ollama_keep_alive value is passed through."""
        import focusmonitor.ollama as ollama_mod

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data)
            import io
            resp = io.BytesIO(json.dumps({"response": "ok"}).encode())
            return resp

        monkeypatch.setattr(ollama_mod, "urlopen", fake_urlopen)

        cfg = DEFAULT_CONFIG.copy()
        cfg["ollama_keep_alive"] = "5m"
        query_ollama(cfg, "test prompt")

        assert captured["body"]["keep_alive"] == "5m"

    def test_temperature_and_format_included_when_provided(self, monkeypatch):
        """temperature and format appear in payload when passed."""
        import focusmonitor.ollama as ollama_mod

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data)
            import io
            resp = io.BytesIO(json.dumps({"response": "ok"}).encode())
            return resp

        monkeypatch.setattr(ollama_mod, "urlopen", fake_urlopen)

        cfg = DEFAULT_CONFIG.copy()
        query_ollama(cfg, "test prompt", temperature=0.0, format_="json")

        assert captured["body"]["options"] == {"temperature": 0.0}
        assert captured["body"]["format"] == "json"

    def test_temperature_and_format_omitted_when_none(self, monkeypatch):
        """Neither options nor format key present when args are None."""
        import focusmonitor.ollama as ollama_mod

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data)
            import io
            resp = io.BytesIO(json.dumps({"response": "ok"}).encode())
            return resp

        monkeypatch.setattr(ollama_mod, "urlopen", fake_urlopen)

        cfg = DEFAULT_CONFIG.copy()
        query_ollama(cfg, "test prompt")

        assert "options" not in captured["body"]
        assert "format" not in captured["body"]

    def test_return_timing_true_returns_tuple(self, monkeypatch):
        """return_timing=True returns (str, float) with elapsed_ms > 0."""
        import focusmonitor.ollama as ollama_mod

        def fake_urlopen(req, timeout=None):
            import io
            return io.BytesIO(json.dumps({"response": "ok"}).encode())

        monkeypatch.setattr(ollama_mod, "urlopen", fake_urlopen)

        cfg = DEFAULT_CONFIG.copy()
        result = query_ollama(cfg, "test prompt", return_timing=True)

        assert isinstance(result, tuple)
        assert len(result) == 2
        text, elapsed_ms = result
        assert isinstance(text, str)
        assert text == "ok"
        assert isinstance(elapsed_ms, float)
        assert elapsed_ms >= 0

    def test_return_timing_false_returns_string(self, monkeypatch):
        """return_timing=False (default) returns a plain string."""
        import focusmonitor.ollama as ollama_mod

        def fake_urlopen(req, timeout=None):
            import io
            return io.BytesIO(json.dumps({"response": "ok"}).encode())

        monkeypatch.setattr(ollama_mod, "urlopen", fake_urlopen)

        cfg = DEFAULT_CONFIG.copy()
        result = query_ollama(cfg, "test prompt")

        assert isinstance(result, str)
        assert result == "ok"

    def test_return_timing_on_failure_returns_none_with_elapsed(self):
        """Unreachable port with return_timing=True returns (None, float)."""
        cfg = DEFAULT_CONFIG.copy()
        cfg["ollama_url"] = "http://127.0.0.1:1"
        result = query_ollama(cfg, "anything", return_timing=True)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] is None
        assert isinstance(result[1], float)
        assert result[1] >= 0
