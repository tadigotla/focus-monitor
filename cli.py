#!/usr/bin/env python3
"""
Focus Monitor CLI — unified entry point.

Usage:
  python3 cli.py run         Start monitor + live dashboard (default)
  python3 cli.py dashboard   Start only the dashboard server
  python3 cli.py setup       Run first-time setup
"""

import argparse
import sys
from pathlib import Path


def cmd_run(args):
    """Start the monitor with the dashboard server."""
    from focusmonitor.main import main
    main()


def cmd_dashboard(args):
    """Start only the dashboard server (no monitoring)."""
    from focusmonitor.config import load_config, DB_PATH
    from focusmonitor.dashboard import start_dashboard_server

    if not DB_PATH.exists():
        print("No activity database found. Run 'python3 cli.py run' first.")
        sys.exit(1)

    cfg = load_config()
    port = cfg["dashboard_port"]
    refresh = cfg["dashboard_refresh_sec"]

    thread = start_dashboard_server(port, refresh)
    if thread is None:
        sys.exit(1)

    print(f"📊 Dashboard server running at http://localhost:{port}")
    print(f"   Auto-refresh: every {refresh}s")
    print("   Press Ctrl+C to stop.\n")

    try:
        thread.join()
    except KeyboardInterrupt:
        print("\n👋 Dashboard server stopped.")


def cmd_setup(args):
    """Run the setup script."""
    from setup import main
    main()


def main():
    parser = argparse.ArgumentParser(
        prog="focusmonitor",
        description="Focus Monitor — local AI productivity tracker",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run", help="Start monitor + live dashboard (default)")
    sub.add_parser("dashboard", help="Start only the dashboard server")
    sub.add_parser("setup", help="Run first-time setup")

    args = parser.parse_args()

    commands = {
        "run": cmd_run,
        "dashboard": cmd_dashboard,
        "setup": cmd_setup,
    }

    # Default to "run" if no subcommand given
    cmd = args.command or "run"
    commands[cmd](args)


if __name__ == "__main__":
    main()
