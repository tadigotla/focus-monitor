## ADDED Requirements

### Requirement: Dashboard served over HTTP
The system SHALL serve the dashboard HTML over HTTP on a configurable local port (default: 9876), bound to 127.0.0.1 only.

#### Scenario: Dashboard accessible at localhost
- **WHEN** the dashboard server is running
- **THEN** a GET request to `http://localhost:9876/` returns the dashboard HTML with status 200

#### Scenario: Dashboard shows current data
- **WHEN** a user visits the dashboard URL after analyses have been logged
- **THEN** the page displays data from the current day's activity log, freshly queried from the database

### Requirement: Auto-refresh
The dashboard HTML SHALL include an auto-refresh mechanism that reloads the page at a configurable interval (default: 60 seconds).

#### Scenario: Page auto-refreshes
- **WHEN** the dashboard page is open in a browser
- **THEN** the page automatically reloads after the configured refresh interval

#### Scenario: Custom refresh interval
- **WHEN** the config contains `"dashboard_refresh_sec": 30`
- **THEN** the page auto-refreshes every 30 seconds

### Requirement: Server starts with monitor
The dashboard server SHALL start automatically as a daemon thread when `monitor.py` runs, so no separate command is needed.

#### Scenario: Monitor starts server
- **WHEN** the user starts the monitor
- **THEN** the dashboard server starts on the configured port
- **AND** the startup banner prints the dashboard URL

#### Scenario: Monitor stops, server stops
- **WHEN** the monitor process exits
- **THEN** the dashboard server thread terminates automatically (daemon thread)

### Requirement: Configurable port
The system SHALL read a `dashboard_port` key from the config file (default: 9876).

#### Scenario: Custom port
- **WHEN** the config contains `"dashboard_port": 8080`
- **THEN** the dashboard server binds to port 8080

#### Scenario: Port conflict
- **WHEN** the configured port is already in use
- **THEN** the system prints an error message suggesting to change the port in config
- **AND** the monitor continues running without the dashboard server

### Requirement: Local-only binding
The dashboard server SHALL bind to 127.0.0.1 only, not to 0.0.0.0 or any external interface.

#### Scenario: External access blocked
- **WHEN** a request comes from a non-local IP
- **THEN** the connection is refused because the server only listens on 127.0.0.1

### Requirement: Discovered activities section
The dashboard SHALL render a "Discovered Activities" section that displays every entry from `~/.focus-monitor/discovered_activities.json`, sorted by `last_seen` descending.

Each entry SHALL display the activity `name`, `count`, `first_seen` date, `last_seen` date, `sample_signals`, and a visual indicator when `promoted` is `true`.

#### Scenario: Activities file populated
- **WHEN** `discovered_activities.json` contains one or more entries
- **AND** a user requests the dashboard page
- **THEN** the response includes a section listing each activity by name with its count, first/last seen timestamps, and sample signals
- **AND** entries are ordered with the most recently seen first

#### Scenario: Promoted entries visually distinguished
- **WHEN** an activity has `promoted: true`
- **THEN** its rendered entry is visually distinguished from non-promoted entries (e.g., a "promoted" badge or distinct styling)

#### Scenario: Activities file missing
- **WHEN** `discovered_activities.json` does not exist
- **THEN** the Discovered Activities section renders an empty-state message (e.g., "No activities discovered yet") instead of an error
- **AND** the rest of the dashboard still renders normally

#### Scenario: Activities file malformed
- **WHEN** `discovered_activities.json` exists but cannot be parsed as JSON
- **THEN** the Discovered Activities section renders an empty-state message
- **AND** the dashboard request still returns status 200 with the timeline and stats intact

#### Scenario: Activities file empty
- **WHEN** `discovered_activities.json` contains `{"activities": []}`
- **THEN** the Discovered Activities section renders the same empty-state message as the missing-file case

### Requirement: Light-theme-first design system

The dashboard SHALL use a light color palette by default and SHALL provide a dark palette via the `prefers-color-scheme: dark` media query. No manual theme toggle, no config key, and no server-side theme logic SHALL be introduced. The dark palette SHALL be implemented as property re-declaration of the same CSS custom properties used by the light palette; no duplicate CSS rules or duplicate HTML templates SHALL exist for the two themes.

#### Scenario: Default light rendering
- **WHEN** a user with no OS dark-mode preference opens the dashboard
- **THEN** the page renders with a light background (near-white surfaces, dark neutral text)
- **AND** all interactive elements use the light-palette tokens

#### Scenario: OS dark preference honored
- **WHEN** a user whose OS is set to dark mode opens the dashboard
- **THEN** the page renders with the dark palette via `prefers-color-scheme: dark` overrides
- **AND** all readable text maintains at least 4.5:1 contrast against its background

