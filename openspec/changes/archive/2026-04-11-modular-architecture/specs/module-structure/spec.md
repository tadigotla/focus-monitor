## ADDED Requirements

### Requirement: Package-based module structure
The system SHALL be organized as a `focusmonitor/` Python package with separate modules for each functional area: config, db, activitywatch, screenshots, ollama, analysis, tasks, nudges, cleanup, dashboard, and main.

#### Scenario: Each module is independently importable
- **WHEN** a developer imports `from focusmonitor.screenshots import take_screenshot`
- **THEN** only the screenshots module and its dependencies (config) are loaded

#### Scenario: No circular dependencies
- **WHEN** any module in the package is imported
- **THEN** no circular import errors occur

### Requirement: Clear module responsibilities
Each module SHALL contain only functions related to its functional area. No module SHALL mix concerns from different areas.

#### Scenario: Analysis module contains only analysis functions
- **WHEN** a developer reads `focusmonitor/analysis.py`
- **THEN** it contains only prompt building, JSON parsing, validation, screenshot description, history retrieval, and the analysis pipeline — no screenshot capture, no nudge logic, no cleanup

#### Scenario: Config module is the single source of path constants
- **WHEN** any module needs a path constant (DB_PATH, SCREENSHOT_DIR, etc.)
- **THEN** it imports it from `focusmonitor.config`, not from any other module

### Requirement: Backward-compatible entry points
The system SHALL maintain backward-compatible entry points so existing launchd plists and scripts continue to work.

#### Scenario: monitor.py still works
- **WHEN** a user runs `python3 monitor.py`
- **THEN** the monitor starts normally (thin wrapper that calls `focusmonitor.main.main()`)

#### Scenario: cli.py still works
- **WHEN** a user runs `python3 cli.py run`
- **THEN** the CLI dispatches correctly using imports from the `focusmonitor` package

#### Scenario: dashboard.py standalone still works
- **WHEN** a user runs `python3 dashboard.py` directly (at root level)
- **THEN** it opens the dashboard in the browser (thin wrapper)

### Requirement: All existing tests pass
The system SHALL pass all existing tests after the refactor with only import path changes in test files.

#### Scenario: Tests with updated imports
- **WHEN** test files are updated to import from `focusmonitor.*` instead of `monitor`
- **THEN** all 80 existing tests pass without any logic changes
