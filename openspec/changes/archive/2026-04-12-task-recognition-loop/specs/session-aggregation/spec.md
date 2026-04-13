## ADDED Requirements

### Requirement: Sessions are the primary timeline unit
The system SHALL aggregate consecutive analysis cycles into **sessions**: contiguous time ranges representing one coherent activity. Sessions are computed deterministically from `activity_log` rows and the structured signals attached to each cycle, without invoking the LLM.

A session SHALL have, at minimum: `start` timestamp, `end` timestamp, `task` name (or `null` for unclear sessions), `cycle_count`, `dip_count`, and an aggregated `evidence` list summarizing the strongest signals seen across its cycles.

The dashboard SHALL render sessions (not raw cycles) as the primary timeline unit. Existing per-cycle `activity_log` rows SHALL remain queryable but are not the primary surface.

#### Scenario: Single coherent activity becomes one session
- **WHEN** five consecutive analysis cycles all share `workspace="focus-monitor"` and have `name_confidence` of medium or higher
- **THEN** the aggregator produces exactly one session spanning the time range of the first cycle's start to the last cycle's end
- **AND** the session's `cycle_count` is 5
- **AND** the session's `task` is the canonical name extracted from the cycles

#### Scenario: Genuine task switch creates separate sessions
- **WHEN** three consecutive cycles share `workspace="focus-monitor"`, then four consecutive cycles share `workspace="other-project"`, with no overlapping signals
- **THEN** the aggregator produces two distinct sessions
- **AND** the boundary between them is set at the end of the third cycle / start of the fourth

### Requirement: Glue rules merge cycles sharing structured signal
The aggregator SHALL merge two consecutive cycles into the same session when ANY of the following are true:
1. Both cycles' artifacts share a non-null `workspace` value (case-insensitive match).
2. Both cycles' artifacts share a non-null `terminal_cwd` value (case-insensitive match).
3. Both cycles' artifacts share a non-null `browser_url` host (case-insensitive match on the host portion only).
4. Both cycles have `name_confidence` of `medium` or higher AND share the same `task` (case-insensitive).

The set of glue signals SHALL be defined in a module-level constant (e.g. `_GLUE_SIGNALS`) so it can be tuned without touching the aggregation logic.

#### Scenario: Workspace glue
- **WHEN** cycle A has `workspace="focus-monitor"` and cycle B has `workspace="focus-monitor"`
- **THEN** the aggregator merges A and B into the same session even if their other fields differ

#### Scenario: Terminal cwd glue
- **WHEN** cycle A has `terminal_cwd="~/code/proj"` and cycle B has `terminal_cwd="~/code/proj"`
- **THEN** the aggregator merges them

#### Scenario: Browser host glue
- **WHEN** cycle A has `browser_url="github.com/foo/bar/pull/47"` and cycle B has `browser_url="github.com/foo/bar/issues/12"`
- **THEN** the aggregator merges them on the shared `github.com` host

#### Scenario: Task name glue
- **WHEN** cycle A and cycle B both have `task="auth refactor"` and both have `name_confidence="medium"` or higher
- **THEN** the aggregator merges them even if their structured artifacts differ

#### Scenario: No overlapping signals
- **WHEN** cycle A has only `workspace="proj-a"` populated and cycle B has only `workspace="proj-b"` populated
- **THEN** the aggregator does NOT merge them and treats them as separate sessions

### Requirement: Short dips are tolerated within a session
A cycle whose signals would normally start a new session, but whose duration is less than or equal to `session_dip_tolerance_sec` (default: 300s = 5 minutes), and whose neighbors on both sides belong to the same session, SHALL be absorbed into the surrounding session as a **dip** rather than splitting it.

The session SHALL increment its `dip_count` by one for each dip absorbed. The dip's signals SHALL NOT contribute to the session's aggregated evidence.

#### Scenario: 3-minute reddit dip inside auth session
- **WHEN** four consecutive cycles share `workspace="focus-monitor"`, then one 3-minute cycle has `browser_url="reddit.com"`, then four more cycles return to `workspace="focus-monitor"`
- **THEN** the aggregator produces exactly one session covering all nine cycles
- **AND** the session's `dip_count` is 1
- **AND** the session's evidence does not list reddit.com

#### Scenario: 10-minute distraction breaks the session
- **WHEN** the same scenario but the distraction lasts 10 minutes (> `session_dip_tolerance_sec`)
- **THEN** the aggregator produces three distinct sessions: focus-monitor, distraction, focus-monitor

#### Scenario: Configurable dip tolerance
- **WHEN** `session_dip_tolerance_sec` is set to 600 in config
- **THEN** dips up to 10 minutes are tolerated
- **AND** dips longer than 10 minutes split the session

### Requirement: AW afk events drive away/active distinction
The aggregator SHALL query ActivityWatch's `aw-watcher-afk` bucket for the analysis range and SHALL classify any cycle that overlaps ≥ 50% with an `afk` event as an `away` entry rather than as part of any session.

