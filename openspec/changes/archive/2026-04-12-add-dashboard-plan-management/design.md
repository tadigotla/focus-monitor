## Context

After `redesign-dashboard-visual`, the dashboard at [focusmonitor/dashboard.py](focusmonitor/dashboard.py) is a 770-line Rize-inspired single-page read-only server bound to `127.0.0.1:9876`. It has a `DashboardHandler` with a `do_GET` method, a `build_dashboard` orchestrator, seven `render_*` card helpers, a `string.Template` shell, and a design-tokens CSS layer. It does not have a `do_POST`, a CSRF token, a `/static/*` route, any form elements, any JavaScript, or any mutation path.

The user wants to manage their plan from the dashboard: promote a discovered activity, add/edit/delete planned tasks, hide noisy discoveries. The exploration landed on *plan management only* for this change (config editing, restart, manual-analyze are V2/V3/never). The exploration also committed to Option A from the architecture spread: Python server-renders, HTMX vendored into the repo (no CDN), handwritten CSS custom properties (no framework), stdlib only.

This design document covers the how. The what is in proposal.md; the what-must-be-true is in specs/. Where a decision affects the security posture, I name the alternative and say why we're not doing that.

## Goals / Non-Goals

**Goals:**

- Ship plan management (promote / add / edit / delete / hide) accessible from the dashboard with zero text-editor friction.
- Introduce the security foundation — Host/Origin validation + per-request CSRF token + single mutation choke-point — correctly on first try, so the rest of the dashboard's future can build on it.
- Vendor htmx (single file, committed to repo, served from a new `/static/` route) so the UX is "interactive enough to feel real" without importing a framework or touching an external network.
- Keep the server single-file, single-process, standard-library-only. Zero new Python packages, zero new runtime dependencies.
- Harden the `privacy-review` skill so future mutations cannot be landed without the same hardening.
- Keep existing `GET /` behavior identical for any client that never touches the mutation UI.

**Non-Goals:**

- **No authentication.** Not in the "log in with a password" sense. The CSRF token is the entire auth story and is sufficient for the single-user local threat model.
- **No sessions, cookies, or JWTs.** A mutation request carries a single-use CSRF token in its form body. That's it.
- **No config editing from the dashboard.** Out of scope for this change, Thread 1 V2.
- **No process management from the dashboard.** No restart button, no "analyze now" button, no kill switch. Those are Thread 1 V3 if ever.
- **No delete of activity_log rows.** Out of scope — touching the SQLite history is destructive and has no safe undo.
- **No undo/redo.** Delete operations show an inline confirmation dialog and proceed on confirm. Users who change their mind re-add the task; the cost is low in a single-user local tool.
- **No multi-user considerations.** There is only ever one user.
- **No CORS support.** The dashboard does not and will never accept cross-origin requests.
- **No keyboard shortcuts.** Deferred until a real need emerges.
- **No reopening the design system.** All visual work uses Change 1's tokens and component CSS. This change adds at most a few form-specific rules.
- **No accessibility audit beyond Change 1's baseline.** Semantic HTML, focus rings, `aria-label` on mutation buttons. Full WCAG pass is still deferred.
- **No support for browsers with JavaScript disabled (mutation paths only).** The read-only view still renders without JS. Mutation requires htmx, which requires JS. This is a degradation for no one — the user opens the dashboard in their main browser.
- **No rate limiting.** Single user, local server, no abuse model.

## Decisions

### Decision 1: CSRF-token-per-`GET` as the whole auth story

**Chosen:** On every `GET /` response, generate a fresh token via `secrets.token_urlsafe(32)`. Store it in a module-level dict `_csrf_tokens: {token: expiry_timestamp}` with a 1-hour TTL. Embed the token in the rendered HTML as a hidden `<input name="csrf" value="...">` inside every mutation form *and* as an HTMX `hx-headers='{"X-CSRF-Token": "..."}'` attribute on the `<body>`. On every mutation request, `_mutate` validates the token exists in the store, is not expired, and removes it on successful validation (single-use per mutation).

**Why:**

