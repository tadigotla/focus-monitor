"""Database initialization."""

import sqlite3
from focusmonitor.config import DB_PATH


def init_db():
    db = sqlite3.connect(str(DB_PATH))
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
    db.commit()
    return db
