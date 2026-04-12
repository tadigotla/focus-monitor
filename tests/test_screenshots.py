"""Tests for `focusmonitor.screenshots`.

Covers:
  - `deduplicate_screenshots` — size-based dedup against real files
  - `recent_screenshots`      — sorted-by-name slice of SCREENSHOT_DIR
  - `cleanup_old_screenshots` — timestamp-based deletion
  - `take_screenshot`         — exercises the `screencapture` subprocess
    path by monkey-patching `subprocess.run` so the real macOS command
    doesn't fire during tests (that would open a screen-capture prompt
    and write to the test sandbox).

The committed fixture PNGs under `tests/data/screenshots/` are used by
the Ollama cassette suite — the dedup tests here generate their own
differently-sized files under `tmp_path` to stay independent of those
fixtures.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from focusmonitor import config, screenshots


# ── deduplicate_screenshots ──────────────────────────────────────────────────

class TestDeduplicateScreenshots:
    """Mirrors (and replaces) the dedup cases in `test_analysis.py`.

    Kept here so `test_analysis.py` can focus on analysis-layer tests
    and `test_screenshots.py` owns the screenshot-layer surface.
    """

    @pytest.fixture
    def size_files(self, tmp_path):
        def make(name, size):
            p = tmp_path / name
            p.write_bytes(b"x" * size)
            return p
        return {
            "a": make("a.png", 10000),
            "b": make("b.png", 10000),
            "c": make("c.png", 15000),
            "d": make("d.png", 15050),
            "e": make("e.png", 20000),
        }

    def test_consecutive_same_size_removed(self, size_files):
        result = screenshots.deduplicate_screenshots(
            list(size_files.values()), threshold_pct=2
        )
        assert result == [size_files["a"], size_files["c"], size_files["e"]]

    def test_empty_list(self):
        assert screenshots.deduplicate_screenshots([], 2) == []

    def test_threshold_zero_disables_dedup(self, size_files):
        result = screenshots.deduplicate_screenshots(
            [size_files["a"], size_files["b"], size_files["c"]], threshold_pct=0
        )
        assert len(result) == 3

    def test_single_file_survives(self, tmp_path):
        p = tmp_path / "only.png"
        p.write_bytes(b"x" * 100)
        assert screenshots.deduplicate_screenshots([p], 2) == [p]


# ── recent_screenshots ───────────────────────────────────────────────────────

class TestRecentScreenshots:

    def _make(self, name, size=100):
        p = config.SCREENSHOT_DIR / name
        p.write_bytes(b"x" * size)
        return p

    def test_returns_last_n_by_name_order(self, tmp_home):
        shots = [
            self._make("screen_20260412_090000.png"),
            self._make("screen_20260412_100000.png"),
            self._make("screen_20260412_110000.png"),
            self._make("screen_20260412_120000.png"),
            self._make("screen_20260412_130000.png"),
        ]
        result = screenshots.recent_screenshots({"screenshots_per_analysis": 3})
        assert result == shots[-3:]

    def test_empty_dir_returns_empty(self, tmp_home):
        assert screenshots.recent_screenshots({"screenshots_per_analysis": 5}) == []

    def test_fewer_than_n_returns_all(self, tmp_home):
        a = self._make("screen_20260412_100000.png")
        b = self._make("screen_20260412_110000.png")
        result = screenshots.recent_screenshots({"screenshots_per_analysis": 5})
        assert result == [a, b]


# ── cleanup_old_screenshots ──────────────────────────────────────────────────

class TestCleanupOldScreenshots:

    def _make(self, name):
        p = config.SCREENSHOT_DIR / name
        p.write_bytes(b"x")
        return p

    def test_deletes_files_older_than_keep_hours(self, tmp_home):
        now = datetime.now()
        old = (now - timedelta(hours=100)).strftime("%Y%m%d_%H%M%S")
        recent = (now - timedelta(hours=1)).strftime("%Y%m%d_%H%M%S")
        old_p = self._make(f"screen_{old}.png")
        recent_p = self._make(f"screen_{recent}.png")

        deleted = screenshots.cleanup_old_screenshots({"screenshot_keep_hours": 48})
        assert deleted == 1
        assert not old_p.exists()
        assert recent_p.exists()

    def test_empty_dir_returns_zero(self, tmp_home):
        assert screenshots.cleanup_old_screenshots(
            {"screenshot_keep_hours": 48}
        ) == 0

    def test_malformed_filename_ignored(self, tmp_home):
        """Files whose stem doesn't parse as a timestamp are left alone."""
        garbage = config.SCREENSHOT_DIR / "screen_notatimestamp.png"
        garbage.write_bytes(b"x")
        assert screenshots.cleanup_old_screenshots(
            {"screenshot_keep_hours": 1}
        ) == 0
        assert garbage.exists()


# ── take_screenshot ──────────────────────────────────────────────────────────

class TestTakeScreenshot:
    """The real `screencapture` command would pop a security prompt and
    write to the test sandbox. We replace `subprocess.run` so we just
    observe that the right command shape is constructed, and fake the
    created file."""

    def test_returns_path_when_screencapture_succeeds(self, tmp_home, monkeypatch):
        captured = {}

        def fake_run(cmd, *args, **kwargs):
            captured["cmd"] = cmd
            # Simulate screencapture creating the file.
            out_path = Path(cmd[-1])
            out_path.write_bytes(b"fake-png")
            class _R:
                returncode = 0
                stdout = b""
                stderr = b""
            return _R()

        monkeypatch.setattr("focusmonitor.screenshots.subprocess.run", fake_run)
        result = screenshots.take_screenshot()
        assert result is not None
        assert result.parent == config.SCREENSHOT_DIR
        assert result.name.startswith("screen_")
        assert result.name.endswith(".png")
        # Command shape: ["screencapture", "-x", "-C", <path>]
        assert captured["cmd"][0] == "screencapture"
        assert "-x" in captured["cmd"]

    def test_returns_none_when_file_not_created(self, tmp_home, monkeypatch):
        def fake_run(cmd, *args, **kwargs):
            class _R:
                returncode = 1
                stdout = b""
                stderr = b""
            return _R()

        monkeypatch.setattr("focusmonitor.screenshots.subprocess.run", fake_run)
        assert screenshots.take_screenshot() is None
