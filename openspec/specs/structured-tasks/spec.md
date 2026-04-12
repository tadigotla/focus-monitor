## ADDED Requirements

### Requirement: JSON-based planned task definitions
The system SHALL read planned tasks from `~/.focus-monitor/planned_tasks.json` as a JSON array of task objects. Each task object SHALL have a required `name` field (string) and optional fields: `signals` (array of strings), `apps` (array of strings), `notes` (string).

#### Scenario: Valid planned tasks file
- **WHEN** `planned_tasks.json` contains a valid JSON array of task objects
- **THEN** the system loads all tasks with their names, signals, apps, and notes

#### Scenario: Task with signals
- **WHEN** a task has `"signals": ["sanskrit", "panini", "dhatu"]`
- **THEN** the system uses these keywords for matching against window titles and detected projects during analysis

#### Scenario: Task with only name
- **WHEN** a task has only `"name"` and no signals, apps, or notes
- **THEN** the system uses the name for matching (backward-compatible behavior)

### Requirement: Auto-migration from planned_tasks.txt
The system SHALL auto-migrate from `planned_tasks.txt` to `planned_tasks.json` on startup when the JSON file does not exist but the text file does.

#### Scenario: Migration on first run
- **WHEN** `planned_tasks.json` does not exist AND `planned_tasks.txt` exists with task entries
- **THEN** the system creates `planned_tasks.json` with each text line as a task object (name only, empty signals)
- **AND** renames `planned_tasks.txt` to `planned_tasks.txt.bak`
- **AND** prints a message suggesting the user add signals to their tasks

#### Scenario: Both files exist
- **WHEN** both `planned_tasks.json` and `planned_tasks.txt` exist
- **THEN** the system uses `planned_tasks.json` and ignores the text file

#### Scenario: Neither file exists
- **WHEN** neither file exists
- **THEN** the system creates a `planned_tasks.json` with an example entry and a comment-like placeholder

### Requirement: Default example file
The system SHALL create a `planned_tasks.json` with a helpful example when no task files exist, demonstrating the name, signals, apps, and notes fields.

#### Scenario: Generated example
- **WHEN** the system generates the default `planned_tasks.json`
- **THEN** the file contains one commented-out example entry showing all fields
- **AND** the file is valid JSON that loads as an empty array (or array with example)

### Requirement: Signal-based matching in nudge checks
The system SHALL use both task names and signals for matching when checking whether a planned task has been worked on (for nudge decisions).

#### Scenario: Match via signal keyword
- **WHEN** a task has `signals: ["sanskrit", "panini"]`
- **AND** a recent analysis detected a project containing "sanskrit" in its name
- **THEN** the task is considered matched and no nudge is sent

#### Scenario: Match via task name (fallback)
- **WHEN** a task has no signals defined
- **AND** a recent analysis detected a project whose name contains the task name
- **THEN** the task is considered matched (backward-compatible)

### Requirement: Atomic planned-task mutation helpers

`focusmonitor.tasks` SHALL expose three helpers that mutate `planned_tasks.json`:

- `add_planned_task(name, signals=None, notes="")` — appends a new task. Returns `True` on success, `False` if a task with the same name already exists (case-insensitive).
- `update_planned_task(name, signals=None, notes=None)` — updates an existing task's `signals` and/or `notes`. Fields passed as `None` are left unchanged. Returns `True` on success, `False` if no task with the given name exists.
- `delete_planned_task(name)` — removes the task with the given name (case-insensitive). Returns `True` on success, `False` if no matching task exists.

Every helper SHALL perform its file write via a `_write_json_atomic(path, data)` helper that writes to a temp file and uses `os.replace` to swap the target. No helper SHALL leave a partial or corrupted `planned_tasks.json` on disk under any failure mode short of filesystem-level corruption.

#### Scenario: Add a new task
- **WHEN** `add_planned_task("Foo", signals=["bar"], notes="hello")` is called
- **AND** no task named "Foo" exists
- **THEN** `planned_tasks.json` gains a new entry with those fields
- **AND** the function returns `True`

#### Scenario: Add rejects duplicate name
- **WHEN** `add_planned_task("Foo")` is called
- **AND** a task named "Foo" already exists (case-insensitive)
- **THEN** the file is not modified
- **AND** the function returns `False`

#### Scenario: Update modifies selective fields
- **WHEN** `update_planned_task("Foo", signals=["baz"], notes=None)` is called
- **AND** a task named "Foo" exists with `notes: "hello"`
- **THEN** the entry's `signals` is replaced with `["baz"]`
- **AND** the entry's `notes` remains "hello"
- **AND** the function returns `True`

#### Scenario: Update rejects missing name
- **WHEN** `update_planned_task("Nonexistent", signals=["foo"])` is called
- **AND** no matching task exists
- **THEN** the file is not modified
- **AND** the function returns `False`

#### Scenario: Delete removes entry
- **WHEN** `delete_planned_task("Foo")` is called
- **AND** a task named "Foo" exists
- **THEN** the entry is removed from the file
- **AND** the function returns `True`

#### Scenario: Delete rejects missing name
- **WHEN** `delete_planned_task("Nonexistent")` is called
- **AND** no matching task exists
- **THEN** the function returns `False`
- **AND** the file is not modified

#### Scenario: Atomic write survives crash
- **WHEN** any mutation helper is interrupted mid-write (e.g., the process crashes between open and close)
- **THEN** `planned_tasks.json` retains its pre-mutation contents
- **AND** no `.tmp` file is left in a state where it could be mistaken for the real file

#### Scenario: Case-insensitive matching
- **WHEN** `delete_planned_task("foo")` is called
- **AND** a task named "Foo" exists
- **THEN** the entry is removed successfully
