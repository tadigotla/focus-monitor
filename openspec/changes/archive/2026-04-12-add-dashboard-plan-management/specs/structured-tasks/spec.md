## ADDED Requirements

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
