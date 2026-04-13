## 1. Schema and Config

- [x] 1.1 Add `pending_data` table to `init_db()` in `focusmonitor/db.py`
- [x] 1.2 Add `batch_analysis` (bool, default `false`) and `batch_schedule` (list, default `["07:00", "12:00", "15:00", "18:00", "20:00"]`) to `DEFAULT_CONFIG` in `focusmonitor/config.py`

## 2. AW Event Snapshotting

- [x] 2.1 Add `snapshot_aw_events(cfg, minutes)` function to `focusmonitor/activitywatch.py` that returns the raw event list (reusing existing `get_aw_events` internals but returning the list rather than only the summary)

## 3. Collection Tick

- [x] 3.1 Add `collect_tick(cfg, db)` function in `focusmonitor/main.py` that takes a screenshot, snapshots AW events, and inserts a `pending_data` row
- [x] 3.2 Wire `collect_tick()` into the main loop when `batch_analysis` is `True`, replacing the direct `take_screenshot()` + `run_analysis()` calls on the screenshot timer

## 4. Refactor `run_analysis()` Signature

- [x] 4.1 Add optional `prefetched_events` and `prefetched_screenshots` kwargs to `run_analysis()` in `focusmonitor/analysis.py`
- [x] 4.2 Gate `get_aw_events()` and `recent_screenshots()` calls behind `is None` checks on the new kwargs
- [x] 4.3 Gate `check_nudges()` call on `cfg["batch_analysis"]` being `False`

## 5. Batch Processing

- [x] 5.1 Add `batch_analyze(cfg, db)` function in `focusmonitor/analysis.py` (or `focusmonitor/main.py`) that queries unprocessed `pending_data` rows, groups them into `analysis_interval_sec`-width windows, and calls `run_analysis()` with merged AW events and screenshot paths per window
- [x] 5.2 Mark `pending_data` rows as `processed = 1` after each window completes successfully

## 6. Main Loop Scheduling

- [x] 6.1 Add clock-check logic to the main loop: compare `HH:MM` against `batch_schedule`, maintain `fired_today` set, reset on date change
- [x] 6.2 Call `batch_analyze()` when a schedule slot matches and hasn't fired today
- [x] 6.3 Update startup banner to print batch mode status and schedule when `batch_analysis` is `True`

## 7. Tests

- [x] 7.1 Test `pending_data` table creation in `init_db()` (extend `test_db_schema.py`)
- [x] 7.2 Test `collect_tick()` inserts a row with screenshot path and AW events JSON
- [x] 7.3 Test `batch_analyze()` groups rows into correct windows and calls `run_analysis()` per window
- [x] 7.4 Test `batch_analyze()` marks rows as processed after completion
- [x] 7.5 Test `run_analysis()` uses prefetched data when provided, skips live queries
- [x] 7.6 Test clock-schedule matching and `fired_today` reset on date change
- [x] 7.7 Test that nudges are skipped when `batch_analysis` is `True`
- [x] 7.8 Verify all existing tests still pass (no regressions from signature change)