#### Scenario: No theme toggle exposed
- **WHEN** inspecting the dashboard UI
- **THEN** there SHALL NOT be a theme toggle button, switch, or config key
- **AND** the only way to change themes is via OS preference

### Requirement: Design tokens as CSS custom properties

The dashboard stylesheet SHALL declare all colors, spacing, border radii, font sizes, font weights, and shadows as CSS custom properties (`--*`) in a single `:root` block. All component-level CSS rules SHALL reference these tokens via `var(--token-name)` and SHALL NOT hardcode hex values, px units for the 4px spacing grid, or font sizes.

The dark palette SHALL be implemented as a `@media (prefers-color-scheme: dark)` block that re-declares the color tokens only. Non-color tokens (spacing, radii, type scale, shadows) SHALL remain stable across themes.

#### Scenario: Tokens declared once
- **WHEN** the dashboard stylesheet is loaded
- **THEN** there is exactly one `:root { ... }` block declaring the full set of tokens
- **AND** no component rule hardcodes a color value outside of the two `:root` / `@media` blocks

#### Scenario: Color token set
- **WHEN** inspecting the token declarations
- **THEN** the following color tokens SHALL exist (non-exhaustive minimum set):
  - `--color-bg`, `--color-surface`, `--color-surface-raised`
  - `--color-border`
  - `--color-text`, `--color-text-muted`, `--color-text-subtle`
  - `--color-accent`, `--color-accent-hover`
  - `--color-score-good`, `--color-score-mid`, `--color-score-bad`
  - `--color-distraction`, `--color-planned`

#### Scenario: Non-color token set
- **WHEN** inspecting the token declarations
- **THEN** the following non-color tokens SHALL exist:
  - Spacing scale: `--space-1` through `--space-8` (4px base unit)
  - Radii: `--radius-sm`, `--radius-md`, `--radius-lg`
  - Shadows: `--shadow-sm`, `--shadow-md`
  - Type sizes: at minimum `--font-size-xs`, `--font-size-sm`, `--font-size-base`, `--font-size-lg`, `--font-size-xl`, `--font-size-2xl`, `--font-size-5xl`
  - Weights: `--font-weight-regular`, `--font-weight-medium`, `--font-weight-semibold`
  - Family: `--font-family-sans`

### Requirement: System font stack, no web fonts

The dashboard SHALL use a system font stack for all text and SHALL NOT load any web fonts from external origins (Google Fonts, any CDN) or from self-hosted `@font-face` files. The font stack SHALL begin with `-apple-system` and end with a generic `sans-serif` fallback.

Numeric displays (focus score, counts, durations) SHALL use `font-variant-numeric: tabular-nums` (or the equivalent `font-feature-settings: "tnum"`) so numeric columns align visually.

#### Scenario: No external font requests
- **WHEN** the dashboard HTML is loaded
- **THEN** the page emits zero HTTP requests to any host other than `localhost` / `127.0.0.1`
- **AND** no `@font-face` rule references an external URL
- **AND** no `<link rel="stylesheet" href="https://fonts.googleapis.com/...">` tag is present

#### Scenario: System stack declared
- **WHEN** inspecting the `body` rule (or the `--font-family-sans` token)
- **THEN** the declared family begins with `-apple-system` and terminates with a generic `sans-serif` fallback

#### Scenario: Tabular numbers on numeric displays
- **WHEN** inspecting the rendered focus score, analysis count, nudge count, or top-apps duration column
- **THEN** the element uses `font-variant-numeric: tabular-nums` (or the equivalent feature-settings) either directly or via an inherited class

### Requirement: Single-screen layout with four visual zones

The dashboard SHALL render a single-screen layout with the following zones in this order, top to bottom:

1. **Header zone** — project name on the left, current date and time-range toggle on the right.
2. **Hero zone** — a large focus-score card (big numeric display, score bucket coloring) and today's timeline strip (inline SVG).
3. **Primary zone** — a Planned Focus card and a Discovered Activities card, side by side.
4. **Secondary zone** — a Top Apps card and a Recent Nudges card, side by side.

No sidebar, no top-nav, no breadcrumbs, no tabs. The layout SHALL be a centered, max-width container with generous whitespace between zones.

#### Scenario: Zone order in the rendered HTML
- **WHEN** the dashboard HTML is rendered
- **THEN** the four zones appear in the order above
- **AND** each zone is a semantic `<section>` or equivalent element

#### Scenario: No navigation chrome
- **WHEN** inspecting the rendered page
- **THEN** there SHALL NOT be a `<nav>` sidebar, a top-nav bar with multiple pages, tabs, or breadcrumbs
- **AND** the only navigation element is the time-range toggle in the header

#### Scenario: Hero zone cards
- **WHEN** inspecting the hero zone
- **THEN** it contains exactly two direct children: the focus-score card and the timeline strip
- **AND** the focus-score card displays the average focus score for the current time range as a large number

