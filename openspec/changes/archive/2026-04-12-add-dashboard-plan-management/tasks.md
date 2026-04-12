## 1. Vendor HTMX

- [x] 1.1 Create `focusmonitor/static/` directory.
- [x] 1.2 Place `htmx.min.js` (htmx v1.9.x, minified) into `focusmonitor/static/htmx.min.js`. Vendoring a fresh copy from `https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js` is a *one-off exception* to the network policy — allowed because it's a controlled, reviewable, committed artifact. Do this step manually and confirm file size is between 5KB and 100KB. Computing a SHA256 and recording it in the next step is required.
- [x] 1.3 Create `focusmonitor/static/PROVENANCE.md` with the upstream URL, pinned version, fetch date (2026-04-12), and SHA256 of the file. Keep it to ~10 lines.

## 2. Data-layer helpers in `focusmonitor/tasks.py`

- [x] 2.1 Add a private `_write_json_atomic(path, data)` helper that writes JSON to `<path>.tmp` and then calls `os.replace(tmp, path)`. On exception, unlink the tmp file before re-raising.
- [x] 2.2 Refactor `update_discovered_activities` to use `_write_json_atomic` for its final write, and ensure it preserves any existing `hidden` field on upsert.
- [x] 2.3 Add `add_planned_task(name, signals=None, notes="")` that reads `planned_tasks.json`, rejects on case-insensitive duplicate name (returns `False`), appends a new entry with `name`, `signals` (default `[]`), `apps: []`, `notes`, and writes atomically. Returns `True` on success.
- [x] 2.4 Add `update_planned_task(name, signals=None, notes=None)` that reads the file, finds the case-insensitive match, updates only fields that are not `None`, writes atomically. Returns `True`/`False`.
- [x] 2.5 Add `delete_planned_task(name)` that reads the file, drops the entry matching `name` case-insensitively, writes atomically. Returns `True`/`False`.
- [x] 2.6 Add `hide_discovered(name)` that reads `discovered_activities.json`, sets `hidden: true` on the case-insensitive match, writes atomically. Returns `True`/`False`.
- [x] 2.7 Add `promote_discovered(name)` that composes `add_planned_task` (with the discovered entry's `sample_signals` as `signals`) + setting `promoted: true` on the discovered entry, both written atomically (two separate atomic writes, one per file). Returns `False` if the discovered entry is missing OR if the planned task already exists (idempotent guard).

## 3. CSRF scaffolding in `focusmonitor/dashboard.py`

- [x] 3.1 Add module-level constants: `STATIC_DIR = Path(__file__).parent / "static"`, `STATIC_ALLOWLIST = {"htmx.min.js"}`, `CSRF_TTL_SECONDS = 3600`.
- [x] 3.2 Add a module-level dict `_csrf_tokens: dict[str, float]` (token → expiry epoch seconds) and a `_csrf_lock = threading.Lock()` since the handler runs on a thread pool via `ThreadingHTTPServer`.
- [x] 3.3 Add `_issue_csrf_token() -> str` that calls `secrets.token_urlsafe(32)`, records `(token, time.time() + CSRF_TTL_SECONDS)` under the lock, and returns the token.
- [x] 3.4 Add `_consume_csrf_token(token) -> bool` that under the lock: (a) prunes all expired entries, (b) checks the given token is present and not expired, (c) removes it atomically, (d) returns True on success / False on failure.
- [x] 3.5 In `build_dashboard`, call `_issue_csrf_token()` once per call and make the token available to every render helper.
- [x] 3.6 Update the `DASHBOARD_TEMPLATE` shell to include `hx-headers='{"X-CSRF-Token": "$csrf_token"}'` on the `<body>` tag so htmx sends the token on every `hx-post`.

## 4. `_mutate` choke-point and `do_POST` dispatcher

- [x] 4.1 Add `_mutate(handler, required_fields)` that performs the validation sequence from design.md Decision 2 and returns a validated fields dict or `None`. Helper methods for sending 400/403/404 live alongside it.
- [x] 4.2 Read the CSRF token from EITHER the form body `csrf` field OR the `X-CSRF-Token` header (htmx sends it as a header). Prefer the header if both are present.
- [x] 4.3 Add `do_POST` to `DashboardHandler` that dispatches based on `self.path`:
  - `/api/planned-tasks` → `_handle_create_task`
  - `/api/planned-tasks/<name>/delete` → `_handle_delete_task`
  - `/api/planned-tasks/<name>` → `_handle_update_task`
  - `/api/discoveries/<name>/promote` → `_handle_promote_discovery`
  - `/api/discoveries/<name>/hide` → `_handle_hide_discovery`
  - any other path → 404
  The `<name>` segment is URL-decoded before matching.
- [x] 4.4 Each handler method is thin: call `_mutate(...)`, call the appropriate data-layer helper, re-render the affected card(s), send a 200 with the HTML fragment, done. On `False` from the data-layer helper, send 404.
- [x] 4.5 Every path through `do_POST` and its handlers SHALL call `_mutate` exactly once. Any bypass is a bug.

## 5. `/static/*` route

- [x] 5.1 Extend `do_GET` to handle paths starting with `/static/`. Strip the prefix, look up in `STATIC_ALLOWLIST`, reject with 404 if not present.
- [x] 5.2 Read the file with `(STATIC_DIR / filename).read_bytes()`. Set `Content-Type: application/javascript` for `.js` files. Cache aggressively (`Cache-Control: public, max-age=3600`).
- [x] 5.3 Explicitly do NOT use `os.path.join(STATIC_DIR, path_segment)` — the allowlist lookup is the entire path-resolution logic. No `..` handling needed because there is no user input in the path beyond the allowlist key.

## 6. Render helper updates

- [x] 6.1 Add `<script src="/static/htmx.min.js" defer></script>` to the `DASHBOARD_TEMPLATE` `<head>`.
- [x] 6.2 Extend `render_planned_card` to accept a `csrf_token` arg. Each row gains edit/delete buttons with `hx-post` attributes. The card ends with an "+ Add planned task" affordance that, on click, reveals an inline form wired to `/api/planned-tasks`.
- [x] 6.3 Extend `render_discovered_card` to accept a `csrf_token` arg. Each visible row gains Promote and Hide buttons with `hx-post` attributes targeting `/api/discoveries/<name>/promote` and `.../hide`.
- [x] 6.4 All mutation forms include a hidden `<input type="hidden" name="csrf" value="...">` in addition to the `hx-headers` body attribute. This covers the fallback case where a form is submitted without htmx for any reason.
- [x] 6.5 Add minimal CSS for the new form elements: reuse existing `--color-*` and `--space-*` tokens; no new tokens. Inline forms get `background: var(--color-bg)` to distinguish from card surface.
- [x] 6.6 Confirm no new inline `<script>` blocks are introduced anywhere — only the `<script src="/static/htmx.min.js">` tag.
- [x] 6.7 Add an `id` to the Planned Focus card container (`id="planned-card"`) and the Discovered Activities card container (`id="discovered-card"`) so `hx-target` attributes can point at them with `#planned-card` / `#discovered-card`.

## 7. HTMX wiring details

- [x] 7.1 For forms that need to swap their target card: set `hx-target="#planned-card"` (or `#discovered-card`) and `hx-swap="outerHTML"`. The response is the rendered card fragment *including* its outer `<div id="planned-card">` wrapper.
- [x] 7.2 For promote (which affects both cards): the response contains the Discovered card (matching the target) AND the Planned card wrapped with `hx-swap-oob="true"` so htmx swaps it out-of-band. This is the standard htmx pattern for multi-target updates.
- [x] 7.3 The inline edit form swap is achieved with `hx-target="closest li"` `hx-swap="outerHTML"` pointing at the row itself — the server returns the rendered row.

## 8. Tests in `test_dashboard_mutations.py`

- [x] 8.1 Create `test_dashboard_mutations.py` at the repo root following the `python3 test_*.py` convention.
- [x] 8.2 Isolate temp paths for `DB_PATH`, `TASKS_JSON_FILE`, `DISCOVERED_FILE` via module-level monkey-patching BEFORE importing `focusmonitor.dashboard` (same pattern as `test_dashboard_render.py`).
- [x] 8.3 Unit-test `_write_json_atomic`: happy path writes the file; a simulated exception mid-write leaves the original file untouched and cleans up the tmp file.
- [x] 8.4 Unit-test each data-layer helper (`add_planned_task`, `update_planned_task`, `delete_planned_task`, `hide_discovered`, `promote_discovered`) against a temp-file-backed `planned_tasks.json` and `discovered_activities.json`. Cover success, duplicate-reject, missing-entry, and case-insensitivity cases.
- [x] 8.5 Unit-test `_issue_csrf_token` + `_consume_csrf_token`: fresh token consumed once, second consume returns False, expired token (manipulate `time.time` or the store directly) returns False.
- [x] 8.6 Unit-test `_mutate`: construct a fake `BaseHTTPRequestHandler` subclass with controllable headers, path, and rfile. Cover: valid path; wrong Host → 403; wrong Origin → 403; missing Origin → allowed; missing csrf → 403; expired csrf → 403; replay → 403; missing required field → 400.
- [x] 8.7 End-to-end test for each endpoint: use `http.client.HTTPConnection` against a real `ThreadingHTTPServer` on an ephemeral port. Seed DB/files, fetch `GET /` to scrape the CSRF token, POST to each endpoint, assert file side-effects and that the response body contains the expected re-rendered card.
- [x] 8.8 XSS canary: POST a new planned task with `name="<script>alert(1)</script>"` (via a valid CSRF token) and assert the returned card fragment contains `&lt;script&gt;` and not a raw tag.
- [x] 8.9 Path traversal canary: GET `/static/..%2Fconfig.py` and `/static/../config.py`; assert 404.
- [x] 8.10 Allowlist check: GET `/static/htmx.min.js` → 200; GET `/static/secrets.txt` → 404.
- [x] 8.11 Run all repo-root `test_*.py` files via `python3` to confirm no regressions.

## 9. Extend `privacy-review` skill

- [x] 9.1 Edit `.claude/skills/privacy-review/SKILL.md` to add a section "5. Write endpoint hardening" after the existing four categories.
- [x] 9.2 The new section lists the checks: (a) any new `do_POST` or method other than `do_GET` in `dashboard.py` must reference `_mutate`; (b) any new route in `do_POST`'s dispatcher must route to a handler that calls `_mutate`; (c) any new `Access-Control-*` / `CORS` header is a finding; (d) any weakening of the Host or Origin check is a finding; (e) any new `.js` file under `static/` must have a corresponding PROVENANCE.md entry; (f) any `http://` or `https://` URL referencing htmx or other vendored JS libraries outside of PROVENANCE.md is a finding.
- [x] 9.3 Update the report format example in the skill to include a "5. Write endpoint hardening" section.

## 10. Privacy verification

- [x] 10.1 Run the `privacy-review` skill over the diff — expect no findings in categories 1-4, and verify category 5 passes (every mutation handler calls `_mutate`, htmx is vendored, no CDN references).
- [x] 10.2 Grep the diff for `https://` and `http://` — the only matches should be in PROVENANCE.md and comments.
- [x] 10.3 Confirm `focusmonitor/dashboard.py`'s imports are still stdlib-only + `focusmonitor.*` after the change.
- [x] 10.4 Confirm the `ThreadingHTTPServer(("127.0.0.1", port), ...)` bind is unchanged.

## 11. Smoke test (manual, end-to-end)

- [x] 11.1 Reload the launchd agent or run `python3 cli.py run`. Open `http://localhost:9876/`.
- [x] 11.2 Click "+ Add planned task", fill in a name, submit. Confirm the Planned Focus card re-renders inline.
- [x] 11.3 Click the edit icon on an existing task, change its signals, save. Confirm the row updates.
- [x] 11.4 Click delete on the task just added, confirm, verify the row disappears.
- [x] 11.5 Click Promote on a discovered activity. Confirm it appears in Planned Focus and gets a promoted pill in Discovered (or is hidden based on promoted semantics).
- [x] 11.6 Click Hide on a different discovered activity. Confirm it disappears from the Discovered card.
- [x] 11.7 Open DevTools Network tab. Confirm: (a) only `localhost` requests appear; (b) `htmx.min.js` loads from `/static/htmx.min.js` with 200; (c) POSTs include an `X-CSRF-Token` header; (d) no `fonts.googleapis.com`, `unpkg`, or `cdnjs` appear anywhere.
- [x] 11.8 Flip macOS to dark mode, reload, click through again. Confirm the form elements read correctly in the dark palette.

## 12. Archive

- [x] 12.1 After implementation, tests, and smoke test pass, run the `openspec-archive-change` skill to fold the deltas into `openspec/specs/{dashboard-server,activity-discovery,structured-tasks}/spec.md` and move this change to `openspec/changes/archive/`.
