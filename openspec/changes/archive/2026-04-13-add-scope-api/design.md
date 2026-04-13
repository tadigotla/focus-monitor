## Context

Phase 1 added the `analysis_traces` table with full prompt/response/timing data. The existing tables (`activity_log`, `corrections`, `sessions`) already contain rich classification and feedback data. The planned Scope React UI needs a JSON API to consume all of this.

The existing Pulse dashboard (`focusmonitor/dashboard.py`) uses stdlib `http.server.ThreadingHTTPServer` bound to `127.0.0.1:9876`. It serves HTML, handles POST mutations with CSRF validation, and uses SQLite directly. The Scope API follows the same infrastructure pattern but is simpler: read-only JSON, no CSRF, separate port.

## Goals / Non-Goals

**Goals:**
- Serve JSON data from the existing SQLite DB for the Scope React UI
- Provide queryable access to cycles, traces, corrections, sessions, and learning statistics
- Bind to localhost only, preserving the privacy invariant
- Follow existing patterns (stdlib HTTP server, direct SQLite)

**Non-Goals:**
- Write endpoints — Scope is read-only
- Authentication — single-user localhost tool
- Rate limiting — single-user, local requests only
- Serving the React UI — that's Vite's job in dev, or a static build later

## Decisions

### D1. Separate server process, separate port

**Decision:** Scope API runs as its own process on `127.0.0.1:9877`, started via `python scope_api.py`. It does not run inside the Pulse monitor process.

**Why:** Pulse and Scope have different lifecycles. Pulse runs continuously as a background monitor. Scope runs when the developer wants to inspect. Coupling them would mean Scope infrastructure loads into every Pulse run, and Scope crashes could affect Pulse. Separate processes = separate failure domains.

### D2. stdlib `http.server`, not FastAPI or Flask

**Decision:** Use `http.server.ThreadingHTTPServer` and `BaseHTTPRequestHandler`, same as Pulse.

**Why:** No new runtime dependency. The API surface is small (~8 endpoints, all GET, all returning JSON). FastAPI would be nicer to write but adds `uvicorn`, `starlette`, `pydantic` — three new runtime deps that violate the "prefer stdlib" rule. The stdlib pattern is already proven in `focusmonitor/dashboard.py`.

### D3. Read-only SQLite connection

**Decision:** The API opens the DB with `PRAGMA query_only = ON` (SQLite 3.8+, well within Python 3.10's bundled version). This makes write attempts fail at the SQLite level, not just at the application level.

**Why:** Defense-in-depth. Even if a bug in a query function accidentally issues a write, SQLite rejects it. Combined with the fact that there are no POST endpoints, this makes the read-only contract structurally enforceable.

### D4. CORS allows localhost Vite dev server only

**Decision:** Responses include `Access-Control-Allow-Origin: http://localhost:5173` (the default Vite dev server port). For production builds served from the same origin, CORS isn't needed.

**Why:** During development, the React UI runs on Vite's dev server (`:5173`) and makes `fetch()` calls to the API (`:9877`). Without CORS headers, the browser blocks cross-origin requests. Allowing only `localhost:5173` keeps the policy tight.

### D5. Query functions are pure functions taking a DB connection

**Decision:** `scope/api/queries.py` contains functions like `get_cycles(db, date, limit, offset)` that take a `sqlite3.Connection` and return Python dicts/lists. The HTTP handlers call these and serialize to JSON.

**Why:** Testability. Query functions can be unit-tested with an in-memory SQLite DB populated with synthetic data, no HTTP server needed. The HTTP layer is a thin routing shell on top.

### D6. Stats endpoints compute aggregations in SQL

**Decision:** Learning statistics (correction rate, confidence calibration, per-task accuracy) are computed via SQL aggregation queries, not by loading all rows into Python and computing in-memory.

**Why:** The DB may have months of data. SQL aggregation is efficient and bounded by SQLite's query planner. Python-side aggregation would load unbounded result sets.

## API Endpoints

| Method | Path | Returns |
|--------|------|---------|
| GET | `/api/health` | `{"status": "ok", "db_path": "..."}` |
| GET | `/api/cycles?date=YYYY-MM-DD&limit=50&offset=0` | Paginated cycle list with timestamp, task, score, confidence |
| GET | `/api/cycles/:id` | Single cycle: full `activity_log` row + parsed `raw_response` |
| GET | `/api/cycles/:id/trace` | Full trace from `analysis_traces`: prompts, responses, timing |
| GET | `/api/cycles/:id/corrections` | Corrections filed against this cycle |
| GET | `/api/corrections?limit=50&offset=0` | All corrections, most-recent-first |
| GET | `/api/sessions?date=YYYY-MM-DD` | Sessions for a given day |
| GET | `/api/sessions/:id` | Single session with constituent cycle IDs |
| GET | `/api/stats/correction-rate?days=30` | Corrections per day over time |
| GET | `/api/stats/confidence-calibration` | Accuracy by confidence level |
| GET | `/api/stats/per-task-accuracy` | Accuracy breakdown by task name |

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| **Port conflict with other local services.** | Default `9877` is uncommon. Configurable via `scope_api_port`. |
| **DB locking contention with Pulse.** | SQLite WAL mode (already enabled by Pulse) allows concurrent readers. Scope only reads. `busy_timeout = 5000` handles transient locks. |
| **Privacy — exposing activity data on a local port.** | `127.0.0.1` binding means only local processes can connect. Same exposure model as Pulse's dashboard on `:9876`. No new risk surface. |

## Migration Plan

1. Create `scope/api/` directory with `queries.py` (query functions) and `server.py` (HTTP server).
2. Add tests for query functions with in-memory SQLite.
3. Add HTTP endpoint tests.
4. Add `scope_api.py` entrypoint, config key, gitignore updates, CLAUDE.md section.
5. Manual validation: start API, curl endpoints, verify JSON.