### Requirement: Inline SVG timeline strip

The dashboard SHALL render the timeline as an inline `<svg>` element embedded in the HTML, generated server-side from the current time-range's `activity_log` rows. Each time bucket SHALL be rendered as a `<rect>` whose fill is determined by the focus-score bucket of that tick (good/mid/bad). Hour labels SHALL be rendered as `<text>` elements beneath the rects.

The SVG SHALL NOT require any JavaScript to render or interact with. No hover tooltips, no click handlers, no animations are required in this change.

#### Scenario: Timeline SVG structure
- **WHEN** the dashboard is rendered for a day with at least one analysis row
- **THEN** the timeline zone contains an `<svg>` element with one `<rect>` per time bucket
- **AND** each `<rect>` has a `fill` referencing a score-bucket token (`var(--color-score-good|mid|bad)`)

#### Scenario: Timeline empty state
- **WHEN** the current time range has zero analysis rows
- **THEN** the timeline zone renders an empty-state message (e.g., "No activity recorded yet today")
- **AND** the dashboard returns status 200

#### Scenario: No JavaScript required
- **WHEN** a user loads the dashboard with JavaScript disabled
- **THEN** the timeline still renders with correct colors and labels
- **AND** no feature of the dashboard requires JavaScript to display

### Requirement: Time-range toggle

The dashboard SHALL provide a time-range toggle in the header with exactly three options: **Today**, **Yesterday**, **Last 7 days**. The default (when no range is specified) SHALL be Today. The toggle SHALL be implemented as plain `<a>` links with a `range` query parameter — no JavaScript, no form submission, no client-side state.

The server handler SHALL read the `range` query parameter, convert it to a date range, and apply it to the existing SQLite queries that currently hardcode today's date. If the parameter is missing or invalid, the handler SHALL default to Today.

#### Scenario: Default to today
- **WHEN** a user requests `GET /` with no query parameters
- **THEN** the page renders with data from the current calendar day
- **AND** the "Today" option in the toggle is marked active

#### Scenario: Yesterday view
- **WHEN** a user requests `GET /?range=yesterday`
- **THEN** the page renders with data from the previous calendar day
- **AND** the "Yesterday" option in the toggle is marked active

#### Scenario: Seven-day view
- **WHEN** a user requests `GET /?range=7d`
- **THEN** the page renders with data from the last seven calendar days (inclusive of today)
- **AND** the "Last 7 days" option in the toggle is marked active

#### Scenario: Invalid range falls back to today
- **WHEN** a user requests `GET /?range=garbage`
- **THEN** the page renders with data from the current calendar day
- **AND** the response status is 200 (no error page)

### Requirement: Templated rendering via `string.Template`

The dashboard server SHALL render HTML using `string.Template` from the Python standard library (not `str.replace`, not f-string concatenation of large blobs, not a third-party template engine). The template SHALL use named placeholders (`$name` style) and SHALL be substituted in a single `template.substitute(...)` call with a dict produced by the `render_*` helpers.

No third-party templating library (Jinja2, Mako, etc.) SHALL be introduced.

#### Scenario: Named placeholders resolved
- **WHEN** `build_dashboard()` is called for a populated day
- **THEN** the returned HTML contains zero literal `$name` placeholders
- **AND** `string.Template.substitute` raises a `KeyError` at render time if any placeholder is missing from the substitution dict

#### Scenario: No third-party template engine
- **WHEN** inspecting the imports of [focusmonitor/dashboard.py](focusmonitor/dashboard.py)
- **THEN** the only templating mechanism imported is `string.Template` from the stdlib
- **AND** there is no `import jinja2`, `import mako`, or equivalent

### Requirement: Render helpers for each card

The dashboard module SHALL expose module-level `render_*` helper functions — at minimum: `render_header`, `render_score_card`, `render_timeline`, `render_planned_card`, `render_discovered_card`, `render_apps_card`, `render_nudges_card`. Each helper SHALL take already-loaded data (parsed rows, lists, dicts) as arguments and SHALL return an HTML fragment as a string. Helpers SHALL NOT query the database directly; `build_dashboard` is the single orchestrator that queries once and passes data into the helpers.

Each helper SHALL HTML-escape untrusted data (user-provided task names, window titles, etc.) using `html.escape` before embedding into the fragment.

#### Scenario: Helpers are importable and independently callable
- **WHEN** a test imports `render_discovered_card` from `focusmonitor.dashboard`
- **AND** calls it with a fixed list of activity dicts
- **THEN** it receives an HTML fragment string containing each activity name

#### Scenario: Helpers HTML-escape untrusted input
- **WHEN** `render_discovered_card` receives an activity whose name contains `<script>alert(1)</script>`
- **THEN** the returned fragment contains `&lt;script&gt;` rather than the raw tag
- **AND** the rendered dashboard does not execute the script when opened in a browser

