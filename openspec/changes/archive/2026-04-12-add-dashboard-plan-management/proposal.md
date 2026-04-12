## Why

The dashboard is now visually where the user wants it (`redesign-dashboard-visual` shipped). What it still cannot do is let the user *act on* what they see: today, adding a discovered activity to `planned_tasks.json`, editing a planned task's signals, or deleting an obsolete task all require opening `~/.focus-monitor/planned_tasks.json` in a text editor and fighting with JSON by hand. That friction is the original "management commands need to be accessible from the dashboard" ask from the exploration.

This change delivers Thread 1 Version 1 from that exploration — *plan management only*, scoped deliberately tight:

- Promote a discovered activity to a planned task (one click).
- Hide a discovered activity so it stops cluttering the card without being evicted.
- Add a planned task inline.
- Edit a planned task's signals/notes inline.
- Delete a planned task inline.

Crucially, this change also introduces the **security foundation** that any future write endpoint will use. Today's dashboard is a read-only HTTP server on `127.0.0.1:9876` — no auth, no CSRF protection, no request validation, and that's *correct* for a read-only localhost server. The moment it grows a POST endpoint, three new threats appear: DNS rebinding (a remote page tricking a browser into POSTing to localhost), other local processes with network access but no direct file access, and browser extensions with host permissions for `localhost`. A single-user local tool does not need accounts, sessions, or cookies — but it absolutely needs Host/Origin validation and a CSRF token on every mutation. Getting this wrong ships a local XSRF vulnerability by default, which is exactly the kind of thing focus-monitor's privacy-first identity cannot tolerate.

We are *not* bringing in a framework, a JS build pipeline, or a new Python dependency. We are vendoring **htmx.min.js** (single file, ~14KB, committed to the repo) and serving it from a new `/static/` route the dashboard server already has all the plumbing for. HTMX turns form-submit + partial-swap into attributes on HTML elements, so the "write endpoints that return HTML fragments" pattern from Change 1's `render_*` helpers becomes the natural consumer of this work.

## What Changes

**Security foundation (the backbone of every write endpoint)**

- Add a `_mutate(handler, required_form_fields)` choke-point function in [focusmonitor/dashboard.py](focusmonitor/dashboard.py) that every write handler MUST call. It:
  - Validates the `Host` header is `localhost:<port>` or `127.0.0.1:<port>`, rejecting anything else with 403.
  - Validates the `Origin` header (when present) matches the same, rejecting on mismatch.
  - Reads and validates a short-lived CSRF token from the request body, rejecting on missing/invalid/expired/already-used with 403.
  - Parses the form body and returns a dict of the required fields (or a 400 on missing).
- CSRF token lifecycle: generated per `GET /` response via `secrets.token_urlsafe(32)`, stored in a server-side in-memory dict with a 1-hour TTL, embedded in the rendered HTML as a hidden form field on every mutable form, invalidated on first successful use (single-use per mutation).
- No cookies, no sessions, no headers-only auth — the token is the whole auth story. This is deliberate and matches the single-user local threat model.

**Vendored HTMX**

- Create `focusmonitor/static/` directory. Place `htmx.min.js` inside it, committed to the repo as a single 14KB file. Provenance is htmx.org/dist/1.9.x/htmx.min.js; the exact version is pinned in a `PROVENANCE.md` next to the file so future readers can verify.
- Dashboard server gains a `GET /static/<filename>` route that serves files from this directory. Restrict to an allowlist (`htmx.min.js` initially) so path traversal is impossible by construction — no `os.path.join(user_input)`.
- Dashboard HTML's `<head>` gains a `<script src="/static/htmx.min.js" defer></script>` tag. This is a same-origin request to the already-existing local server — privacy invariant preserved.

**Write endpoints (all routed through `_mutate`)**

