"""Main loop and startup."""

import time
from focusmonitor.config import load_config, TASKS_JSON_FILE, DISCOVERED_FILE
from focusmonitor.db import init_db
from focusmonitor.screenshots import take_screenshot
from focusmonitor.analysis import run_analysis
from focusmonitor.cleanup import run_cleanup
from focusmonitor.tasks import load_planned_tasks


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

    try:
        while True:
            now = time.time()

            if now - last_screenshot >= cfg["screenshot_interval_sec"]:
                path = take_screenshot()
                if path:
                    print(f"📸 Screenshot: {path.name}")
                last_screenshot = now

            if now - last_analysis >= cfg["analysis_interval_sec"]:
                run_analysis(cfg, db)
                run_cleanup(cfg, db)
                last_analysis = now

            time.sleep(5)

    except KeyboardInterrupt:
        print("\n\n👋 Focus Monitor stopped.")
        db.close()