- The threat we're defending against is DNS rebinding and browser extensions POSTing to `localhost:9876` without the user's knowledge. Both attackers can see the user's cookies and headers but *cannot* read the HTML the dashboard served to the user's real browser tab — that's protected by the same-origin policy. Therefore a secret embedded in the HTML is a strong enough signal that "this request came from a real visit to this server."
- Single-use means a leaked token is only useful once, and since the HTML is re-rendered on every auto-refresh, the blast radius of a leak is at most one mutation.
- In-memory store means no file I/O, no persistence across restarts (fine — tokens are 1-hour TTL anyway), no database schema change.
- `secrets.token_urlsafe(32)` is 256 bits of entropy from `os.urandom`. Not guessable.
- TTL of 1 hour is long enough that a user who opens the dashboard, goes to get coffee, and comes back can still click a button. Short enough that an abandoned tab's token expires before the machine sleeps or wakes.

**Alternatives considered:**

- **Double-submit cookie pattern.** Classic CSRF defense: server sets a random cookie, server embeds the same value in the HTML, mutation request must send both. Rejected because it adds cookies to a project that has zero cookies, and for single-user local a cookie buys nothing over the simpler "embed in HTML" approach.
- **SameSite=strict cookie as the only defense.** Too dependent on browser behavior; doesn't defend against DNS rebinding as cleanly; and we'd still be adding cookies for the first time.
- **HMAC-signed token with no server state.** More scalable but our server-state overhead is 32 bytes per active token, capped at a few hundred per hour at absolute worst. Not worth the complexity of key management.
- **No CSRF at all, rely on Host/Origin only.** Rejected. Origin is trivially absent on some requests, and Host can be spoofed in DNS rebinding scenarios where the browser still sends the attacker's hostname. Defense in depth matters here.

### Decision 2: Single `_mutate(handler, required_fields)` choke-point

**Chosen:** Every mutation endpoint calls `_mutate(self, required_fields)` as its first act. The helper returns either a dict of validated form fields (on success) or `None` (after writing an error response to the handler). If it returns `None`, the endpoint returns immediately without touching any files. The helper performs, in order:

1. Validate `self.headers["Host"]` is `localhost:<port>` or `127.0.0.1:<port>`. Reject with 403 and a plain-text body on mismatch.
2. Validate `self.headers["Origin"]` (if present) against the same. Absent Origin is allowed (happens on direct form posts); present-but-mismatched is rejected.
3. Read `Content-Length` bytes from `self.rfile`, parse as `application/x-www-form-urlencoded`, yielding a flat dict. Reject with 400 if `Content-Length` is missing or unparseable.
4. Validate a `csrf` field is present, matches an entry in `_csrf_tokens`, and is not expired. Remove the token on successful validation. Reject with 403 on missing/expired/unknown.
5. Validate every name in `required_fields` is present in the form dict and non-empty. Reject with 400 on missing.
6. Return the validated fields dict.

**Why:**

- **One place** is the entire value proposition. If the check logic lives anywhere else, one forgetful contributor ships a vulnerability. If it lives in a helper that every endpoint *must* call, static grep (and the extended `privacy-review` skill) can verify the invariant.
- The helper returns a dict so endpoints have typed access to the fields they care about.
- Writing the error response inside `_mutate` (instead of raising and catching in the endpoint) keeps endpoints linear: `fields = _mutate(...)`; `if fields is None: return`; proceed.
- Host check rejects DNS rebinding trivially — the browser sends the attacker's hostname in `Host`, we reject it.
- Origin check rejects cross-origin browser fetches that do include an Origin header (most of them).

**Alternatives considered:**

- **Decorator on each endpoint method.** Cute but Python decorators on `BaseHTTPRequestHandler` methods are fiddly (they need to preserve `self`, return type matters, and the pattern is rarer than an explicit call). Explicit call is clearer.
- **Middleware layer.** Would be natural if we used a framework. We don't. The explicit call is a middleware-of-one.
- **Check in `do_POST` dispatcher, then route to un-checked handlers.** Works but splits the invariant across the dispatcher and the handlers, making it easier to land a new handler that "doesn't need checking for some reason." Rejected.

### Decision 3: HTMX vendored, not CDN'd

**Chosen:** Commit `htmx.min.js` (v1.9.x, pinned) to `focusmonitor/static/htmx.min.js`. Add a `PROVENANCE.md` alongside it documenting the upstream URL, SHA256, and the date of the fetch. Serve via a new `GET /static/<filename>` route with an allowlist of `{"htmx.min.js"}`. The dashboard's `<head>` includes `<script src="/static/htmx.min.js" defer></script>`.

**Why:**

