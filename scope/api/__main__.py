"""`python -m scope.api` entrypoint for the Scope API server."""

from focusmonitor.config import load_config, DB_PATH
from focusmonitor.db import init_db
from scope.api.server import start_scope_server


def main():
    cfg = load_config()
    port = cfg.get("scope_api_port", 9877)

    if not DB_PATH.exists():
        print(f"⚠️  Database not found at {DB_PATH}")
        print("   Run Pulse first to create it.")
        return

    db = init_db()
    db.close()

    start_scope_server(port, DB_PATH)


if __name__ == "__main__":
    main()
