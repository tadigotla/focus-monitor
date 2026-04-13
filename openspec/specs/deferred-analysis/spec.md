## ADDED Requirements

### Requirement: Pending-data staging table
The system SHALL maintain a `pending_data` table in the existing focus-monitor SQLite database with at minimum the following columns:

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Auto-incrementing |
| `collected_at` | TEXT NOT NULL | ISO-8601 timestamp of collection |
| `screenshot_path` | TEXT | Absolute path to the PNG on disk; nullable if screenshot capture failed |
| `aw_events_json` | TEXT NOT NULL | JSON-encoded raw ActivityWatch events for the collection window |
| `processed` | INTEGER DEFAULT 0 | 0 = pending, 1 = analyzed |

The table SHALL be created via `CREATE TABLE IF NOT EXISTS` during the existing schema-init path in `focusmonitor/db.py`.

#### Scenario: Table created on first run
- **WHEN** focus-monitor starts against a database that does not yet contain the `pending_data` table
- **THEN** the table is created with the schema above
- **AND** no existing tables are modified or destroyed

#### Scenario: Collection tick inserts a row
- **WHEN** a collection tick fires in batch mode
- **THEN** one row is inserted into `pending_data` with `collected_at` set to the current ISO-8601 timestamp, `screenshot_path` set to the path returned by `take_screenshot()` (or NULL on failure), `aw_events_json` set to the JSON-encoded AW events for the last `screenshot_interval_sec` seconds, and `processed` set to 0

### Requirement: AW event snapshotting at collection time
When `batch_analysis` is enabled, each collection tick SHALL query ActivityWatch for raw events covering the last `screenshot_interval_sec` seconds and store them as a JSON blob in the `pending_data` row. The system SHALL NOT re-query ActivityWatch at batch-processing time.

#### Scenario: AW events captured alongside screenshot
- **WHEN** a collection tick fires and ActivityWatch is reachable
- **THEN** the raw AW event list for the last `screenshot_interval_sec` seconds is JSON-encoded and stored in `aw_events_json`

#### Scenario: ActivityWatch unreachable during collection
- **WHEN** a collection tick fires and ActivityWatch is not reachable
- **THEN** `aw_events_json` SHALL be set to an empty JSON array `"[]"`
- **AND** the system logs a warning but does not skip the collection tick

### Requirement: Collect-only mode during non-batch hours
When `batch_analysis` is `True`, the main loop SHALL only perform screenshot capture and AW event snapshotting on the `screenshot_interval_sec` cadence. The main loop SHALL NOT call `run_analysis()` on the `analysis_interval_sec` timer. The `analysis_interval_sec` timer is unused in batch mode.

#### Scenario: Normal collection tick in batch mode
- **WHEN** `batch_analysis` is `True` and a `screenshot_interval_sec` tick fires
- **THEN** the system takes a screenshot, snapshots AW events, inserts a `pending_data` row
- **AND** does NOT call `run_analysis()` or `query_ollama()`

#### Scenario: Legacy mode unchanged
- **WHEN** `batch_analysis` is `False`
- **THEN** the main loop behaves exactly as before: screenshots on `screenshot_interval_sec`, analysis on `analysis_interval_sec`, no `pending_data` rows written

### Requirement: Clock-scheduled batch processing
When `batch_analysis` is `True`, the main loop SHALL compare the current time (`HH:MM` format) against each entry in `batch_schedule` on every loop tick. When a match is found and that schedule slot has not already fired today, the system SHALL invoke `batch_analyze()`.

The `fired_today` set SHALL reset when the calendar date changes (midnight rollover).

#### Scenario: Scheduled time reached
- **WHEN** the current time matches an entry in `batch_schedule` (e.g., `"12:00"`)
- **AND** that slot has not already fired today
- **THEN** `batch_analyze()` is invoked
- **AND** the slot is marked as fired for today

