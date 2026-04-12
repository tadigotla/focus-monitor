"""Dashboard rendering tests.

Split across:

- `TestBuildDashboardSnapshot`     — syrupy full-HTML snapshot tests
                                      against a seeded DB and a frozen
                                      clock. Update with
                                      `pytest --snapshot-update`.
- `TestDashboardStructural`        — focused assertions the snapshot
                                      alone is too noisy to express
                                      (HTML-escaping, empty-state
                                      branching).

Determinism story:

- `freeze_clock` pins `datetime.now()` to 2026-04-12T15:00:00 UTC so
  `resolve_range("today")` picks "2026-04-12".
- `seeded_db` inserts four fixed rows with timestamps inside the
  2026-04-12 day boundary.
- `_issue_csrf_token` is monkeypatched to a fixed string so the
  `csrf_token` placeholders in the rendered template don't randomize.

Together these three pins make `build_dashboard()` output byte-stable.
If you change any of them, you'll need to re-accept the snapshot with
`pytest --snapshot-update`.
"""

from __future__ import annotations

import pytest

from focusmonitor import dashboard as dash
from focusmonitor.config import DEFAULT_CONFIG


FIXED_CSRF = "TEST_CSRF_TOKEN_FIXED_VALUE_FOR_SNAPSHOT_STABILITY_DO_NOT_USE_IN_PROD"


@pytest.fixture
def stable_csrf(monkeypatch):
    """Replace the random CSRF token generator with a constant.

    `_issue_csrf_token` is called in multiple places during a single
    `build_dashboard` invocation, so the constant must be literal
    equality — not just stable within one call.
    """
    monkeypatch.setattr(dash, "_issue_csrf_token", lambda: FIXED_CSRF)


@pytest.fixture
def dashboard_seed(seeded_db, tmp_home):
    """Seeded DB + populated planned_tasks.json + discovered_activities.json.

    The `seeded_db` fixture handles the DB rows. We add minimal fixture
    files for the two JSON state files the dashboard also reads, so
    every card has content rather than the empty-state branch.
    """
    import json

    tasks_json = [
        {
            "name": "focus-monitor",
            "signals": ["focus-monitor", "focusmonitor"],
            "apps": ["Code", "Terminal"],
            "notes": "Work on the focus-monitor project itself.",
        },
        {
            "name": "Deep Reading",
            "signals": ["paper.pdf", "arxiv"],
            "apps": ["Preview"],
            "notes": "",
        },
    ]
    from focusmonitor.config import TASKS_JSON_FILE, DISCOVERED_FILE
    TASKS_JSON_FILE.write_text(json.dumps(tasks_json, indent=2))

    discovered = {
        "activities": [
            {
                "name": "news",
                "first_seen": "2026-04-12T11:30:00",
                "last_seen": "2026-04-12T11:30:00",
                "count": 1,
            },
        ]
    }
    DISCOVERED_FILE.write_text(json.dumps(discovered, indent=2))

    return seeded_db


# ── snapshot tests ───────────────────────────────────────────────────────────

class TestBuildDashboardSnapshot:

    def test_today_range_matches_snapshot(
        self, dashboard_seed, freeze_clock, stable_csrf, snapshot
    ):
        html = dash.build_dashboard(refresh_sec=0, range_key="today")
        assert html is not None
        assert html == snapshot

    def test_yesterday_range_matches_snapshot(
        self, dashboard_seed, freeze_clock, stable_csrf, snapshot
    ):
        """`yesterday` produces the empty-state variant for the seeded data.

        The seed rows are all dated 2026-04-12, so a `yesterday` query
        against frozen 2026-04-12T15:00 sees no activity. That exercises
        the empty-state branch cleanly.
        """
        html = dash.build_dashboard(refresh_sec=0, range_key="yesterday")
        assert html is not None
        assert html == snapshot


# ── structural tests the snapshot is too coarse to express ──────────────────

class TestDashboardStructural:

    def test_returns_none_when_db_missing(self, tmp_home):
        """Fresh `tmp_home` has no DB file — first-run state."""
        assert dash.build_dashboard(refresh_sec=0, range_key="today") is None

    def test_csrf_token_appears_in_rendered_html(
        self, dashboard_seed, freeze_clock, stable_csrf
    ):
        """Spot-check: the fixed token must make it into the output."""
        html = dash.build_dashboard(refresh_sec=0, range_key="today")
        assert FIXED_CSRF in html

    def test_untrusted_task_name_is_html_escaped(
        self, seeded_db, tmp_home, freeze_clock, stable_csrf
    ):
        """A task name with HTML metacharacters must not be interpreted as markup."""
        import json
        from focusmonitor.config import TASKS_JSON_FILE, DISCOVERED_FILE

        tasks = [
            {
                "name": "<script>alert('xss')</script>",
                "signals": [],
                "apps": [],
                "notes": "",
            }
        ]
        TASKS_JSON_FILE.write_text(json.dumps(tasks))
        DISCOVERED_FILE.write_text("[]")

        html = dash.build_dashboard(refresh_sec=0, range_key="today")
        assert html is not None
        # Raw tag MUST NOT appear
        assert "<script>alert('xss')</script>" not in html
        # Escaped form SHOULD appear
        assert "&lt;script&gt;" in html

    def test_untrusted_discovered_name_is_html_escaped(
        self, seeded_db, tmp_home, freeze_clock, stable_csrf
    ):
        import json
        from focusmonitor.config import TASKS_JSON_FILE, DISCOVERED_FILE

        TASKS_JSON_FILE.write_text("[]")
        DISCOVERED_FILE.write_text(json.dumps({
            "activities": [
                {
                    "name": "<img src=x onerror=alert(1)>",
                    "first_seen": "2026-04-12T10:00:00",
                    "last_seen": "2026-04-12T10:00:00",
                    "count": 1,
                }
            ]
        }))

        html = dash.build_dashboard(refresh_sec=0, range_key="today")
        assert html is not None
        assert "<img src=x" not in html
        assert "&lt;img" in html

    def test_refresh_meta_included_when_refresh_sec_set(
        self, dashboard_seed, freeze_clock, stable_csrf
    ):
        html = dash.build_dashboard(refresh_sec=60, range_key="today")
        assert 'http-equiv="refresh"' in html
        assert 'content="60"' in html

    def test_refresh_meta_omitted_when_refresh_sec_zero(
        self, dashboard_seed, freeze_clock, stable_csrf
    ):
        html = dash.build_dashboard(refresh_sec=0, range_key="today")
        assert 'http-equiv="refresh"' not in html

    def test_invalid_range_falls_back_to_today(
        self, dashboard_seed, freeze_clock, stable_csrf
    ):
        html = dash.build_dashboard(refresh_sec=0, range_key="garbage")
        assert html is not None
        # The "Today" link should be marked as current.
        assert 'href="/?range=today" class="current"' in html


# ── render_header focused tests (cheap to include; no DB needed) ────────────

class TestRenderHeader:

    def test_contains_brand_and_date(self):
        h = dash.render_header("today", "Sunday, April 12")
        assert "Focus Monitor" in h
        assert "Sunday, April 12" in h

    def test_three_range_links(self):
        h = dash.render_header("today", "Sunday, April 12")
        assert h.count('href="/?range=') == 3

    def test_today_is_current_when_range_today(self):
        h = dash.render_header("today", "Sunday, April 12")
        assert 'href="/?range=today" class="current"' in h
        assert 'aria-current="page"' in h

    def test_yesterday_not_current_when_range_today(self):
        h = dash.render_header("today", "Sunday, April 12")
        assert '<a href="/?range=yesterday" class="current"' not in h
