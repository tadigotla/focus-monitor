## ADDED Requirements

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