#### Scenario: Helpers do not open database connections
- **WHEN** any `render_*` helper is called in a test
- **THEN** it does not import or invoke `sqlite3` inside its body
- **AND** all data is passed in as arguments

### Requirement: Preserve existing read behavior

All existing dashboard-server requirements — HTTP serving on a configurable port, 127.0.0.1-only binding, auto-refresh via meta tag, daemon-thread lifecycle, the discovered-activities section with its empty-state handling — SHALL remain satisfied after this change. The visual redesign SHALL NOT weaken, remove, or alter the semantics of any pre-existing requirement under the `dashboard-server` capability.

#### Scenario: Port and binding unchanged
- **WHEN** the redesigned dashboard starts
- **THEN** it binds to 127.0.0.1 on the port from `dashboard_port` (default 9876)
- **AND** a request from a non-loopback interface is refused

#### Scenario: Auto-refresh preserved
- **WHEN** the redesigned dashboard HTML is loaded
- **THEN** the page still includes an auto-refresh mechanism driven by `dashboard_refresh_sec`
- **AND** the page reloads itself on that interval without user interaction

#### Scenario: Discovered activities empty states preserved
- **WHEN** `discovered_activities.json` is missing, malformed, or contains an empty list
- **THEN** the Discovered Activities card still renders an empty-state message
- **AND** the rest of the dashboard continues to render normally

### Requirement: Privacy posture preserved

The redesign SHALL NOT introduce any new network request, outbound URL, web font, CDN reference, or external dependency. All fonts, icons, and stylesheets SHALL be inline or served from `localhost`. No new Python packages SHALL be added to the project. No new `@font-face` rules SHALL reference external URLs.

#### Scenario: No outbound network calls
- **WHEN** the dashboard HTML is rendered and opened in a browser
- **THEN** the browser makes zero HTTP requests to any host other than the local dashboard server

#### Scenario: No new Python dependencies
- **WHEN** inspecting the imports of [focusmonitor/dashboard.py](focusmonitor/dashboard.py) after this change
- **THEN** every imported module is either from the Python standard library or from the existing `focusmonitor` package
- **AND** there is no new entry in any `requirements.txt`, `pyproject.toml`, or equivalent

### Requirement: Single mutation choke-point

The dashboard server SHALL route every write request through a single `_mutate(handler, required_fields)` helper function. No mutation handler SHALL perform its side effects without first calling `_mutate` and receiving a non-`None` validated-fields dict.

`_mutate` SHALL, in order:

1. Validate the `Host` request header equals `localhost:<port>` or `127.0.0.1:<port>` for the server's configured port. On mismatch, SHALL send HTTP 403 and return `None`.
2. Validate the `Origin` request header, when present, matches the same Host values. Absent Origin is permitted; present-but-mismatched SHALL send HTTP 403 and return `None`.
3. Read the `Content-Length` bytes from the request body, parse as `application/x-www-form-urlencoded`, and fail with HTTP 400 on missing length or unparseable body.
4. Validate a `csrf` field in the parsed form. The value MUST exist in the server's in-memory CSRF token store and MUST NOT be expired. On success, SHALL atomically remove the token from the store so the same value cannot be used twice. On failure, SHALL send HTTP 403 and return `None`.
5. Validate every name listed in `required_fields` is present and non-empty in the form. On failure, SHALL send HTTP 400 and return `None`.
6. Return the validated fields dict on success.

#### Scenario: Happy path returns fields dict
- **WHEN** a request arrives with a valid Host, valid Origin, fresh CSRF token, and all required form fields
- **THEN** `_mutate` returns a dict with the required fields
- **AND** the CSRF token is removed from the store

#### Scenario: Wrong Host rejected
- **WHEN** a request arrives with `Host: evil.example.com`
- **THEN** `_mutate` responds with HTTP 403
- **AND** returns `None`
- **AND** no file on disk is modified

#### Scenario: Wrong Origin rejected
- **WHEN** a request arrives with `Host: localhost:9876` and `Origin: https://evil.example.com`
- **THEN** `_mutate` responds with HTTP 403
- **AND** returns `None`

#### Scenario: Missing Origin allowed
- **WHEN** a request arrives with a valid Host and no Origin header
- **AND** has a fresh CSRF token and all required fields
- **THEN** `_mutate` succeeds and returns the fields dict

#### Scenario: Missing CSRF token rejected
- **WHEN** a request arrives with a valid Host/Origin and required fields but no `csrf` field
- **THEN** `_mutate` responds with HTTP 403
- **AND** returns `None`

#### Scenario: Expired CSRF token rejected
- **WHEN** a request carries a CSRF token whose expiry has passed
- **THEN** `_mutate` responds with HTTP 403
- **AND** returns `None`