- `POST /api/planned-tasks` — create. Form fields: `name` (required), `signals` (optional, comma-separated), `notes` (optional).
- `POST /api/planned-tasks/<name>` — update. Same form shape. (Using POST instead of PUT because browser form methods and htmx's default; simplicity over correctness.)
- `POST /api/planned-tasks/<name>/delete` — delete. (POST instead of DELETE for the same reason — keeps the server-side router trivial.)
- `POST /api/discoveries/<name>/promote` — promote to planned task. Pulls the discovered activity's sample signals as suggested signals, creates the planned-task entry, and sets `promoted: true` on the discovered entry.
- `POST /api/discoveries/<name>/hide` — set `hidden: true` on the discovered entry. The rendering helper already filters hidden entries from the card (shipped in Change 1).

Every endpoint returns an HTML fragment that htmx swaps into the target card (the Planned Focus card or the Discovered Activities card). No JSON responses, no redirects, no page reloads.

**HTMX-driven inline UI (built on Change 1's visual system)**

- Planned Focus card gains a "+ Add planned task" row at the bottom. Click → inline form expands in place with name, signals (comma-separated), notes. Submit → htmx POSTs to `/api/planned-tasks` → server returns the re-rendered Planned Focus card fragment → htmx swaps it into place. Cancel → the expand collapses.
- Each planned task row gains an edit icon and a delete icon, revealed on hover. Edit → the row becomes an inline form. Delete → confirm dialog (small inline overlay, not a browser `confirm()`) → POST to `/delete` → server returns the re-rendered card.
- Discovered Activities card: each visible entry gains a "Promote" button and a "Hide" button. Click Promote → the entry becomes a planned task, both cards re-render. Click Hide → the entry is hidden from the Discovered card, the Planned card is unchanged.
- A small toast area near the header shows a success or error message after any mutation. The toast disappears after ~3 seconds via htmx's built-in `hx-swap-oob` + CSS transition — no custom JS.

**`focusmonitor/tasks.py` data-layer changes**

- Add a `hidden` field to the activity dict shape (default `false`, set by `hide` endpoint). Update `update_discovered_activities` to preserve `hidden` on upsert (same pattern as `promoted`).
- Add `add_planned_task(name, signals, notes)`, `update_planned_task(name, signals, notes)`, and `delete_planned_task(name)` helpers that read-modify-write `planned_tasks.json` atomically (write to a temp file, `os.replace` to target). These are importable by the dashboard's write handlers and are the single source of truth for planned-task mutations.
- Add a `promote_discovered(name)` helper that composes "hide the discovered entry" + "create a planned task with the discovered entry's sample signals" in one call, so the endpoint logic is a single line.

**Tests**

- Add `test_dashboard_mutations.py` at the repo root — no framework, `python3 test_*.py` convention.
- Unit-test `_mutate`: missing Host, wrong Host, wrong Origin, missing CSRF token, expired CSRF token, already-used CSRF token (replay), and all happy paths.
- Unit-test each data-layer helper (`add_planned_task`, `update_planned_task`, `delete_planned_task`, `promote_discovered`, `hide_discovered`) against a temp-file-backed `planned_tasks.json` and `discovered_activities.json`.
- Unit-test `render_planned_card` and `render_discovered_card` to confirm they now embed the CSRF token and the new buttons.
- End-to-end test: hit each endpoint with a fake handler (or subclass of `DashboardHandler` with test hooks), confirm the file side-effects and returned fragments match expectations.

**`privacy-review` skill extension**

- Edit [.claude/skills/privacy-review/SKILL.md](.claude/skills/privacy-review/SKILL.md) to add a fifth category: "Write endpoint hardening."
- The new category checks for: any new route in `dashboard.py` whose handler method is not `do_GET`, any new POST handling that does not flow through `_mutate`, any addition of `allow_origin`/`CORS`/`Access-Control-*` headers, any weakening of the Host/Origin check, and any code that imports htmx from a URL instead of the vendored file.
- This is future-proofing: so that future changes (by Claude, by a contributor, by future-me) cannot quietly add a write endpoint that bypasses the choke-point.

## Capabilities

### New Capabilities
<!-- None — this change extends `dashboard-server` with new requirements; it does not introduce a new capability. -->

### Modified Capabilities

- `dashboard-server`: this capability already describes HTTP serving, local-only binding, auto-refresh, the Rize-inspired design system from Change 1, the render helpers, the time-range toggle, and the discovered activities section. This change **adds** requirements covering the mutation choke-point, CSRF token lifecycle, Origin/Host validation, the vendored htmx file and its static route, the five write endpoints and their authentication requirements, and the inline-form UI for plan management. The existing read-only requirements remain unchanged.
- `activity-discovery`: already describes the shape of `discovered_activities.json` entries, the eviction cap, and the planned-task filter from `filter-planned-tasks-from-discoveries`. This change **adds** the `hidden` field to the entry shape and the requirement that `render_discovered_card` filter hidden entries (already implemented in Change 1 but not yet specified).
- `structured-tasks`: already describes `planned_tasks.json` shape and loading. This change **adds** the three mutation helpers (`add_planned_task`, `update_planned_task`, `delete_planned_task`) as part of the module's public surface, with requirements around atomic file writes (temp-file + `os.replace`) so a crash mid-write cannot corrupt the file.

## Impact

- **Code**
  - [focusmonitor/dashboard.py](focusmonitor/dashboard.py) — primary file. Gains `_mutate`, CSRF token store, `do_POST` handler, `do_GET` extended for `/static/*`, five mutation endpoint methods, and the CSRF-embedding additions to `render_planned_card` / `render_discovered_card`. ~400 lines added net.
  - [focusmonitor/tasks.py](focusmonitor/tasks.py) — adds five helpers (`add_planned_task`, `update_planned_task`, `delete_planned_task`, `hide_discovered`, `promote_discovered`) and a `_write_json_atomic` helper they share. Preserves `hidden` on upsert in `update_discovered_activities`. ~150 lines added.
  - **New file:** `focusmonitor/static/htmx.min.js` — vendored, ~14KB, committed.
  - **New file:** `focusmonitor/static/PROVENANCE.md` — short text file naming the upstream source and version so the provenance is auditable.
  - **New file:** `test_dashboard_mutations.py` — repo-root test file, ~500 lines covering CSRF, Host/Origin, data-layer helpers, endpoint integration.
  - [.claude/skills/privacy-review/SKILL.md](.claude/skills/privacy-review/SKILL.md) — adds section 5 "Write endpoint hardening" with the checks described above.
- **Data** — `planned_tasks.json` schema is unchanged (the existing fields `name`, `signals`, `apps`, `notes` are all this change uses). `discovered_activities.json` gains a `hidden: true | false` field, defaulting to `false`; existing files without the field are treated as `hidden: false`. No migration needed.
- **Runtime deps** — zero new Python packages. Zero new pip installs. HTMX is a single file committed to the repo, not a dependency. Python standard library only on the server side.
- **External deps / network** — **zero new network surface**. HTMX is served from `localhost:9876/static/htmx.min.js` (same origin as the dashboard). No CDN, no `fonts.googleapis.com`, no telemetry, no update checks. The `privacy-review` skill is explicitly extended to enforce this forward.
- **Privacy posture** — this is the most security-sensitive change in the project's history, but the posture remains the same: *nothing leaves the machine*. What changes is the *write* surface inside the machine, which is why the CSRF/Origin/Host hardening is non-negotiable and is wired in from the beginning, not bolted on after.
- **Tests** — existing 216-test suite must still pass unchanged. New test file adds ~40-60 assertions across CSRF, Host/Origin, data-layer atomic writes, and endpoint integration.
- **Backwards compatibility** — dashboard URL `GET /` remains identical in shape. Existing users who never click a mutation button see exactly the dashboard from Change 1. Existing `planned_tasks.json` files continue to load. Existing `discovered_activities.json` files continue to load (missing `hidden` field defaults to `false`). No migration steps, no config changes, no restart beyond the normal "unload/load the launchd plist after code changes" cadence.
- **Privacy impact section** — not required by the CLAUDE.md rule because this change introduces *zero new outbound network calls*. Everything stays on `127.0.0.1`. The Host/Origin/CSRF hardening is about making the *inbound* local surface safe, not about adding outbound traffic.
