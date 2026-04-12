## 1. Planned Tasks JSON

- [x] 1.1 Add `TASKS_JSON_FILE` path constant (`~/.focus-monitor/planned_tasks.json`) and `DISCOVERED_FILE` path constant (`~/.focus-monitor/discovered_activities.json`) in monitor.py
- [x] 1.2 Rewrite `load_planned_tasks()` to return a list of task dicts from `planned_tasks.json`. Each dict has `name` (str), `signals` (list), `apps` (list), `notes` (str). Fall back to empty list if file missing
- [x] 1.3 Add migration logic in `load_config()`: if `planned_tasks.json` doesn't exist but `planned_tasks.txt` does, migrate entries to JSON format (name-only, empty signals), rename `.txt` to `.txt.bak`, print migration message
- [x] 1.4 Generate a default `planned_tasks.json` with an example entry when neither file exists, similar to current `planned_tasks.txt` behavior

## 2. Discovered Activities

- [x] 2.1 Add `update_discovered_activities(projects, top_titles)` function that reads/creates `discovered_activities.json`, upserts detected projects (update last_seen/count for known, add new), captures sample signals from window titles, enforces 50-entry cap with eviction
- [x] 2.2 Call `update_discovered_activities()` from `run_analysis()` after a successful analysis, passing the result's `projects` list and the current ActivityWatch window titles

## 3. Prompt & Matching Updates

- [x] 3.1 Update `build_classification_prompt()` to format planned tasks with signals and notes instead of plain names. Format: `- "Name" — signals: x, y, z\n  (notes)`. Include instruction for the AI to use signals for matching
- [x] 3.2 Update all callers of `load_planned_tasks()` — adapt `run_analysis()` task_list formatting and `check_nudges()` matching logic to work with task dicts instead of plain strings
- [x] 3.3 Update `check_nudges()` to match using both task name AND signals against recent detected projects (case-insensitive substring matching)

## 4. Startup & Display

- [x] 4.1 Update `main()` startup banner to show planned tasks with their signal counts (e.g., "Sanskrit Study Tool (3 signals)")
- [x] 4.2 Update the default `planned_tasks.json` creation message to guide the user on the JSON format

## 5. Testing

- [x] 5.1 Test: planned tasks JSON loading (valid file, missing file, task with signals, task without signals)
- [x] 5.2 Test: migration from `planned_tasks.txt` to JSON (creates JSON, renames txt to .bak)
- [x] 5.3 Test: discovered activities upsert (new activity, known activity update, cap enforcement, promoted flag preservation)
- [x] 5.4 Test: signal-based nudge matching (match via signal, match via name fallback, no match triggers nudge)
