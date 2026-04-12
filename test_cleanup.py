#!/usr/bin/env python3
"""Tests for periodic data cleanup functions."""

import json
import sqlite3
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta

passed = 0
failed = 0


def test(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}")


tmpdir = Path(tempfile.mkdtemp())

# Patch paths
import focusmonitor.cleanup as cleanup_mod
import focusmonitor.config as config_mod
original_log_dir = cleanup_mod.LOG_DIR
cleanup_mod.LOG_DIR = tmpdir / "logs"
cleanup_mod.LOG_DIR.mkdir()


# ── 4.1: DB cleanup ─────────────────────────────────────────────────────────

print("\n== DB Cleanup ==")

db = sqlite3.connect(":memory:")
db.execute("""CREATE TABLE activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT, window_titles TEXT, apps_used TEXT,
    project_detected TEXT, is_distraction INTEGER, summary TEXT, raw_response TEXT
)""")
db.execute("""CREATE TABLE nudges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT, task TEXT, message TEXT
)""")

# Insert old and recent rows
old_ts = (datetime.now() - timedelta(days=60)).isoformat()
recent_ts = (datetime.now() - timedelta(days=5)).isoformat()
now_ts = datetime.now().isoformat()

db.execute("INSERT INTO activity_log (timestamp, summary) VALUES (?, 'old')", (old_ts,))
db.execute("INSERT INTO activity_log (timestamp, summary) VALUES (?, 'recent')", (recent_ts,))
db.execute("INSERT INTO activity_log (timestamp, summary) VALUES (?, 'now')", (now_ts,))
db.execute("INSERT INTO nudges (timestamp, task) VALUES (?, 'old task')", (old_ts,))
db.execute("INSERT INTO nudges (timestamp, task) VALUES (?, 'new task')", (now_ts,))
db.commit()

# Default 30 days retention
cfg = {"db_retention_days": 30}
deleted = cleanup_mod.cleanup_old_db_rows(cfg, db)
test("deletes old rows", deleted == 2)  # 1 activity_log + 1 nudge

remaining = db.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
test("recent rows kept", remaining == 2)

remaining_nudges = db.execute("SELECT COUNT(*) FROM nudges").fetchone()[0]
test("recent nudges kept", remaining_nudges == 1)

# Disabled
cfg_disabled = {"db_retention_days": 0}
deleted = cleanup_mod.cleanup_old_db_rows(cfg_disabled, db)
test("disabled returns 0", deleted == 0)

# Custom retention — after previous cleanup, we have 2 activity rows (recent + now)
# Add back and test with 3-day retention which should prune the 5-day-old "recent" row
before = db.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
cfg_short = {"db_retention_days": 3}
deleted = cleanup_mod.cleanup_old_db_rows(cfg_short, db)
after = db.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
test("custom retention prunes correctly", deleted == 1 and after == before - 1)

db.close()


# ── 4.2: Log truncation ─────────────────────────────────────────────────────

print("\n== Log Truncation ==")

# Create oversized log file
big_log = cleanup_mod.LOG_DIR / "stdout.log"
big_log.write_bytes(b"A" * (6 * 1024 * 1024))  # 6MB

small_log = cleanup_mod.LOG_DIR / "stderr.log"
small_log.write_bytes(b"B" * (100 * 1024))  # 100KB

cfg_log = {"log_max_size_mb": 5}
truncated = cleanup_mod.cleanup_log_files(cfg_log)
test("truncates oversized log", truncated == 1)
test("keeps under 1MB after truncation", big_log.stat().st_size == 1 * 1024 * 1024)
test("small log untouched", small_log.stat().st_size == 100 * 1024)

# Keeps tail content
big_log.write_bytes(b"X" * (5 * 1024 * 1024) + b"TAIL_CONTENT")
cleanup_mod.cleanup_log_files(cfg_log)
content = big_log.read_bytes()
test("keeps tail content", content.endswith(b"TAIL_CONTENT"))

# Disabled
big_log.write_bytes(b"C" * (10 * 1024 * 1024))
cfg_disabled = {"log_max_size_mb": 0}
truncated = cleanup_mod.cleanup_log_files(cfg_disabled)
test("disabled returns 0", truncated == 0)
test("file unchanged when disabled", big_log.stat().st_size == 10 * 1024 * 1024)

# Missing log file
(cleanup_mod.LOG_DIR / "stdout.log").unlink()
(cleanup_mod.LOG_DIR / "stderr.log").unlink()
truncated = cleanup_mod.cleanup_log_files({"log_max_size_mb": 5})
test("missing files handled", truncated == 0)


# ── 4.3: run_cleanup calls all three ────────────────────────────────────────

print("\n== run_cleanup Integration ==")

# Verify run_cleanup doesn't crash with a real DB
db2 = sqlite3.connect(":memory:")
db2.execute("""CREATE TABLE activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT, window_titles TEXT, apps_used TEXT,
    project_detected TEXT, is_distraction INTEGER, summary TEXT, raw_response TEXT
)""")
db2.execute("""CREATE TABLE nudges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT, task TEXT, message TEXT
)""")
db2.commit()

full_cfg = config_mod.DEFAULT_CONFIG.copy()
# Should not crash even with nothing to clean
cleanup_mod.run_cleanup(full_cfg, db2)
test("run_cleanup completes without error", True)

# Insert old data and verify cleanup works end-to-end
old_ts = (datetime.now() - timedelta(days=60)).isoformat()
db2.execute("INSERT INTO activity_log (timestamp, summary) VALUES (?, 'old')", (old_ts,))
db2.commit()
cleanup_mod.run_cleanup(full_cfg, db2)
remaining = db2.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
test("run_cleanup prunes DB via cleanup_old_db_rows", remaining == 0)

db2.close()


# ── Verify existing tests still pass ─────────────────────────────────────────

print("\n== Config Keys ==")
test("db_retention_days in DEFAULT_CONFIG", config_mod.DEFAULT_CONFIG["db_retention_days"] == 30)
test("log_max_size_mb in DEFAULT_CONFIG", config_mod.DEFAULT_CONFIG["log_max_size_mb"] == 5)


# ── Cleanup ──────────────────────────────────────────────────────────────────

cleanup_mod.LOG_DIR = original_log_dir
shutil.rmtree(tmpdir, ignore_errors=True)

print(f"\n{'='*50}")
print(f"  Results: {passed} passed, {failed} failed")
print(f"{'='*50}")

exit(0 if failed == 0 else 1)
