## 1. Reverse session ordering

- [x] 1.1 Change `ORDER BY start ASC` to `ORDER BY start DESC` in the session-rendering query in `focusmonitor/dashboard.py`

## 2. Fix CSRF token propagation for htmx corrections

- [x] 2.1 Add an inline `<script>` listener in the dashboard HTML that listens for a custom htmx event (e.g. `csrf-refreshed`) and updates the `hx-headers` attribute on `<body>` with the new token
- [x] 2.2 In the correction/confirmation POST response path, add an `HX-Trigger` response header that fires the `csrf-refreshed` event carrying the fresh CSRF token

## 3. Tests and snapshots

- [x] 3.1 Add a test in `tests/test_dashboard_mutations.py` that performs two successive correction POSTs without a page reload and asserts both succeed (no 403)
- [x] 3.2 Update the dashboard HTML snapshot (`pytest --snapshot-update`) to reflect the new session ordering
- [x] 3.3 Verify all existing tests pass with the changes
