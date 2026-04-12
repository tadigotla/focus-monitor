## 1. Config

- [x] 1.1 Add `db_retention_days` (30) and `log_max_size_mb` (5) to `DEFAULT_CONFIG` in monitor.py

## 2. Unified Cleanup Function

- [x] 2.1 Add `cleanup_old_db_rows(cfg, db)` function that deletes `activity_log` and `nudges` rows older than `db_retention_days`. Returns count of deleted rows. Skip if `db_retention_days` is 0
- [x] 2.2 Add `cleanup_log_files(cfg)` function that truncates `stdout.log` and `stderr.log` in `~/.focus-monitor/logs/` when they exceed `log_max_size_mb`, keeping the last 1MB. Returns count of truncated files. Skip if `log_max_size_mb` is 0
- [x] 2.3 Add `run_cleanup(cfg, db)` function that calls `cleanup_old_screenshots(cfg)`, `cleanup_old_db_rows(cfg, db)`, and `cleanup_log_files(cfg)`. Print a summary line only if something was cleaned

## 3. Integration

- [x] 3.1 Replace the `cleanup_old_screenshots(cfg)` call in the main loop with `run_cleanup(cfg, db)`
- [x] 3.2 Add a `run_cleanup(cfg, db)` call at startup in `main()`, after `init_db()` and before the main loop

## 4. Testing

- [x] 4.1 Test: DB cleanup deletes old rows, respects retention period, skips when disabled
- [x] 4.2 Test: Log truncation caps file size, keeps tail, skips when disabled or file missing
- [x] 4.3 Test: `run_cleanup` calls all three cleanup functions
