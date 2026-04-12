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
The system SHALL keep at most 50 entries in `discovered_activities.json`. When the cap is reached, the oldest non-promoted entry (by `last_seen`) SHALL be evicted.

#### Scenario: Cap reached with non-promoted entries
- **WHEN** there are 50 activities and a new one is detected
- **AND** there are non-promoted entries
- **THEN** the oldest non-promoted entry (by `last_seen`) is removed and the new entry is added

#### Scenario: All entries promoted
- **WHEN** all 50 entries are promoted and a new activity is detected
- **THEN** the oldest entry (by `last_seen`) is evicted regardless of promoted status
