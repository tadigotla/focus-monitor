## ADDED Requirements

### Requirement: Hidden flag on discovered activities

Each entry in `~/.focus-monitor/discovered_activities.json` MAY have a `hidden` boolean field. When `hidden` is `true`, the dashboard SHALL filter the entry out of the Discovered Activities card without evicting it from the file. When absent, `hidden` SHALL default to `false` for backward compatibility with pre-existing files. The `hidden` flag SHALL be preserved across upsert operations in `update_discovered_activities`, analogous to how `promoted` is preserved.

The `hidden` flag is independent of `promoted`. An entry MAY be both `hidden` and `promoted`. An entry MAY be `hidden` without being `promoted` (the user simply doesn't want to see it in the dashboard). An entry MAY be `promoted` without being `hidden` (the user has actively added it to their plan and wants the dashboard to continue showing its pill).

#### Scenario: Hidden entry not shown in dashboard
- **WHEN** an entry has `hidden: true`
- **THEN** `render_discovered_card` omits it from the rendered card
- **AND** the entry remains in `discovered_activities.json` on disk

#### Scenario: Hidden flag preserved on upsert
- **WHEN** `update_discovered_activities` processes a project that matches an entry with `hidden: true`
- **THEN** the entry's `hidden` field remains `true` after the upsert
- **AND** its `last_seen` and `count` are still updated

#### Scenario: Default hidden value
- **WHEN** a discovered activity entry is read from a pre-existing file that has no `hidden` field
- **THEN** the entry is treated as `hidden: false`
- **AND** the dashboard shows it normally

#### Scenario: Hidden and promoted are independent
- **WHEN** an entry has `hidden: true` and `promoted: true`
- **THEN** `render_discovered_card` omits it (because of hidden)
- **AND** the entry is NOT evicted when the cap is reached (because of promoted, per the existing requirement)

### Requirement: Hide helper

`focusmonitor.tasks` SHALL expose a `hide_discovered(name)` function that sets `hidden: true` on the entry matching `name` (case-insensitive). If no matching entry exists, the function SHALL return `False`. On success, it SHALL return `True` and write the updated file via the atomic write helper.

#### Scenario: Hide an existing entry
- **WHEN** `hide_discovered("Sanskrit Tool")` is called
- **AND** a discovered activity with that name exists
- **THEN** the entry's `hidden` field is set to `true`
- **AND** the function returns `True`
- **AND** the file is written atomically (via temp-file + `os.replace`)

#### Scenario: Hide a non-existent entry
- **WHEN** `hide_discovered("Nonexistent")` is called
- **AND** no discovered activity matches that name
- **THEN** the function returns `False`
- **AND** the file is not modified

#### Scenario: Hide is case-insensitive
- **WHEN** `hide_discovered("sanskrit tool")` is called
- **AND** a discovered activity named "Sanskrit Tool" exists
- **THEN** the entry is hidden successfully

### Requirement: Promote helper

`focusmonitor.tasks` SHALL expose a `promote_discovered(name)` function that composes "add a planned task" and "mark the discovered entry as promoted" in a single atomic operation. The new planned task SHALL inherit the discovered entry's name and `sample_signals` as its `signals`; `notes` SHALL be empty. If no matching discovered entry exists, or if a planned task with the same name already exists, the function SHALL return `False`. On success, it SHALL return `True`.

#### Scenario: Promote a new discovery
- **WHEN** `promote_discovered("Sanskrit Tool")` is called
- **AND** a discovered activity with that name and sample signals `["devanagari", "pāṇini"]` exists
- **AND** no planned task named "Sanskrit Tool" exists
- **THEN** `planned_tasks.json` gains a new entry with `name: "Sanskrit Tool"` and `signals: ["devanagari", "pāṇini"]`
- **AND** the discovered entry's `promoted` field is set to `true`
- **AND** the function returns `True`

#### Scenario: Promote is idempotent when planned task exists
- **WHEN** `promote_discovered("Sanskrit Tool")` is called
- **AND** a planned task with that name already exists
- **THEN** the function returns `False`
- **AND** neither file is modified