#### Scenario: Same slot does not fire twice
- **WHEN** `batch_analyze()` has already run for `"12:00"` today
- **AND** the main loop ticks again at `"12:00"` (within the same minute)
- **THEN** `batch_analyze()` is NOT invoked again

#### Scenario: Midnight rollover resets schedule
- **WHEN** the calendar date changes from one day to the next
- **THEN** all entries in `fired_today` are cleared
- **AND** the next matching schedule slot triggers a fresh batch

### Requirement: Batch analysis groups pending data into windows
`batch_analyze()` SHALL query all `pending_data` rows with `processed = 0`, order them by `collected_at`, and group them into analysis windows of `analysis_interval_sec` width. Each window SHALL be processed through `run_analysis()` sequentially.

#### Scenario: Full day of pending data
- **WHEN** `batch_analyze()` is invoked and 120 unprocessed rows exist spanning 10 hours
- **AND** `analysis_interval_sec` is 3600 (1 hour)
- **THEN** the system creates 10 windows of ~12 rows each
- **AND** calls `run_analysis()` once per window in chronological order

#### Scenario: Partial window at the end
- **WHEN** the last group of pending rows spans less than `analysis_interval_sec`
- **THEN** the system still processes that group as its own window (no data is left behind)

#### Scenario: No pending data
- **WHEN** `batch_analyze()` is invoked but no rows have `processed = 0`
- **THEN** the system logs a message and returns without calling Ollama

#### Scenario: Rows marked as processed
- **WHEN** `run_analysis()` completes successfully for a window
- **THEN** all `pending_data` rows belonging to that window are updated to `processed = 1`

### Requirement: Batch merges AW events from constituent rows
When processing a window, `batch_analyze()` SHALL deserialize `aw_events_json` from each constituent `pending_data` row, concatenate the raw event lists, and pass the merged list to `run_analysis()` via the `prefetched_events` parameter.

#### Scenario: AW events from multiple 5-minute snapshots are merged
- **WHEN** a 1-hour window contains 12 `pending_data` rows, each with 5 minutes of AW events
- **THEN** `batch_analyze()` concatenates the 12 event lists into one
- **AND** passes the merged list to `run_analysis()` which calls `summarize_aw_events()` on it

### Requirement: Batch analysis config keys
The system SHALL support two new config keys:

| Key | Type | Default | Description |
|---|---|---|---|
| `batch_analysis` | boolean | `false` | Enable deferred batch analysis mode |
| `batch_schedule` | list of strings | `["07:00", "12:00", "15:00", "18:00", "20:00"]` | Times (HH:MM, 24-hour) to trigger batch processing |

When `batch_analysis` is `false`, all batch-related machinery is inert and the system behaves identically to the pre-change state.

#### Scenario: Default config preserves live mode
- **WHEN** a fresh install starts with the default config
- **THEN** `batch_analysis` is `false`
- **AND** the system runs in live analysis mode

#### Scenario: User enables batch mode
- **WHEN** the user sets `"batch_analysis": true` in `config.json`
- **THEN** the system switches to collect-only mode during non-batch hours
- **AND** processes pending data at the times listed in `batch_schedule`

#### Scenario: Custom schedule
- **WHEN** the user sets `"batch_schedule": ["08:00", "20:00"]`
- **THEN** batch processing fires only at 8 AM and 8 PM

### Requirement: Nudges disabled in batch mode
When `batch_analysis` is `True`, the system SHALL NOT call `check_nudges()` during batch analysis runs. The nudge infrastructure code SHALL remain intact but ungated.

#### Scenario: Batch analysis skips nudges
- **WHEN** `batch_analysis` is `True` and `batch_analyze()` processes a window
- **THEN** `check_nudges()` is not invoked for that window

#### Scenario: Live mode nudges unchanged
- **WHEN** `batch_analysis` is `False` and `run_analysis()` runs
- **THEN** `check_nudges()` is invoked as before
