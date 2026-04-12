## Context

The monitor currently has `cleanup_old_screenshots(cfg)` which deletes screenshots older than `screenshot_keep_hours` (default: 48h). It's called after each analysis cycle. There is no cleanup for `activity.db` rows or launchd log files. Screenshots are ~2MB each, taken every 2 minutes — ~1.4GB/day before cleanup kicks in.

## Goals / Non-Goals

**Goals:**
- Consolidate all cleanup into one function
- Add database row retention (prune old activity_log and nudges rows)
- Add log file size management
- Run cleanup at startup and after each analysis cycle

**Non-Goals:**
- Compressing or archiving old data (just delete it)
- Database vacuuming (SQLite auto-manages free space adequately)
- Backup mechanisms
- Export-before-delete functionality

## Decisions

### 1. Single `run_cleanup(cfg, db)` function

Consolidate screenshot cleanup, DB pruning, and log truncation into one function. Called at startup and after each analysis cycle.

**Rationale**: One function is easier to maintain and reason about than scattered cleanup calls.

### 2. DB retention via DELETE with timestamp comparison

```sql
DELETE FROM activity_log WHERE timestamp < ?
DELETE FROM nudges WHERE timestamp < ?
```

Using ISO timestamp string comparison works because the timestamps are stored in ISO format and sort lexicographically.

**Default**: 30 days. Configurable via `db_retention_days`. Set to 0 to disable.

### 3. Log truncation by keeping tail

When `stdout.log` or `stderr.log` exceeds `log_max_size_mb`, read the last 1MB and overwrite the file. This preserves recent logs while capping growth.

**Rationale**: Simple and effective. Log files only matter for recent debugging. The 1MB tail is enough for diagnosis.

**Default**: 5MB max. Configurable via `log_max_size_mb`. Set to 0 to disable.

## Risks / Trade-offs

- **[Data loss]** → Old analysis data is deleted permanently. Mitigated by a generous 30-day default and configurability. The dashboard only shows today's data anyway.
- **[Log truncation during write]** → If the monitor writes to the log while truncation happens, a line could be split. Mitigated by truncation happening rarely (only when > 5MB) and by keeping a generous tail (1MB).
