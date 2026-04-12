## Why

Viewing the dashboard currently requires running `python3 dashboard.py` each time, which generates a throwaway temp file and opens a new browser tab. There's no persistent URL to bookmark, no auto-refresh, and no way to keep it open as a live view. The monitor should serve the dashboard on a local port so you can bookmark `localhost:9876` and see live data whenever you want.

## What Changes

- **Local HTTP dashboard server**: Replace the temp-file approach with a lightweight HTTP server (stdlib `http.server`) that serves the dashboard HTML on a configurable local port. The server runs as part of `monitor.py`'s main loop so there's no extra process to manage.
- **Auto-refresh**: The dashboard page auto-refreshes at a configurable interval (default: 60s) so an open browser tab always shows current data.
- **Unified CLI entry point**: Add a single `focusmonitor` CLI script with subcommands (`run`, `dashboard`, `setup`) instead of requiring users to know which `.py` file to invoke.
- **Dashboard always available**: The dashboard server starts automatically when the monitor runs — no separate command needed. A standalone `focusmonitor dashboard` command is also available for viewing without running the monitor.

## Capabilities

### New Capabilities
- `dashboard-server`: Local HTTP server that serves the dashboard on a persistent port with auto-refresh
- `cli-entrypoint`: Unified CLI with subcommands (`run`, `dashboard`, `setup`) replacing direct script invocation

### Modified Capabilities

(none — no existing spec requirements are changing)

## Impact

- **dashboard.py**: Refactored from a one-shot script to a module that can both generate HTML and serve it over HTTP. The `build_dashboard()` function remains but now returns HTML instead of writing to a temp file.
- **monitor.py**: Starts the dashboard server thread alongside the main monitoring loop.
- **New file**: `cli.py` — thin entry point that dispatches to subcommands.
- **setup.py**: Updated to register the `focusmonitor` CLI command and mention the dashboard URL.
- **Config**: New keys `dashboard_port` (default: 9876) and `dashboard_refresh_sec` (default: 60).
- **Dependencies**: None — uses only stdlib (`http.server`, `threading`).
