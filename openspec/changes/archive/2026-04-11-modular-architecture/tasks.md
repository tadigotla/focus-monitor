## 1. Create Package

- [x] 1.1 Create `focusmonitor/` directory and `focusmonitor/__init__.py` (re-exports `main` from `focusmonitor.main`)

## 2. Extract Modules (leaf modules first, then dependents)

- [x] 2.1 Create `focusmonitor/config.py` — move path constants (`CONFIG_DIR`, `DB_PATH`, `SCREENSHOT_DIR`, `TASKS_FILE`, `TASKS_JSON_FILE`, `DISCOVERED_FILE`, `CONFIG_FILE`, `LOG_DIR`), `DEFAULT_CONFIG`, `DEFAULT_PLANNED_TASKS`, and `load_config()` from monitor.py
- [x] 2.2 Create `focusmonitor/db.py` — move `init_db()`, importing `DB_PATH` from config
- [x] 2.3 Create `focusmonitor/activitywatch.py` — move `get_aw_events()` and `summarize_aw_events()`
- [x] 2.4 Create `focusmonitor/screenshots.py` — move `take_screenshot()`, `recent_screenshots()`, `deduplicate_screenshots()`, `cleanup_old_screenshots()`, importing `SCREENSHOT_DIR` from config
- [x] 2.5 Create `focusmonitor/ollama.py` — move `encode_image()` and `query_ollama()`
- [x] 2.6 Create `focusmonitor/tasks.py` — move `load_planned_tasks()`, `update_discovered_activities()`, `_task_matches_projects()`, and `MAX_DISCOVERED` constant, importing paths from config
- [x] 2.7 Create `focusmonitor/nudges.py` — move `check_nudges()`, `send_nudge()`, importing `load_planned_tasks` from tasks
- [x] 2.8 Create `focusmonitor/cleanup.py` — move `cleanup_old_db_rows()`, `cleanup_log_files()`, `run_cleanup()`, importing `cleanup_old_screenshots` from screenshots and `LOG_DIR` from config
- [x] 2.9 Create `focusmonitor/analysis.py` — move `parse_analysis_json()`, `validate_analysis_result()`, `describe_screenshots()`, `get_recent_history()`, `build_classification_prompt()`, `run_analysis()`, importing from ollama, screenshots, tasks, activitywatch, nudges, cleanup
- [x] 2.10 Create `focusmonitor/dashboard.py` — move contents from root `dashboard.py`, importing `DB_PATH` from config
- [x] 2.11 Create `focusmonitor/main.py` — move `main()` function, importing from config, db, dashboard, analysis, cleanup, tasks

## 3. Update Entry Points

- [x] 3.1 Replace root `monitor.py` with a thin wrapper: `from focusmonitor.main import main; main()` when run as `__main__`
- [x] 3.2 Replace root `dashboard.py` with a thin wrapper that imports from `focusmonitor.dashboard`
- [x] 3.3 Update `cli.py` imports to use `focusmonitor.*` package paths
- [x] 3.4 Update `setup.py` imports if any (no changes needed)

## 4. Update Tests

- [x] 4.1 Update `test_analysis.py` imports to use `focusmonitor.*` paths
- [x] 4.2 Update `test_structured_tasks.py` imports to use `focusmonitor.*` paths
- [x] 4.3 Update `test_cleanup.py` imports to use `focusmonitor.*` paths
- [x] 4.4 Run all tests and verify 80/80 pass
