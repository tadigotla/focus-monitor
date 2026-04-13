"""Unified cleanup — screenshots, database rows, log files."""

from datetime import datetime, timedelta
from focusmonitor.config import LOG_DIR
from focusmonitor.screenshots import cleanup_old_screenshots


def cleanup_old_db_rows(cfg, db):
    """Delete activity_log and nudges rows older than db_retention_days. Returns count."""
    days = cfg.get("db_retention_days", 30)
    if days <= 0:
        return 0
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    c1 = db.execute("DELETE FROM activity_log WHERE timestamp < ?", (cutoff,))
    c2 = db.execute("DELETE FROM nudges WHERE timestamp < ?", (cutoff,))
    total = (c1.rowcount or 0) + (c2.rowcount or 0)
    # Always commit — even when 0 rows are deleted.  The DELETE
    # statements start an implicit transaction that holds a RESERVED
    # lock in WAL mode.  Without an unconditional commit the lock
    # stays held on the long-lived monitor connection, blocking every
    # write from the dashboard's correction/confirmation endpoints.
    db.commit()
    return total


def cleanup_log_files(cfg):
    """Truncate log files exceeding log_max_size_mb, keeping the last 1MB. Returns count."""
    max_mb = cfg.get("log_max_size_mb", 5)
    if max_mb <= 0:
        return 0
    max_bytes = max_mb * 1024 * 1024
    keep_bytes = 1 * 1024 * 1024
    truncated = 0
    for name in ("stdout.log", "stderr.log"):
        path = LOG_DIR / name
        if not path.exists():
            continue
        if path.stat().st_size > max_bytes:
            data = path.read_bytes()
            path.write_bytes(data[-keep_bytes:])
            truncated += 1
    return truncated


def run_cleanup(cfg, db):
    """Run all cleanup operations. Print summary if anything was cleaned."""
    screenshots = cleanup_old_screenshots(cfg)
    db_rows = cleanup_old_db_rows(cfg, db)
    logs = cleanup_log_files(cfg)
    if screenshots or db_rows or logs:
        parts = []
        if screenshots:
            parts.append(f"{screenshots} screenshots")
        if db_rows:
            parts.append(f"{db_rows} DB rows")
        if logs:
            parts.append(f"{logs} logs truncated")
        print(f"  🧹 Cleanup: {', '.join(parts)}")
