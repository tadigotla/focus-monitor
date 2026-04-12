## ADDED Requirements

### Requirement: Discovered activities file
The system SHALL maintain a `~/.focus-monitor/discovered_activities.json` file containing activities the AI has observed, updated after each analysis cycle.

#### Scenario: New activity detected
- **WHEN** an analysis detects a project name not already in `discovered_activities.json`
- **THEN** the system adds an entry with `name`, `first_seen`, `last_seen`, `count: 1`, `sample_signals` (from current window titles), and `promoted: false`

#### Scenario: Known activity detected again
- **WHEN** an analysis detects a project name already in `discovered_activities.json`
- **THEN** the system updates `last_seen` to the current timestamp, increments `count`, and merges any new sample signals

#### Scenario: First run with no file
- **WHEN** `discovered_activities.json` does not exist
- **THEN** the system creates it with an empty activities array

### Requirement: Sample signals capture
The system SHALL capture sample signals from ActivityWatch window titles during each analysis and associate them with discovered activities. Sample signals SHALL be limited to 10 entries per activity.

#### Scenario: Signals extracted from window titles
- **WHEN** a project is detected and ActivityWatch has window titles like "monitor.py — VS Code"
- **THEN** the system extracts relevant keywords (e.g., "monitor.py", "VS Code") and stores them as sample signals for that activity

### Requirement: Promoted flag
Each discovered activity SHALL have a `promoted` boolean field. The user sets this to `true` when they have promoted the activity to `planned_tasks.json`.

#### Scenario: Promoted activity not evicted
- **WHEN** the activities list reaches the 50-entry cap
- **AND** an activity has `promoted: true`
- **THEN** the activity is not evicted regardless of age

#### Scenario: User marks as promoted
- **WHEN** the user edits `discovered_activities.json` and sets `promoted: true` on an entry
- **THEN** the system preserves that flag on subsequent updates

### Requirement: Activity cap and eviction
The system SHALL keep at most 50 entries in `discovered_activities.json`. When the cap is reached, the oldest non-promoted entry (by `last_seen`) SHALL be evicted. When all existing entries are promoted, the oldest entry (by `last_seen`) SHALL be evicted regardless of promoted status so that a newly-detected activity is still retained. A newly-detected activity SHALL never be evicted as part of the same update that added it.

#### Scenario: Cap reached with non-promoted entries
- **WHEN** there are 50 activities and a new one is detected
- **AND** there are non-promoted entries
- **THEN** the oldest non-promoted entry (by `last_seen`) is removed and the new entry is added
- **AND** the new entry remains in the list after the update

#### Scenario: All entries promoted
- **WHEN** all 50 entries are promoted and a new activity is detected
- **THEN** the oldest entry (by `last_seen`) is evicted regardless of promoted status
- **AND** the new activity is retained in the list

### Requirement: Planned tasks excluded from discoveries

The system SHALL NOT write an entry to `discovered_activities.json` when the detected project name case-insensitively matches the `name` field of any currently-loaded planned task. Filtering SHALL be enforced inside `update_discovered_activities` (the write-site function), so no caller can bypass it. The caller SHALL pass the currently-loaded planned tasks to the function.

#### Scenario: LLM echoes a planned task into projects

- **WHEN** `run_analysis` produces `projects: ["Focus Monitor", "Sanskrit Tool"]`
- **AND** `planned_tasks.json` contains a task with `name: "Focus Monitor"`
- **THEN** `update_discovered_activities` writes only `"Sanskrit Tool"` to `discovered_activities.json`
- **AND** `"Focus Monitor"` is dropped from the discoveries update

#### Scenario: Case drift in echoed planned task

- **WHEN** `projects` contains `"focus monitor"` (lowercase)
- **AND** `planned_tasks.json` has a task with `name: "Focus Monitor"` (title case)
- **THEN** the lowercase entry is treated as a match and dropped from the discoveries update

#### Scenario: All projects match planned tasks

- **WHEN** every entry in `projects` matches a planned task name
- **THEN** `update_discovered_activities` writes no new entries to `discovered_activities.json`
- **AND** the function returns without error (no-op is valid)

#### Scenario: Filter does not affect activity_log

- **WHEN** the filter drops a project name from the discoveries update
- **THEN** the same raw `projects` list is still written verbatim to `activity_log.project_detected`
- **AND** the debug/forensic record of what the LLM actually returned is preserved

#### Scenario: No planned tasks provided

- **WHEN** `update_discovered_activities` is called with an empty or missing `planned_tasks` argument
- **THEN** no filtering is performed (every project in the input is eligible for discovery)
- **AND** the function behaves exactly as it did before this change

#### Scenario: Planned task name substring is not a match

- **WHEN** `projects` contains `"Sanskrit Tooling Dashboard"`
- **AND** `planned_tasks.json` has a task with `name: "Sanskrit"`
- **THEN** `"Sanskrit Tooling Dashboard"` is NOT treated as a match (substrings do not filter)
- **AND** `"Sanskrit Tooling Dashboard"` is written to `discovered_activities.json` as normal

#### Scenario: Existing discovered entry is still upserted

- **WHEN** `projects` contains a name that is already in `discovered_activities.json` and is NOT a planned task
- **THEN** `update_discovered_activities` upserts the existing entry normally (updates `last_seen`, increments `count`, merges `sample_signals`)
- **AND** the filter does not interfere with the upsert path
