## ADDED Requirements

### Requirement: Corrections store schema
The system SHALL maintain a `corrections` table in the existing focus-monitor SQLite database. The schema SHALL include at minimum the following columns:

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Auto-incrementing |
| `created_at` | TEXT NOT NULL | ISO-8601 timestamp |
| `entry_kind` | TEXT NOT NULL | One of `session | cycle` |
| `entry_id` | INTEGER NOT NULL | Foreign id into the `sessions` or `activity_log` table |
| `range_start` | TEXT NOT NULL | ISO-8601 timestamp of the corrected entry's start |
| `range_end` | TEXT NOT NULL | ISO-8601 timestamp of the corrected entry's end |
| `model_task` | TEXT | Nullable; may be `NULL` if the model said "unclear" |
| `model_evidence` | TEXT NOT NULL | JSON-encoded evidence list as the model produced it |
| `model_boundary_confidence` | TEXT NOT NULL | One of `low | medium | high` |
| `model_name_confidence` | TEXT NOT NULL | One of `low | medium | high` |
| `user_verdict` | TEXT NOT NULL | One of `corrected | confirmed` |
| `user_task` | TEXT | Nullable; the task name the user supplied |
| `user_kind` | TEXT NOT NULL | One of `on_planned_task | thinking_offline | meeting | break | other` |
| `user_note` | TEXT | Optional free text from the user |
| `signals` | TEXT NOT NULL | JSON-encoded structured signals visible at the time |

The table SHALL be created via `CREATE TABLE IF NOT EXISTS` during the existing schema-init path in `focusmonitor/db.py`. The path to the SQLite file SHALL be read from `focusmonitor.config` and SHALL NOT be hardcoded.

#### Scenario: Table created on first run
- **WHEN** focus-monitor starts against a database that does not yet contain the `corrections` table
- **THEN** the table is created with the schema above
- **AND** no existing data is destroyed or migrated

#### Scenario: Path read from config
- **WHEN** inspecting the code that opens the database for corrections
- **THEN** the SQLite path is obtained from `focusmonitor.config`
- **AND** is not a hardcoded string

### Requirement: Per-entry corrections only (v1)
A correction SHALL apply only to the single entry (`entry_kind`, `entry_id`) it was filed against. The correction-loop machinery SHALL NOT retroactively re-label other entries — past or future — based on a single correction.

#### Scenario: Correcting one session does not affect others
- **WHEN** the user files a correction against session `id=42`
- **THEN** only one row is inserted into `corrections` (with `entry_id=42`)
- **AND** no other session's stored task or evidence is modified

#### Scenario: Re-correcting the same entry appends a new row
- **WHEN** the user files a second correction against the same session
- **THEN** a second row is appended to `corrections` with the new verdict
- **AND** the earlier row remains in place (the corrections table is append-only history)

### Requirement: Confirmations are first-class
The system SHALL accept and persist user confirmations (✓) using the same `corrections` table and the same write path as corrections (✏️), distinguished by the `user_verdict` column.

A confirmation SHALL be considered a positive training signal of equal status to a correction in the few-shot retrieval below.

#### Scenario: Confirming an entry inserts a row
- **WHEN** the user clicks ✓ on a session that the model classified correctly
- **THEN** a row is inserted into `corrections` with `user_verdict='confirmed'`
- **AND** the row's `user_task` matches the model's `task` (or is `NULL` if the model said "unclear" and the user is confirming the unclear verdict)

#### Scenario: Confirmations and corrections retrieved together
- **WHEN** the few-shot retrieval pulls recent records from the corrections store
- **THEN** both `corrected` and `confirmed` rows are returned
- **AND** they appear in the prompt with their verdict clearly labeled

### Requirement: Few-shot retrieval injects most-recent-N records
The classification pipeline SHALL include the N most recent records (any verdict) from the `corrections` table in the Pass 2 classification prompt as few-shot examples. N is read from `corrections_few_shot_n` in the config (default: 5). When N is 0, no few-shot section is included.

The retrieval SHALL be a single SQL query of the form `SELECT ... FROM corrections ORDER BY created_at DESC LIMIT ?` with no scoring, no similarity calculation, and no embedding lookup. Adding similarity-based retrieval is explicitly out of scope for this change.

When `batch_analysis` is `True`, the few-shot retrieval still operates identically. Corrections filed between batch runs are visible to the next batch run's analysis cycles. The feedback latency increases from ~1 hour to ~2–3 hours but the mechanism is unchanged.

#### Scenario: Most recent N records retrieved
- **WHEN** the classification pipeline runs and the `corrections` table has more than N records
- **THEN** the N records with the most recent `created_at` are pulled
- **AND** they appear in the prompt ordered most-recent-first

