## Why

Phase 1 (`add-analysis-trace-logging`) captures full prompt text, raw responses, timing, and few-shot context for every analysis cycle. But this data sits in a SQLite table with no way to view it except raw `sqlite3` queries. The planned Scope UI (React) needs a JSON API to read from.

This change creates the Scope API: a lightweight, read-only Python HTTP server that serves JSON from the existing SQLite DB. It runs on its own port (`127.0.0.1:9877`), opens the DB in read-only mode, and provides endpoints for querying cycles, traces, corrections, sessions, and aggregated learning statistics.

The API is deliberately separate from the existing Pulse dashboard server — different port, different process, different purpose. Pulse serves HTML for the productivity dashboard. Scope API serves JSON for the learning inspector.

## What Changes

- **New `scope/` directory** at the repo root, containing `scope/api/server.py` and `scope/api/queries.py`.
- **Read-only HTTP server** binding to `127.0.0.1:9877` using stdlib `http.server` (same pattern as Pulse's `focusmonitor/dashboard.py`).
- **JSON API endpoints** for cycles, traces, corrections, sessions, and aggregated stats.
- **CORS headers** allowing `localhost:5173` (the Vite dev server for Phase 3's React UI) — still localhost-only.
- **Config key** `scope_api_port` (default `9877`) in Pulse's `DEFAULT_CONFIG`.
- **`.gitignore` update** for `scope/ui/node_modules/` and `scope/ui/dist/` (prepping for Phase 3).
- **`CLAUDE.md` update** documenting the Scope companion and naming convention (Pulse / Scope).
- **New entrypoint** `scope_api.py` at the repo root (like `monitor.py`, `dashboard.py`, `cli.py`).

Explicitly out of scope:
- The React UI (Phase 3)
- Write endpoints — Scope never writes to the DB
- Authentication — localhost-only, single-user tool
- CSRF — no mutations, so no CSRF needed

## Capabilities

### New Capabilities
- `scope-api`: Read-only JSON API serving analysis traces, cycles, corrections, sessions, and aggregated learning statistics from the existing SQLite DB.

## Impact

**New code:**
- `scope/__init__.py`
- `scope/api/__init__.py`
- `scope/api/server.py` — HTTP server, request routing, CORS, response serialization
- `scope/api/queries.py` — SQL query functions, data transformation
- `scope_api.py` — top-level entrypoint
- `tests/test_scope_api.py` — unit tests for queries and HTTP endpoints

**Modified code:**
- `focusmonitor/config.py` — add `scope_api_port` to `DEFAULT_CONFIG`
- `.gitignore` — add `scope/ui/node_modules/` and `scope/ui/dist/`
- `CLAUDE.md` — add Scope section

**Dependencies:** None added. Pure stdlib.

**Network:** New server binds to `127.0.0.1:9877`. Localhost only. No outbound calls. CORS allows `localhost:5173` only. Privacy posture preserved.

**Privacy impact:** None. The API exposes data already in `~/.focus-monitor/activity.db` on a localhost-only port. It introduces no new outbound HTTP target, no new dependency, no telemetry, and no non-loopback binding.
