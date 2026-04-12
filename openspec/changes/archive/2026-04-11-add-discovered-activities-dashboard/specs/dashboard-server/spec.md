## ADDED Requirements

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