#### Scenario: Replay attack prevented
- **WHEN** the same CSRF token is used twice in sequence
- **THEN** the first call succeeds and consumes the token
- **AND** the second call responds with HTTP 403

#### Scenario: Missing required field rejected
- **WHEN** a request has valid headers and a valid CSRF token but is missing a required field (e.g., `name`)
- **THEN** `_mutate` responds with HTTP 400
- **AND** returns `None`
- **AND** no file on disk is modified

### Requirement: CSRF token lifecycle

The dashboard server SHALL generate a fresh CSRF token on every `GET /` response using `secrets.token_urlsafe(32)` (or equivalent source of cryptographic randomness yielding at least 256 bits of entropy). Tokens SHALL be stored in a module-level dict keyed by token value with a 1-hour TTL. Tokens SHALL be embedded in the rendered HTML as both a hidden form field (for non-htmx submissions) and an `hx-headers` attribute on the `<body>` (for htmx submissions).

The server SHALL opportunistically prune expired tokens from the store on every `_mutate` invocation to prevent unbounded growth.

#### Scenario: Fresh token on each GET
- **WHEN** two `GET /` requests arrive in sequence
- **THEN** the rendered HTML of each contains a different CSRF token value
- **AND** both tokens are present in the server-side store

#### Scenario: Token embedded in HTML
- **WHEN** inspecting the rendered dashboard HTML
- **THEN** the HTML contains a hidden input named `csrf` with a value
- **AND** the `<body>` tag has an `hx-headers` attribute containing `X-CSRF-Token`
- **AND** both values are equal

#### Scenario: Token TTL enforced
- **WHEN** a token is older than 1 hour at the time of a mutation request
- **THEN** `_mutate` treats the token as expired and rejects the request

#### Scenario: Expired tokens pruned
- **WHEN** `_mutate` is called and the token store contains expired entries
- **THEN** expired entries are removed from the store
- **AND** the call proceeds to validate the incoming token against the remaining (non-expired) entries

### Requirement: Static file serving with allowlist

The dashboard server SHALL serve files from `focusmonitor/static/` via `GET /static/<filename>`. The set of servable filenames SHALL be a compile-time allowlist containing at least `htmx.min.js`. Requests for filenames not in the allowlist SHALL respond with HTTP 404. The server SHALL NOT construct the disk path via user-controlled string concatenation or `os.path.join` with untrusted input.

#### Scenario: Allowlisted file served
- **WHEN** a client requests `GET /static/htmx.min.js`
- **THEN** the server responds with HTTP 200
- **AND** the response body is the contents of `focusmonitor/static/htmx.min.js`
- **AND** the response has `Content-Type: application/javascript`

#### Scenario: Non-allowlisted file denied
- **WHEN** a client requests `GET /static/secrets.txt`
- **THEN** the server responds with HTTP 404

#### Scenario: Path traversal denied
- **WHEN** a client requests `GET /static/../config.py` or `GET /static/..%2Fconfig.py`
- **THEN** the server responds with HTTP 404
- **AND** no file outside `focusmonitor/static/` is read or leaked

#### Scenario: No external fetch
- **WHEN** the dashboard is rendered and loaded in a browser
- **THEN** the browser makes no HTTP request to any host other than the local dashboard server
- **AND** htmx is served from `http://localhost:<port>/static/htmx.min.js`

### Requirement: Vendored HTMX with pinned provenance

The repository SHALL contain `focusmonitor/static/htmx.min.js` as a committed file (not a symlink, not a submodule, not a downloaded-at-runtime blob). A `focusmonitor/static/PROVENANCE.md` file SHALL name the upstream source URL, the pinned version, and the fetch date. No code path SHALL fetch htmx from a remote URL at runtime or at install time.

#### Scenario: HTMX file is committed
- **WHEN** inspecting the git index
- **THEN** `focusmonitor/static/htmx.min.js` is a regular file tracked by git
- **AND** its size is within expected bounds for htmx (between 5KB and 100KB)

#### Scenario: Provenance documented
- **WHEN** inspecting `focusmonitor/static/PROVENANCE.md`
- **THEN** it names the upstream URL, the pinned version string, and the fetch date

#### Scenario: No runtime fetch
- **WHEN** grepping the repository for URLs containing `htmx` or `unpkg` or `cdnjs`
- **THEN** there is no outbound fetch of htmx at runtime
- **AND** any reference to htmx URLs is limited to PROVENANCE.md and documentation

### Requirement: Plan-management endpoints

The dashboard server SHALL expose the following mutation endpoints under `POST /api/...`. Every endpoint SHALL call `_mutate` as its first operation and SHALL return an HTML fragment (not JSON, not a redirect) representing the re-rendered affected cards.

