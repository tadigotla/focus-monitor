"""Main loop and startup."""

import json
import time
from datetime import datetime, timezone
from focusmonitor.config import load_config, TASKS_JSON_FILE, DISCOVERED_FILE
from focusmonitor.db import init_db
from focusmonitor.screenshots import take_screenshot
from focusmonitor.analysis import run_analysis, batch_analyze
from focusmonitor.activitywatch import get_afk_state, snapshot_aw_events
from focusmonitor.cleanup import run_cleanup
from focusmonitor.tasks import load_planned_tasks


def should_skip_tick(cfg):
    state = get_afk_state(cfg)
    if state["status"] != "afk":
        return False
    since = state["since"]
    if since is None:
        return False
    elapsed = (datetime.now(timezone.utc) - since).total_seconds()
    return elapsed >= cfg["idle_skip_grace_sec"]


def collect_tick(cfg, db):
    """Capture a screenshot + AW snapshot and stage for later analysis."""
    path = take_screenshot()
    if path:
        print(f"📸 Screenshot: {path.name}")
    minutes = cfg["screenshot_interval_sec"] // 60 or 1
    events = snapshot_aw_events(cfg, minutes=minutes)
    ts = datetime.now().isoformat()
    db.execute(
        "INSERT INTO pending_data (collected_at, screenshot_path, aw_events_json, processed) "
        "VALUES (?, ?, ?, 0)",
        (ts, str(path) if path else None, json.dumps(events)),
    )
    db.commit()


def main():
    cfg = load_config()
    db = init_db()

    # Start dashboard server
    from focusmonitor.dashboard import start_dashboard_server
    port = cfg["dashboard_port"]
    dash_thread = start_dashboard_server(port, cfg["dashboard_refresh_sec"])

    print("=" * 60)
    print("  Focus Monitor — local AI productivity tracker")
    print("=" * 60)
    print(f"  Screenshots every {cfg['screenshot_interval_sec']}s")
    print(f"  Analysis every {cfg['analysis_interval_sec']}s")
    print(f"  Idle skip grace: {cfg['idle_skip_grace_sec']}s")
    print(f"  Nudge threshold: {cfg['nudge_after_hours']}h")
    print(f"  Planned tasks: {TASKS_JSON_FILE}")
    print(f"  Discovered activities: {DISCOVERED_FILE}")
    print(f"  Ollama model: {cfg['ollama_model']}")
    mode = "two-pass" if cfg["two_pass_analysis"] else "single-pass"
    print(f"  Analysis mode: {mode}")
    print(f"  History window: {cfg['history_window']} entries")
    print(f"  Dedup threshold: {cfg['dedup_size_threshold_pct']}%")
    if dash_thread:
        print(f"  Dashboard: http://localhost:{port}")
    batch_mode = cfg.get("batch_analysis", False)
    if batch_mode:
        schedule = cfg.get("batch_schedule", [])
        print(f"  Batch mode: ON — schedule: {', '.join(schedule)}")
    else:
        print(f"  Batch mode: OFF (live analysis)")
    print("=" * 60)

    tasks = load_planned_tasks()
    if not tasks:
        print(f"\n⚠️  No planned tasks found. Edit {TASKS_JSON_FILE} to get started.\n")
    else:
        print(f"\n📋 Tracking {len(tasks)} planned tasks:")
        for t in tasks:
            sig_count = len(t.get("signals", []))
            sig_info = f" ({sig_count} signals)" if sig_count else " (no signals)"
            print(f"   • {t['name']}{sig_info}")
        print()

    # Startup cleanup
    run_cleanup(cfg, db)

    last_screenshot = 0
    last_analysis = 0
    was_idle = False
    fired_today = set()
    today_date = datetime.now().date()

    try:
        while True:
            now = time.time()

            # Reset fired schedule slots on date change.
            current_date = datetime.now().date()
            if current_date != today_date:
                fired_today = set()
                today_date = current_date

            if batch_mode:
                # --- Batch mode: collect only, trigger analysis on schedule ---
                screenshot_due = now - last_screenshot >= cfg["screenshot_interval_sec"]
                if screenshot_due:
                    if should_skip_tick(cfg):
                        if not was_idle:
                            print("💤 idle — skipping capture")
                        was_idle = True
                    else:
                        if was_idle:
                            print("▶️  resumed")
                        was_idle = False
                        collect_tick(cfg, db)
                    last_screenshot = now

                # Check clock-based batch schedule.
                now_hm = datetime.now().strftime("%H:%M")
                schedule = cfg.get("batch_schedule", [])
                if now_hm in schedule and now_hm not in fired_today:
                    batch_analyze(cfg, db)
                    run_cleanup(cfg, db)
                    fired_today.add(now_hm)
            else:
                # --- Live mode: original behavior ---
                screenshot_due = now - last_screenshot >= cfg["screenshot_interval_sec"]
                analysis_due = now - last_analysis >= cfg["analysis_interval_sec"]

                if screenshot_due or analysis_due:
                    if should_skip_tick(cfg):
                        if not was_idle:
                            print("💤 idle — skipping capture")
                        was_idle = True
                        if screenshot_due:
                            last_screenshot = now
                        if analysis_due:
                            run_cleanup(cfg, db)
                            last_analysis = now
                    else:
                        if was_idle:
                            print("▶️  resumed")
                        was_idle = False
                        if screenshot_due:
                            path = take_screenshot()
                            if path:
                                print(f"📸 Screenshot: {path.name}")
                            last_screenshot = now
                        if analysis_due:
                            run_analysis(cfg, db)
                            run_cleanup(cfg, db)
                            last_analysis = now

            time.sleep(5)

    except KeyboardInterrupt:
        print("\n\n👋 Focus Monitor stopped.")
        db.close()
