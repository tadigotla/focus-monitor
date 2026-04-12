## ADDED Requirements

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
