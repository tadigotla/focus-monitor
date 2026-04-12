## Why

`monitor.py` is an 845-line monolith containing 7 unrelated functional areas: config/DB, ActivityWatch integration, screenshot capture, Ollama queries, AI analysis, task management, nudges, and cleanup. Every change to one area requires reading through the entire file, and cross-cutting concerns (like config, DB paths) are scattered as module-level globals. This makes it hard to enhance any single capability without touching unrelated code.

## What Changes

- **Split `monitor.py` into focused modules** inside a `focusmonitor/` package:
  - `config.py` — Config loading, path constants, defaults, migration
  - `db.py` — Database init and connection
  - `activitywatch.py` — AW event fetching and summarization
  - `screenshots.py` — Capture, dedup, cleanup
  - `ollama.py` — Model queries, image encoding
  - `analysis.py` — Two-pass analysis pipeline, prompt building, JSON parsing, validation
  - `tasks.py` — Planned task loading, discovered activities, signal matching
  - `nudges.py` — Nudge checking and sending
  - `cleanup.py` — Unified cleanup (screenshots, DB, logs)
  - `main.py` — Main loop and startup only

- **`dashboard.py` → `focusmonitor/dashboard.py`**: Move into the package.
- **Update `cli.py`**: Import from the package instead of individual scripts.
- **Preserve all behavior**: Pure refactor — no functional changes, no new features.

## Capabilities

### New Capabilities
- `module-structure`: Package layout with focused modules and clear import boundaries

### Modified Capabilities

(none — this is a pure refactor, no spec-level behavior changes)

## Impact

- **`monitor.py`**: Deleted. Contents distributed across `focusmonitor/` modules.
- **`dashboard.py`**: Moved to `focusmonitor/dashboard.py`.
- **`cli.py`**: Imports updated from `from monitor import ...` to `from focusmonitor import ...`.
- **`setup.py`**: References updated.
- **Tests**: Import paths updated.
- **No behavior changes**: All 80 existing tests must continue to pass.
