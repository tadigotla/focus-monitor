## ADDED Requirements

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
