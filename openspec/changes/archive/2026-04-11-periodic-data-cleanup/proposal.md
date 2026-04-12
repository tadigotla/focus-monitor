## Why

Screenshots accumulate at ~2MB each (every 2 minutes), reaching ~1.4GB/day. The existing `cleanup_old_screenshots()` runs on a 48h window but only triggers during analysis cycles (every 30 min). Meanwhile, `activity.db` and launchd log files (`stdout.log`, `stderr.log`) grow indefinitely with no cleanup. Over weeks of continuous use, disk usage becomes a problem.

## What Changes

- **Database retention**: Prune `activity_log` and `nudges` rows older than a configurable retention period (default: 30 days). Old analysis data loses value quickly.
- **Log rotation**: Truncate launchd log files (`~/.focus-monitor/logs/stdout.log`, `stderr.log`) when they exceed a configurable size (default: 5MB). Keep the most recent content.
- **Unified cleanup function**: Consolidate all cleanup (screenshots, DB, logs) into a single `run_cleanup()` function that runs once per analysis cycle, replacing the scattered `cleanup_old_screenshots()` call.
- **Startup cleanup**: Run cleanup once at monitor startup to clear any backlog from downtime.

## Capabilities

### New Capabilities
- `data-retention`: Configurable retention periods for database rows and log file size limits, with automated periodic cleanup

### Modified Capabilities

(none — no existing spec requirements are changing)

## Impact

- **monitor.py**: New `run_cleanup()` function replaces direct `cleanup_old_screenshots()` calls. New config keys for retention and log limits. Cleanup also runs at startup.
- **Config**: New keys `db_retention_days` (default: 30) and `log_max_size_mb` (default: 5).
- **Database**: Old rows deleted (irreversible but low-value data).
- **Dependencies**: None.