- CDN hosting (e.g., `https://unpkg.com/htmx.org@1.9.12`) would be an outbound network call every time the page loads — a direct violation of CLAUDE.md's network policy. Hard no.
- Installing htmx via pip (it has no official Python package) or npm (we have no node) would introduce a package manager we don't have.
- Vendoring as a single committed file is strictly the cleanest answer for this project: auditable, version-pinned by git SHA, reproducible, offline-friendly, privacy-friendly.
- An allowlist instead of `os.path.join(STATIC_DIR, filename)` makes path traversal impossible by construction. No `..`, no `/etc/passwd`, no scary parsing.

**Alternatives considered:**

- **Vanilla JS, no library.** Would work — the mutations are simple enough. But we'd reinvent form-submit-without-reload, partial-HTML-swap, and event delegation, and the vanilla JS would grow to match htmx's feature set over time. Vendoring htmx is ~14KB and zero lines of handwritten JS.
- **Alpine.js.** Similar weight to htmx but tilted toward client-side state. HTMX's "server returns HTML fragments" model is a better fit for our `render_*` helpers.
- **Hyperscript (htmx's sister library).** Not needed for this scope; basic htmx attributes cover everything.

### Decision 4: POST everywhere (no PUT/DELETE routing)

**Chosen:** Every mutation endpoint uses `POST`, including updates (`/api/planned-tasks/<name>`) and deletes (`/api/planned-tasks/<name>/delete`). The handler's `do_POST` method dispatches based on `self.path` with simple regex matching.

**Why:**

- `BaseHTTPRequestHandler` has separate methods for each verb. Adding `do_PUT`, `do_DELETE` gains us nothing except more dispatch code. One `do_POST` with path matching is clearer.
- HTML form elements only natively support GET and POST. HTMX can issue PUT/DELETE, but doing so requires setting a method attribute on every form, and the payoff is purely semantic.
- POST-only is a legitimate REST-ish style for this kind of app (Rails scaffolding used to do exactly this).

**Alternatives considered:**

- **Full REST (`do_PUT`, `do_DELETE`).** Purer but the router complexity and framework ceremony are not worth it for five endpoints.
- **Query-parameter based routing (`POST /api/planned-tasks?action=delete`).** Uglier, same benefits, rejected.

### Decision 5: Write endpoints return HTML fragments, not JSON

**Chosen:** Every mutation endpoint returns an HTML fragment — specifically, the re-rendered Planned Focus card and/or the re-rendered Discovered Activities card. HTMX's `hx-target` attribute points at the card's container `id`, and `hx-swap="outerHTML"` replaces the card in place.

**Why:**

- The server already has `render_planned_card` and `render_discovered_card`. Mutation endpoints can call them directly. No JSON serialization, no client-side templating, no duplication of the rendering logic in JS.
- Client stays dumb. All data lives on the server, formatted server-side, never transmitted as structured data. The privacy surface is smaller because the client never sees a JSON schema that could be used to infer internal structure.
- "HTML over the wire" is htmx's canonical pattern; swimming against it would mean writing more code.
- A mutation that affects both cards (e.g., promote) returns both fragments wrapped in an out-of-band swap (`hx-swap-oob`). HTMX handles the rest.

**Alternatives considered:**

- **JSON responses + client rendering.** Requires a JSON schema, a client template, and a build step or a lot of handwritten JS. Rejected.
- **Full page reload via redirect.** Works but loses the "feels instant" UX. Rejected.

### Decision 6: Atomic file writes via temp-file + `os.replace`

**Chosen:** All mutations to `planned_tasks.json` and `discovered_activities.json` use a `_write_json_atomic(path, data)` helper:

```
1. Write JSON to `path.with_suffix(path.suffix + ".tmp")`.
2. os.replace(tmp_path, path)
3. On any failure, remove the tmp file.
```

**Why:**

- A crash or power cut between steps 1 and 2 leaves the original file intact — there is no partial-write window.
- `os.replace` is atomic on POSIX and Windows (within the same filesystem), which is all we need for a file in `~/.focus-monitor/`.
- No file locking is needed. The dashboard writes serially on a single thread; there is no concurrent mutation path.

**Alternatives considered:**

- **Direct `open(path, "w")`.** Status quo. A crash mid-write corrupts the file. Users lose their plan.
- **`fcntl.flock` for cross-process locking.** Not needed — only the dashboard writes these files.
- **Append-only log with compaction.** Over-engineered for a file that mutates a handful of times per day.

### Decision 7: Inline forms, not modals

**Chosen:** "Add planned task" expands an inline form at the bottom of the Planned Focus card. "Edit" replaces a row with an inline form in place. "Delete" reveals a small confirm dialog *inside the row*. "Promote" on a discovery replaces the row with an inline form (with name and sample signals pre-filled) so the user can tweak before submitting.

No overlay modals. No full-screen takeovers. No new pages.

**Why:**

- Modals break the "one screen, glance, go" cadence. Inline expansion keeps everything where the user's eyes already are.
- Inline forms can be rendered as plain HTML fragments with no client-side state management. HTMX swaps them into the target and back out on submit/cancel.
- Rize's own UI for equivalent actions uses inline expansion, not modals. Matches the reference.

**Alternatives considered:**

- **Modal overlays.** Heavier visually, require JS or CSS tricks for open/close, and are the wrong choice aesthetically.
- **Side panel.** Same problem as modals, plus shifts the main content.

## Risks / Trade-offs

- **Risk: CSRF token store grows unbounded if mutations never happen but GETs keep firing.** Tokens are 1-hour TTL and we never prune. → **Mitigation:** `_mutate` also opportunistically sweeps expired entries from `_csrf_tokens` on every call (O(n) over the store, which is capped in practice by how often the dashboard auto-refreshes — maybe a few hundred). A background sweep is not worth the thread.

- **Risk: Tokens leak via browser history / shoulder-surfing.** The token is in the page HTML, not in a URL, so it does not appear in `~/.bash_history`, `~/Library/Safari/History.db`, or referrer headers. Not a meaningful risk for this threat model.

- **Risk: A privacy-first user disables JS entirely.** The read-only dashboard still works (Change 1 is JS-free). The mutation UI does not. → **Mitigation:** documented in the spec as explicit. Users who want management must enable JS on localhost:9876, which is a targeted permission and reasonable.

- **Risk: A concurrent write (e.g., the monitor updating `discovered_activities.json` mid-mutation).** The monitor calls `update_discovered_activities` from its analysis thread; the dashboard's mutation handlers call the same file from the HTTP thread. Two writers. → **Mitigation:** both use `_write_json_atomic`, which is safe against crashes but *not* safe against concurrent read-modify-write sequences (TOCTOU). In practice: the monitor writes every ~30 minutes and mutations are clicked by a human, so the collision window is vanishingly small. Accepted as a known limitation; documented in the risks. If it ever bites someone, the fix is a `threading.Lock()` wrapping both read-modify-write paths.

- **Risk: htmx version drift.** We vendor a specific version. Future security advisories in htmx won't reach us unless we actively update. → **Mitigation:** the PROVENANCE.md file names the exact version and the fetch date. An annual review-and-update is a reasonable cadence; htmx's surface area is tiny compared to React/Vue, so drift risk is lower than a framework would have.

- **Risk: An endpoint is added in a future change that bypasses `_mutate`.** → **Mitigation:** the extended `privacy-review` skill explicitly grep-checks that every `do_POST` code path references `_mutate` before writing. This is a soft enforcement (the skill is a review, not a gate), but it's the same enforcement mechanism the privacy invariants already use successfully.

- **Risk: HTML fragment responses leak internal state via rendering.** All untrusted fields are HTML-escaped by the existing `render_*` helpers (tested in Change 1's test_dashboard_render.py). → **Mitigation:** new fields (form values, button labels) flow through `html.escape` the same way. New tests assert escaping of adversarial inputs in form responses.

- **Privacy trade-off:** None, provided the implementation matches the design. The `_mutate` helper exists specifically to guarantee no write endpoint ships without Host/Origin/CSRF checks. The vendored htmx file exists specifically to avoid any outbound network call. The `privacy-review` skill extension exists specifically to prevent regression. Recording per the design-phase privacy rule: the only new surface added is an inbound POST surface on `127.0.0.1:9876`, which is unchanged in threat model if and only if `_mutate` is called on every mutation path. That is an invariant the tests and the skill both enforce.

- **Trade-off:** Ships meaningfully more code than Change 1. ~400 lines added to dashboard.py, ~150 to tasks.py, ~500 test assertions, a vendored JS file, and a skill extension. That's the cost of adding a write surface to a previously read-only server. There is no shortcut that doesn't compromise the security story.
