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
