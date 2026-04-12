## 1. Config Updates

- [x] 1.1 Add `dashboard_port` (9876) and `dashboard_refresh_sec` (60) to `DEFAULT_CONFIG` in monitor.py

## 2. Dashboard Refactor

- [x] 2.1 Refactor `build_dashboard()` in dashboard.py to accept a `refresh_sec` parameter and return HTML string instead of writing to a temp file. Add `<meta http-equiv="refresh">` tag when `refresh_sec > 0`
- [x] 2.2 Keep backward compatibility: when dashboard.py is run directly (`__main__`), fall back to the temp-file + browser-open behavior using the refactored function

## 3. Dashboard HTTP Server

- [x] 3.1 Add a `DashboardHandler` class (subclass `http.server.BaseHTTPRequestHandler`) in dashboard.py that handles GET `/` by calling `build_dashboard()` and returning the HTML
- [x] 3.2 Add a `start_dashboard_server(port, refresh_sec)` function that creates a `ThreadingHTTPServer` on 127.0.0.1, starts it in a daemon thread, and returns the thread. Handle `OSError` for port conflicts gracefully
- [x] 3.3 Integrate into monitor.py: call `start_dashboard_server()` at startup, print the dashboard URL in the banner

## 4. Unified CLI

- [x] 4.1 Create `cli.py` with argparse: subcommands `run` (default), `dashboard`, `setup`
- [x] 4.2 `run` subcommand: calls monitor.py's `main()` (which now includes the dashboard server)
- [x] 4.3 `dashboard` subcommand: starts only the dashboard server and blocks until Ctrl+C. Print error if no database exists
- [x] 4.4 `setup` subcommand: calls setup.py's `main()`

## 5. Setup & Documentation

- [x] 5.1 Update setup.py to mention the dashboard URL and `cli.py` in the "Next steps" output
- [x] 5.2 Test: verify dashboard serves on localhost, auto-refreshes, monitor starts server automatically, CLI subcommands work, port conflict is handled gracefully