#### Scenario: Fewer than N records
- **WHEN** the table has fewer than N records
- **THEN** all available records are returned
- **AND** no padding or placeholder is added

#### Scenario: N is zero
- **WHEN** `corrections_few_shot_n` is `0`
- **THEN** no query is issued and no few-shot section is rendered

#### Scenario: Corrections filed between batch runs
- **WHEN** the user corrects a session at 1:00 PM
- **AND** the next batch runs at 3:00 PM
- **THEN** the 1:00 PM correction appears in the few-shot block for all analysis cycles in the 3:00 PM batch

### Requirement: Correction-loop write API
The system SHALL expose a Python function (e.g. `record_correction(entry_kind, entry_id, model_state, user_state)`) in a `focusmonitor.corrections` module that:

1. Inserts one row into the `corrections` table with all required columns populated.
2. Performs the insert atomically (single SQLite transaction, committed).
3. Returns the inserted row's `id` on success.
4. Raises a clearly-named exception when required fields are missing or when the referenced entry does not exist.

The function SHALL NOT mutate the referenced session or activity_log row. Corrections are append-only history; existing analysis state is left untouched.

#### Scenario: Successful write
- **WHEN** `record_correction` is called with valid model_state and user_state for an existing session
- **THEN** a row is inserted into `corrections`
- **AND** the inserted row's `id` is returned
- **AND** the referenced session's row is unchanged

#### Scenario: Missing required field
- **WHEN** `record_correction` is called with `user_kind=None`
- **THEN** the function raises an exception
- **AND** no row is inserted

#### Scenario: Referenced entry does not exist
- **WHEN** `record_correction` is called with `entry_kind='session'` and an `entry_id` that does not exist in the `sessions` table
- **THEN** the function raises an exception
- **AND** no row is inserted

### Requirement: Correction-loop read API for the dashboard
The system SHALL expose a Python function (e.g. `corrections_for(entry_kind, entry_id)`) that returns the list of correction rows previously filed against a given entry, ordered by `created_at` descending. The dashboard SHALL use this to render correction history on demand (e.g. in an expandable drawer).

#### Scenario: Read corrections for an entry
- **WHEN** `corrections_for('session', 42)` is called and two corrections exist for session 42
- **THEN** both rows are returned ordered most-recent-first

#### Scenario: No corrections for an entry
- **WHEN** `corrections_for('session', 42)` is called and no corrections exist
- **THEN** an empty list is returned (not an exception)

### Requirement: Privacy posture preserved
The corrections store and the few-shot retrieval SHALL NOT introduce any new external dependency, new outbound network call, new third-party Python package, or new data path outside `~/.focus-monitor/`. The corrections file SHALL live in the existing SQLite database whose path is determined by `focusmonitor.config`.

Cassettes used in tests for the corrections-related code paths SHALL be captured against synthetic correction rows and the existing PNG/AW fixtures, never against real user data.

#### Scenario: No new dependencies
- **WHEN** inspecting the imports of the new corrections module
- **THEN** every imported module is from the Python stdlib or from the existing `focusmonitor` package
- **AND** no entry has been added to `requirements.txt`, `setup.py`, or `pyproject.toml`

#### Scenario: No new outbound surface
- **WHEN** the corrections write or read paths execute
- **THEN** no HTTP request is made to any host
- **AND** the existing pytest-socket allow-list (`127.0.0.1`, `localhost`, `::1`) is unchanged

#### Scenario: Path read from config
- **WHEN** the corrections module opens the database
- **THEN** the path is obtained from `focusmonitor.config`
- **AND** is not a hardcoded string

### Requirement: CSRF token refresh after correction submission
After a successful correction or confirmation POST, the server SHALL return a fresh CSRF token that is usable by subsequent htmx requests without a full page reload. The page-level `hx-headers` CSRF token SHALL be updated to match the fresh token so that all htmx-driven mutation endpoints continue to work.

#### Scenario: Second correction succeeds after first
- **WHEN** the user submits a correction for session A (succeeds)
- **AND** then submits a correction for session B without reloading the page
- **THEN** the second submission also succeeds (200, not 403)
- **AND** the correction row for session B is persisted

#### Scenario: Confirmation after correction succeeds
- **WHEN** the user submits a correction for session A (succeeds)
- **AND** then clicks Confirm on session B without reloading the page
- **THEN** the confirmation succeeds (200, not 403)

#### Scenario: Token propagated via htmx mechanism
- **WHEN** a correction POST returns successfully
- **THEN** the response includes a mechanism (e.g. HX-Trigger header) that causes the page-level htmx CSRF header to update
- **AND** no full page reload is required
