## ADDED Requirements

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