Consecutive `away` cycles SHALL be merged into a single `away` entry showing the contiguous away time range.

The system SHALL NOT ask the LLM to infer presence; the determination is made entirely from AW data.

#### Scenario: Lunch break detected via afk
- **WHEN** AW reports an afk event from 12:30 to 13:15 and analysis cycles are running every 5 minutes
- **THEN** the cycles overlapping that range produce a single `away` entry from 12:30 to 13:15
- **AND** no LLM call is made to classify those cycles

#### Scenario: Brief afk does not split active session
- **WHEN** AW reports a 30-second afk event in the middle of an otherwise-active 5-minute cycle
- **THEN** the cycle is NOT classified as `away` (overlap is below 50%)
- **AND** the cycle participates in normal session aggregation

#### Scenario: AW unreachable
- **WHEN** the aggregator cannot reach ActivityWatch
- **THEN** it skips the afk classification step
- **AND** continues to aggregate sessions from cycle data alone
- **AND** does not raise an error

### Requirement: Unclear cycles become standalone unclear entries
A cycle with `name_confidence="low"` whose structured signals do not match any glue rule against either neighbor SHALL be emitted as its own `unclear` entry. It SHALL NOT be silently merged into a neighboring session.

An `unclear` entry is rendered on the dashboard with the same shape as a session (start, end, evidence) but with `task=null` and an `unclear` label.

#### Scenario: Lone unclear cycle
- **WHEN** an analysis cycle has `name_confidence="low"`, `task=null`, no `workspace`/`cwd`/`url` matching either neighbor, and is surrounded by cycles for two different workspaces
- **THEN** the aggregator emits the cycle as a standalone `unclear` entry
- **AND** it does not become part of either neighboring session

#### Scenario: Unclear cycle absorbed when bordered by same session
- **WHEN** an unclear cycle is bordered on both sides by cycles of the same session, AND its duration is within the dip tolerance
- **THEN** it is absorbed as a dip per the dip-tolerance rule above

### Requirement: Session storage in SQLite
The aggregator SHALL persist computed sessions to a `sessions` table in the existing focus-monitor SQLite database. The schema SHALL include at minimum: `id`, `start`, `end`, `task`, `task_name_confidence`, `boundary_confidence`, `cycle_count`, `dip_count`, `evidence_json`, and `kind` (one of `session | unclear | away`).

The table SHALL be created via `CREATE TABLE IF NOT EXISTS` on startup. Existing `activity_log` schema SHALL NOT be modified. Old activity_log rows from before this change SHALL remain readable.

The aggregator SHALL be re-runnable: re-aggregating the same time range MUST produce the same sessions and SHALL NOT create duplicate rows. Implementations MAY achieve this by deleting existing session rows in the affected range before inserting new ones, or by upserting on a deterministic key.

#### Scenario: Sessions table created on first run
- **WHEN** focus-monitor starts against a database that has `activity_log` but no `sessions` table
- **THEN** the `sessions` table is created via the existing schema-init path
- **AND** no existing data is destroyed or migrated

#### Scenario: Re-aggregation is idempotent
- **WHEN** the aggregator runs twice over the same time range
- **THEN** the second run produces the same set of session rows as the first
- **AND** does not create duplicate rows

### Requirement: Session evidence aggregates from constituent cycles
A session's `evidence_json` SHALL contain the union of strong/medium-weight signals from its constituent cycles, deduplicated by `signal` string. Weak-weight signals MAY be omitted from the aggregated evidence.

The evidence list rendered on the dashboard SHALL be drawn from this aggregated evidence, NOT from a single representative cycle.

#### Scenario: Evidence aggregates across cycles
- **WHEN** a session contains five cycles each with overlapping evidence (e.g. all five cite `workspace=focus-monitor` as `strong`)
- **THEN** the session's aggregated evidence contains exactly one entry for `workspace=focus-monitor`
- **AND** any other strong signals from individual cycles also appear once

#### Scenario: Weak signals filtered
- **WHEN** a cycle contributes only weak-weight evidence
- **THEN** the session's aggregated evidence MAY exclude that cycle's signals entirely

### Requirement: Configurable aggregation knobs
The system SHALL read the following keys from the config file:

- `session_dip_tolerance_sec` (integer, default: 300) — maximum dip duration absorbed into a session
- `session_aggregation_enabled` (boolean, default: true) — when false, the dashboard falls back to the legacy per-cycle view

#### Scenario: Custom dip tolerance
- **WHEN** the config contains `"session_dip_tolerance_sec": 120`
- **THEN** the aggregator absorbs dips up to 2 minutes

#### Scenario: Aggregation disabled
- **WHEN** the config contains `"session_aggregation_enabled": false`
- **THEN** the aggregator is not run
- **AND** the dashboard renders the legacy per-cycle activity log
