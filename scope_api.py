#!/usr/bin/env python3
"""Scope API server entrypoint.

Start the read-only JSON API for the Scope companion:
    python scope_api.py [--port PORT]
"""

import argparse

from focusmonitor.config import load_config, DB_PATH
from focusmonitor.db import init_db
from scope.api.server import start_scope_server


def main():
    cfg = load_config()
    default_port = cfg.get("scope_api_port", 9877)

    parser = argparse.ArgumentParser(description="Scope API server")
    parser.add_argument("--port", type=int, default=default_port,
                        help=f"Port to bind (default: {default_port})")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"⚠️  Database not found at {DB_PATH}")
        print("   Run the monitor first to create it.")
        return

    # Ensure all tables exist (including analysis_traces added in
    # Phase 1). init_db uses CREATE TABLE IF NOT EXISTS so this is
    # safe against an already-up-to-date DB.
    db = init_db()
    db.close()

    start_scope_server(args.port, DB_PATH)


if __name__ == "__main__":
    main()
