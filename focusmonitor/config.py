"""Configuration, path constants, and defaults."""

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".focus-monitor"
DB_PATH = CONFIG_DIR / "activity.db"
SCREENSHOT_DIR = CONFIG_DIR / "screenshots"
TASKS_FILE = CONFIG_DIR / "planned_tasks.txt"
TASKS_JSON_FILE = CONFIG_DIR / "planned_tasks.json"
DISCOVERED_FILE = CONFIG_DIR / "discovered_activities.json"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_DIR = CONFIG_DIR / "logs"

DEFAULT_CONFIG = {
    "screenshot_interval_sec": 300,
    "analysis_interval_sec": 3600,
    "nudge_after_hours": 2,
    "screenshot_keep_hours": 48,
    "ollama_model": "llama3.2-vision",
    "ollama_url": "http://localhost:11434",
    "activitywatch_url": "http://localhost:5600",
    "ollama_keep_alive": "30s",
    "screenshots_per_analysis": 12,
    "max_parse_retries": 1,
    "dedup_size_threshold_pct": 2,
    "two_pass_analysis": True,
    "history_window": 3,
    "dashboard_port": 9876,
    "dashboard_refresh_sec": 60,
    "db_retention_days": 30,
    "log_max_size_mb": 5,
    # Seconds of continuous AFK (per ActivityWatch) before the main loop
    # skips screenshot + analysis ticks. Set very large (e.g. 86400) to
    # effectively disable the gate; set to 0 to skip immediately on AFK.
    "idle_skip_grace_sec": 60,
    # Pass 1 returns a typed artifact per screenshot instead of free-form
    # prose when true. See openspec change task-recognition-loop.
    "pass1_structured": True,
    # Most-recent-N user corrections injected as few-shot examples into
    # the Pass 2 classification prompt. 0 disables retrieval entirely.
    "corrections_few_shot_n": 5,
    # Maximum duration of a non-matching "dip" cycle absorbed into the
    # surrounding session by the deterministic aggregator.
    "session_dip_tolerance_sec": 300,
    # When false, skip session aggregation and render the legacy
    # per-cycle view. Useful as a diagnostic escape hatch.
    "session_aggregation_enabled": True,
}

DEFAULT_PLANNED_TASKS = [
    {
        "name": "Example Project",
        "signals": ["example", "project-name"],
        "apps": ["VS Code", "Terminal"],
        "notes": "Replace this with your actual project. Signals are keywords that appear in window titles when you're working on it."
    }
]


def load_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2))

    # Migrate planned_tasks.txt → planned_tasks.json
    if not TASKS_JSON_FILE.exists():
        if TASKS_FILE.exists():
            lines = TASKS_FILE.read_text().strip().splitlines()
            entries = [l.strip() for l in lines
                       if l.strip() and not l.strip().startswith("#")]
            migrated = [{"name": name, "signals": [], "apps": [], "notes": ""}
                        for name in entries]
            TASKS_JSON_FILE.write_text(json.dumps(migrated, indent=2))
            TASKS_FILE.rename(TASKS_FILE.with_suffix(".txt.bak"))
            print(f"📋 Migrated {len(migrated)} tasks from planned_tasks.txt → planned_tasks.json")
            print(f"   Add 'signals' to each task for better matching!")
        else:
            TASKS_JSON_FILE.write_text(json.dumps(DEFAULT_PLANNED_TASKS, indent=2))
            print(f"📝 Created {TASKS_JSON_FILE} — edit it with your projects and signals.")

    cfg = DEFAULT_CONFIG.copy()
    cfg.update(json.loads(CONFIG_FILE.read_text()))
    return cfg