| Endpoint | Required fields | Effect |
|---|---|---|
| `POST /api/planned-tasks` | `name`, `csrf` | Create a planned task. `signals` and `notes` optional. Appends to `planned_tasks.json`. Returns re-rendered Planned Focus card. |
| `POST /api/planned-tasks/<name>` | `csrf` | Update the named planned task's `signals` and `notes`. Returns re-rendered Planned Focus card. |
| `POST /api/planned-tasks/<name>/delete` | `csrf` | Delete the named planned task. Returns re-rendered Planned Focus card. |
| `POST /api/discoveries/<name>/promote` | `csrf` | Create a planned task from the discovered entry's sample signals, mark the discovery as `promoted: true`. Returns re-rendered Planned and Discovered cards (via htmx out-of-band swap). |
| `POST /api/discoveries/<name>/hide` | `csrf` | Set `hidden: true` on the discovered entry. Returns re-rendered Discovered Activities card. |

Task names and discovery names in URL paths SHALL be URL-decoded and matched case-insensitively against the stored entries. A request targeting a non-existent entry SHALL respond with HTTP 404 (via `_mutate`'s error-response helpers).

#### Scenario: Create planned task
- **WHEN** a valid POST to `/api/planned-tasks` with `name="foo"` arrives
- **THEN** `planned_tasks.json` gains a new entry with `name: "foo"`
- **AND** the response body is the re-rendered Planned Focus card fragment
- **AND** the fragment contains "foo"

#### Scenario: Update existing task
- **WHEN** a valid POST to `/api/planned-tasks/foo` with `signals="bar,baz"` arrives
- **AND** a task named "foo" exists
- **THEN** the "foo" entry's `signals` is updated to `["bar", "baz"]`
- **AND** the response is the re-rendered Planned Focus card fragment

#### Scenario: Delete existing task
- **WHEN** a valid POST to `/api/planned-tasks/foo/delete` arrives
- **AND** a task named "foo" exists
- **THEN** the "foo" entry is removed from `planned_tasks.json`
- **AND** the response is the re-rendered Planned Focus card fragment

#### Scenario: Promote a discovered activity
- **WHEN** a valid POST to `/api/discoveries/sanskrit-tool/promote` arrives
- **AND** a discovered activity named "Sanskrit Tool" exists (case-insensitive match)
- **THEN** `planned_tasks.json` gains a new entry with the discovered name and its `sample_signals` as `signals`
- **AND** the discovered entry's `promoted` field is set to `true`
- **AND** the response contains BOTH the re-rendered Planned card and the re-rendered Discovered card (via htmx out-of-band swap)

#### Scenario: Hide a discovered activity
- **WHEN** a valid POST to `/api/discoveries/foo/hide` arrives
- **AND** a discovered activity named "foo" exists
- **THEN** the discovered entry's `hidden` field is set to `true`
- **AND** the re-rendered Discovered Activities card no longer shows "foo"

#### Scenario: Target entry not found
- **WHEN** a valid POST to `/api/planned-tasks/nonexistent/delete` arrives
- **AND** no task named "nonexistent" exists
- **THEN** the server responds with HTTP 404
- **AND** `planned_tasks.json` is not modified

### Requirement: Inline-form plan-management UI

The rendered dashboard HTML SHALL include inline-form UI elements powered by HTMX attributes:

- The Planned Focus card SHALL include an "Add planned task" affordance that expands into an inline form with fields `name`, `signals`, and `notes`, and submits via `hx-post="/api/planned-tasks"` with `hx-target` pointing at the Planned Focus card and `hx-swap="outerHTML"`.
- Each planned task row SHALL include inline edit and delete controls. Edit replaces the row with an inline form; delete reveals an inline confirmation control that submits the delete.
- Each visible discovered activity row SHALL include a "Promote" button and a "Hide" button using the `/api/discoveries/<name>/promote` and `/api/discoveries/<name>/hide` endpoints respectively.
- There SHALL NOT be any modal dialog, full-screen overlay, or separate page for any of the above; all management UI is inline.

The UI SHALL NOT emit any handwritten JavaScript beyond what HTMX attributes provide. No `<script>` tag other than the vendored htmx file SHALL be present.

#### Scenario: Add form present and wired to endpoint
- **WHEN** the dashboard is rendered with at least one planned task (or none)
- **THEN** the Planned Focus card contains an `hx-post="/api/planned-tasks"` element
- **AND** the form contains fields `name`, `signals`, `notes`, `csrf`

#### Scenario: Delete uses inline confirmation
- **WHEN** inspecting the rendered planned task row markup
- **THEN** the delete affordance does NOT use `window.confirm` or any other browser dialog
- **AND** the delete affordance reveals an inline confirm control in the same row

#### Scenario: Discovered row has promote and hide controls
- **WHEN** inspecting a visible discovered activity row
- **THEN** it contains an element with `hx-post="/api/discoveries/<name>/promote"`
- **AND** an element with `hx-post="/api/discoveries/<name>/hide"`
- **AND** both elements include the CSRF token

#### Scenario: No handwritten script
- **WHEN** inspecting the rendered dashboard HTML
- **THEN** the only `<script>` element in the page has `src="/static/htmx.min.js"`
- **AND** no inline `<script>` block is present

### Requirement: Privacy posture preserved for writes

The plan-management endpoints SHALL NOT introduce any new outbound network call, new external dependency, new Python package, CDN reference, or third-party script. HTMX SHALL be served from the same-origin `localhost:<port>` server. The dashboard SHALL continue to bind only to `127.0.0.1`.

#### Scenario: No new outbound surface
- **WHEN** the dashboard is rendered and mutations are performed
- **THEN** the browser and the server make zero HTTP requests to any host other than `localhost` / `127.0.0.1`

#### Scenario: Bind address unchanged
- **WHEN** the dashboard server starts
- **THEN** it binds to `127.0.0.1` on the configured port
- **AND** a request from a non-loopback interface is refused

#### Scenario: No new Python packages
- **WHEN** inspecting the project's dependencies
- **THEN** no new entry has been added to `requirements.txt`, `setup.py`, or `pyproject.toml`
- **AND** `focusmonitor/dashboard.py` imports only from the Python standard library and from `focusmonitor.*`

### Requirement: Session timeline as primary view
The dashboard's primary content area SHALL render a **session timeline**: a vertically-ordered list of session entries from the `sessions` table for the active time range, ordered most-recent-first. Each entry SHALL display:

- The time range (`start` – `end`)
- The session's `kind` (one of `session | unclear | away`) and, for sessions, the `task` name (or "Unclear" when `task` is null)
- An indicator for `boundary_confidence` and a separate indicator for `name_confidence`
- The session's `cycle_count` and `dip_count` when greater than zero
- An expandable evidence drawer that, when expanded, lists the aggregated evidence signals
- Inline ✏️ (correct) and ✓ (confirm) controls

`away` and `unclear` entries SHALL render in the same timeline list with appropriate visual distinction (e.g. greyed background, italic label) and SHALL NOT show ✓ controls — only ✏️.

The legacy per-cycle activity-log view SHALL be retrievable for diagnostics (e.g. via a query parameter) but SHALL NOT be the default surface.

#### Scenario: Sessions rendered as primary list
- **WHEN** the dashboard is rendered for a day with at least one session row
- **THEN** the primary content area contains one DOM element per session ordered most-recent-first
- **AND** each session element shows the time range, task name (or "Unclear"), and confidence indicators

#### Scenario: Session evidence drawer
- **WHEN** the user expands a session's evidence drawer
- **THEN** the drawer renders the session's aggregated evidence as a list of `signal` strings with their `weight`
- **AND** no JavaScript beyond htmx is required to toggle the drawer

#### Scenario: Away entries rendered distinctly
- **WHEN** the timeline includes an `away` entry from AW afk data
- **THEN** the entry is visually distinguished from active sessions
- **AND** the entry has no ✓ control
- **AND** the entry shows the time range only (no task name)

#### Scenario: Unclear entries rendered with correction control
- **WHEN** the timeline includes an `unclear` entry
- **THEN** the entry shows "Unclear" as its label
- **AND** the entry has a ✏️ correction control
- **AND** the entry has no ✓ control

#### Scenario: Confidence indicators visible
- **WHEN** inspecting any session entry
- **THEN** there are two distinct visual elements representing `boundary_confidence` and `name_confidence`
- **AND** their visual styling reflects the `low | medium | high` value

### Requirement: Session correction and confirmation endpoints
The dashboard server SHALL expose two new mutation endpoints, both routed through the existing `_mutate` helper for CSRF, Host/Origin, and field validation:

| Endpoint | Required fields | Effect |
|---|---|---|
| `POST /api/sessions/<session_id>/correct` | `csrf`, `user_kind`, optional `user_task`, optional `user_note` | Inserts a `corrections` row with `user_verdict='corrected'` for the named session via the corrections-loop write API. Returns the re-rendered session row. |
| `POST /api/sessions/<session_id>/confirm` | `csrf` | Inserts a `corrections` row with `user_verdict='confirmed'` for the named session via the corrections-loop write API. Returns the re-rendered session row. |

The `user_kind` field SHALL accept exactly the set `{on_planned_task, thinking_offline, meeting, break, other}`. Any other value SHALL produce HTTP 400.

A request targeting a non-existent `session_id` SHALL respond with HTTP 404 (via `_mutate`'s error helpers). Neither endpoint SHALL bypass the CSRF, Host, or Origin checks. Neither endpoint SHALL introduce any new outbound network call.

#### Scenario: Correct a session — happy path
- **WHEN** a valid POST to `/api/sessions/42/correct` arrives with `user_kind=on_planned_task`, `user_task="auth refactor"`, and a fresh CSRF token
- **THEN** a new row is inserted into `corrections` with `entry_kind='session'`, `entry_id=42`, `user_verdict='corrected'`, `user_kind='on_planned_task'`, `user_task='auth refactor'`
- **AND** the response body is the re-rendered HTML for that session entry
- **AND** the CSRF token is consumed exactly once

#### Scenario: Confirm a session — happy path
- **WHEN** a valid POST to `/api/sessions/42/confirm` arrives with a fresh CSRF token
- **THEN** a new row is inserted into `corrections` with `entry_kind='session'`, `entry_id=42`, `user_verdict='confirmed'`, `user_kind` defaulting to `on_planned_task` (or to the session's existing classification kind)
- **AND** the response body is the re-rendered HTML for that session entry

#### Scenario: Invalid user_kind rejected
- **WHEN** a POST to `/api/sessions/42/correct` arrives with `user_kind="something_made_up"`
- **THEN** the server responds with HTTP 400
- **AND** no row is inserted into `corrections`

#### Scenario: Non-existent session rejected
- **WHEN** a POST to `/api/sessions/9999/correct` arrives but no session with id 9999 exists
- **THEN** the server responds with HTTP 404
- **AND** no row is inserted into `corrections`

#### Scenario: Missing CSRF rejected
- **WHEN** a POST to `/api/sessions/42/correct` arrives without a `csrf` field
- **THEN** the server responds with HTTP 403 via the existing `_mutate` helper
- **AND** no row is inserted into `corrections`

#### Scenario: Wrong Host rejected
- **WHEN** a POST to `/api/sessions/42/correct` arrives with `Host: evil.example.com`
- **THEN** the server responds with HTTP 403
- **AND** no row is inserted into `corrections`

### Requirement: Inline correction modal as part of session row
Each session row in the rendered dashboard HTML SHALL include an inline correction affordance that, when activated (e.g. by clicking ✏️), reveals an inline form (NOT a modal dialog or full-screen overlay) within the same row. The form SHALL include:

- A `user_kind` selector with exactly five options: "Working on a task", "Thinking / reading offline", "Meeting (no screenshare)", "Break / lunch", "Something else"
- A `user_task` text input that becomes relevant when `user_kind` is `on_planned_task` or `thinking_offline` (the form MAY hide it for the other kinds)
- An optional `user_note` text input
- Hidden `csrf` field

The form SHALL submit via `hx-post="/api/sessions/<session_id>/correct"` with `hx-target` pointing at the session row and `hx-swap="outerHTML"`. The dashboard SHALL NOT introduce any new handwritten JavaScript, modal dialog, full-screen overlay, or `window.confirm`-style browser dialog for this UI.

#### Scenario: Inline form on click
- **WHEN** the user clicks ✏️ on a session row
- **THEN** the row reveals an inline form within the same DOM element
- **AND** no modal dialog or full-screen overlay is created
- **AND** no handwritten `<script>` tag (other than the vendored htmx) executes

#### Scenario: Form fields present
- **WHEN** inspecting the rendered correction form
- **THEN** it contains a `user_kind` selector with the five options listed above
- **AND** a `user_task` input
- **AND** an optional `user_note` input
- **AND** a hidden `csrf` field

#### Scenario: Form submission updates the row
- **WHEN** the user fills the form and submits it
- **THEN** the form's `hx-post` targets the correction endpoint
- **AND** the response replaces only the affected session row (not the whole page)

#### Scenario: Confirmation also inline
- **WHEN** the user clicks ✓ on a session row
- **THEN** an `hx-post` is made to the confirm endpoint without revealing any additional form
- **AND** the response replaces only the affected session row

### Requirement: Privacy posture preserved across new endpoints
The new session-correction and session-confirm endpoints SHALL NOT introduce any new outbound network call, new external dependency, new Python package, CDN reference, third-party script, or web font. They SHALL flow through the existing `_mutate` helper, the existing CSRF token lifecycle, the existing static-file allowlist, and the existing 127.0.0.1 binding. No new `<script>` tag SHALL be added beyond the vendored htmx file.

#### Scenario: No new outbound surface
- **WHEN** a session correction or confirmation is performed
- **THEN** the browser and the server make zero HTTP requests to any host other than `localhost` / `127.0.0.1`

#### Scenario: No new Python packages
- **WHEN** inspecting the project's dependencies after this change
- **THEN** no new entry has been added to `requirements.txt`, `setup.py`, or `pyproject.toml`
- **AND** the new dashboard handler imports only from the Python stdlib and from `focusmonitor.*`

#### Scenario: New endpoints flow through `_mutate`
- **WHEN** inspecting the implementation of the correct/confirm endpoints
- **THEN** each handler's first call is `_mutate(...)` with the documented required fields
- **AND** no handler performs disk writes before `_mutate` returns successfully
