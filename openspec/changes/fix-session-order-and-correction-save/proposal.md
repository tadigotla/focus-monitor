## Why

The dashboard's "Today's sessions" list shows sessions in chronological order (oldest first), forcing users to scroll past stale entries to see their most recent activity. Additionally, the correction form's Save button silently fails after the first submission because the CSRF token in the htmx request header goes stale — the page-level `hx-headers` attribute still holds the original token after it is consumed by the server, causing all subsequent corrections to receive a 403.

## What Changes

- Reverse the session display order so newest sessions appear at the top of the list.
- Fix the CSRF token lifecycle so that htmx correction submissions work reliably on every click, not just the first one after a page load.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `correction-loop`: The correction submission flow must survive CSRF token rotation — the fresh token returned by the server after a successful correction must propagate to subsequent htmx requests.
- `dashboard-server`: The sessions list must be rendered in reverse chronological order (newest first).

## Impact

- **Code**: `focusmonitor/dashboard.py` — session query ordering and CSRF token propagation in htmx response fragments.
- **Tests**: `tests/test_dashboard.py` and `tests/test_dashboard_mutations.py` may need updated assertions for the new ordering; the dashboard HTML snapshot will need regeneration.
- **APIs**: No public API changes; the correction POST endpoint behaviour is unchanged aside from returning a usable CSRF token.
- **Dependencies**: None.
