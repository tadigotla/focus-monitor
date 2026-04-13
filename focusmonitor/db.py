"""Database initialization."""

import sqlite3
from focusmonitor.config import DB_PATH


def init_db():
    db = sqlite3.connect(str(DB_PATH))
    # WAL lets readers proceed without blocking writers and vice-versa.
    # The setting is persisted in the db file, so every subsequent
    # connection — including short-lived ones the dashboard opens
    # per request — automatically runs in WAL mode. Combined with a
    # generous busy_timeout, this removes the `database is locked`
    # races between run_analysis() and the dashboard correction
    # endpoints.
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA busy_timeout = 10000")
    db.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            window_titles TEXT,
            apps_used TEXT,
            project_detected TEXT,
            is_distraction INTEGER DEFAULT 0,
            summary TEXT,
            raw_response TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS nudges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            task TEXT,
            message TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start TEXT NOT NULL,
            end TEXT NOT NULL,
            task TEXT,
            task_name_confidence TEXT NOT NULL DEFAULT 'low',
            boundary_confidence TEXT NOT NULL DEFAULT 'low',
            cycle_count INTEGER NOT NULL DEFAULT 0,
            dip_count INTEGER NOT NULL DEFAULT 0,
            evidence_json TEXT NOT NULL DEFAULT '[]',
            kind TEXT NOT NULL DEFAULT 'session'
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            entry_kind TEXT NOT NULL,
            entry_id INTEGER NOT NULL,
            range_start TEXT NOT NULL,
            range_end TEXT NOT NULL,
            model_task TEXT,
            model_evidence TEXT NOT NULL DEFAULT '[]',
            model_boundary_confidence TEXT NOT NULL DEFAULT 'low',
            model_name_confidence TEXT NOT NULL DEFAULT 'low',
            user_verdict TEXT NOT NULL,
            user_task TEXT,
            user_kind TEXT NOT NULL,
            user_note TEXT,
            signals TEXT NOT NULL DEFAULT '{}'
        )
    """)
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_corrections_created_at "
        "ON corrections (created_at DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_corrections_entry "
        "ON corrections (entry_kind, entry_id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_range "
        "ON sessions (start, end)"
    )
    db.commit()
    return db
