## Context

The focus-monitor dashboard (`focusmonitor/dashboard.py`) renders a "Today's sessions" panel. Two bugs exist in the current implementation:

1. **Session ordering** — The SQL query at line ~1431 uses `ORDER BY start ASC`, showing oldest sessions first. Users see stale entries at the top and must scroll to find recent activity.

2. **Correction Save button** — The correction form uses htmx (`hx-post`) to submit. A page-level `<body hx-headers='{"X-CSRF-Token": "..."}'>` attribute provides the CSRF token for all htmx requests. When a correction succeeds, the server consumes the token and issues a fresh one in the HTML fragment response, but the `<body>` tag's `hx-headers` attribute still holds the stale token. All subsequent htmx submissions fail with 403 because the header token takes precedence over the per-form hidden field.

## Goals / Non-Goals

**Goals:**
- Sessions display newest-first in the dashboard.
- Every correction/confirmation Save click succeeds (not just the first one after a page load).

**Non-Goals:**
- Changing the correction data model or API.
- Adding client-side JavaScript beyond what htmx already provides.
- Reworking the full-page auto-refresh mechanism.

## Decisions

### 1. Flip the SQL ORDER BY clause

Change `ORDER BY start ASC` to `ORDER BY start DESC` in the session query inside `build_dashboard()` (or equivalent session-rendering function).

**Alternative considered:** Reverse the list in Python after fetching. Rejected — sorting in SQL is simpler and avoids an extra O(n) pass.

### 2. Propagate fresh CSRF token via an HX-Trigger response header

After a successful correction POST, the server already returns a fresh HTML fragment with the new CSRF token embedded in form hidden fields. To also update the page-level htmx header, the response will include an `HX-Trigger` response header that fires a custom event (e.g. `csrf-refreshed`) carrying the new token. A small inline `<script>` listener on the page (already an htmx-enabled page) will update the `hx-headers` attribute on `<body>` when it receives this event.

**Alternative considered:** Remove the page-level `hx-headers` and rely solely on per-form hidden fields. Rejected — the `_mutate` helper prefers the header token, and other mutation endpoints (confirm, nudge dismiss) also rely on it. Changing the precedence would be a larger refactor.

**Alternative considered:** Use `htmx:configRequest` event to inject the latest token from a `<meta>` tag. This would also work but adds a global event listener for every htmx request. The HX-Trigger approach is more targeted — it fires only on correction/confirmation responses.

## Risks / Trade-offs

- **[Snapshot churn]** → The dashboard HTML snapshot (`tests/__snapshots__/test_dashboard.ambr`) will need regeneration due to the ordering change. This is expected and low-risk.
- **[Inline script]** → Adding a small inline `<script>` block increases the JS surface slightly. Mitigated by keeping it to a 3-4 line event listener that only manipulates `hx-headers`. No external fetches, no new dependencies.
- **[Test coverage for CSRF rotation]** → The existing `test_dashboard_mutations.py` tests should be extended to verify that a second correction after the first still succeeds (i.e., the fresh token is usable). This is a new test scenario.
