## Context

The dashboard is currently a one-shot script (`dashboard.py`) that queries SQLite, renders HTML via string replacement, writes it to a temp file, and opens it with `webbrowser.open()`. Every view requires a terminal command and creates a new browser tab. The monitor (`monitor.py`) runs as a long-lived process via launchd but has no HTTP capabilities.

## Goals / Non-Goals

**Goals:**
- Serve the dashboard on a persistent local URL (e.g., `http://localhost:9876`)
- Auto-refresh the page so an open tab stays current
- Start the server automatically when the monitor runs
- Provide a unified CLI (`focusmonitor run`, `focusmonitor dashboard`, `focusmonitor setup`)
- Zero new dependencies — stdlib only

**Non-Goals:**
- WebSocket-based real-time updates (auto-refresh via meta tag is sufficient)
- Authentication or HTTPS (local-only, single-user)
- REST API endpoints for programmatic access
- Rewriting the dashboard frontend (HTML/CSS stays the same)
- Making the server accessible over the network (binds to 127.0.0.1 only)

## Decisions

### 1. Stdlib `http.server` in a daemon thread

**Rationale**: The simplest approach — spin up a `ThreadingHTTPServer` on a daemon thread inside `monitor.py`'s main process. When the monitor exits, the server thread dies automatically. No extra process management.

**Alternative considered**: Separate process via `subprocess.Popen` or a standalone server script. More complex, requires process lifecycle management, and means the dashboard might outlive or precede the monitor.

### 2. Dynamic HTML generation per request (no static file)

**Rationale**: Each GET to `/` calls `build_dashboard()` which queries SQLite and returns fresh HTML. This avoids stale data, file I/O, and cache invalidation concerns. SQLite queries are fast (~5ms for a day's data) so this is fine for a single-user local tool.

**Alternative considered**: Writing HTML to a file periodically and serving it statically. Simpler server code but introduces staleness and file management.

### 3. Auto-refresh via HTML `<meta>` tag

**Rationale**: Adding `<meta http-equiv="refresh" content="60">` to the dashboard HTML is the simplest auto-refresh mechanism. No JavaScript, no WebSockets, works in every browser.

**Trade-off**: Full page reload every 60s. Acceptable for a dashboard that's glanced at occasionally. The refresh interval is configurable via `dashboard_refresh_sec`.

### 4. Unified CLI via `cli.py` with argparse

**Rationale**: A single `cli.py` entry point with `argparse` subcommands replaces knowing which script to run. Users type `python3 cli.py run` instead of `python3 monitor.py`.

**Subcommands**:
- `run` — starts monitor + dashboard server (default)
- `dashboard` — starts only the dashboard server (for viewing without monitoring)
- `setup` — runs the setup script

**Alternative considered**: Using `__main__.py` with a package structure. Overkill for 3 Python files; argparse in a single file is sufficient.

### 5. Dashboard port defaults to 9876, binds to 127.0.0.1

**Rationale**: Port 9876 is unlikely to conflict. Binding to `127.0.0.1` ensures the dashboard is only accessible locally, maintaining the privacy-first design. Config key `dashboard_port` allows changing it.

## Risks / Trade-offs

- **[Port conflict]** → If 9876 is in use, the server fails to start. Mitigated by catching `OSError` and printing a clear message suggesting a different port via config.
- **[Thread safety with SQLite]** → SQLite in WAL mode supports concurrent readers. The dashboard thread only reads; the monitor thread writes. No locking issues expected. Connection created per-request to avoid cross-thread sharing.
- **[Meta refresh interrupts reading]** → If someone is reading a long timeline, the page refreshes. Mitigated by a generous default (60s) and configurability. Could be improved later with JS-based refresh that only updates changed content.
