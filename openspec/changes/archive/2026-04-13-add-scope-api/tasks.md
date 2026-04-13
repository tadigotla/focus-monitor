## 1. Directory structure and config

- [x] 1.1 Create `scope/__init__.py` and `scope/api/__init__.py` (empty init files).
- [x] 1.2 Add `"scope_api_port": 9877` to `DEFAULT_CONFIG` in `focusmonitor/config.py`.
- [x] 1.3 Add `scope/ui/node_modules/` and `scope/ui/dist/` to `.gitignore`.
- [x] 1.4 Add a "Scope — AI Decision Inspector" section to `CLAUDE.md` documenting: what Scope is, the Pulse/Scope naming convention, the `scope/` directory layout, the localhost-only binding, the read-only DB contract, and that `npm install` in `scope/ui/` is a one-time dev-machine action (same class as pip install).

## 2. Query functions

- [x] 2.1 Create `scope/api/queries.py` with a `get_cycles(db, date, limit, offset)` function that queries `activity_log` for the given date range, parses `raw_response` JSON, and returns a list of cycle dicts with: `id`, `timestamp`, `task`, `focus_score`, `name_confidence`, `boundary_confidence`, `summary`.
- [x] 2.2 Add `get_cycle(db, cycle_id)` — returns a single cycle dict with full `raw_response` fields (evidence, artifacts, etc.) or `None` if not found.
- [x] 2.3 Add `get_cycle_trace(db, cycle_id)` — queries `analysis_traces` by `activity_log_id`, parses JSON array columns, returns the trace dict or `None`.
- [x] 2.4 Add `get_cycle_corrections(db, cycle_id)` — queries `corrections` where `entry_kind='cycle' AND entry_id=?`, returns list of correction dicts.
- [x] 2.5 Add `get_corrections(db, limit, offset)` — queries all corrections ordered by `created_at DESC`, returns list.
- [x] 2.6 Add `get_sessions(db, date)` — queries `sessions` for the given date range, returns list of session dicts.
- [x] 2.7 Add `get_session(db, session_id)` — returns single session dict with constituent `activity_log` cycle IDs (queried by time range overlap) or `None`.
- [x] 2.8 Add `get_correction_rate(db, days)` — SQL aggregation: corrections per day over the last N days, returns list of `{date, total_cycles, corrections, rate}`.
- [x] 2.9 Add `get_confidence_calibration(db)` — for each confidence level (high/medium/low), compute the fraction of cycles at that level that were NOT subsequently corrected. Returns dict.
- [x] 2.10 Add `get_per_task_accuracy(db)` — group cycles by task name, compute correction rate per task. Returns list of `{task, total, corrected, accuracy}`.
- [x] 2.11 Add unit tests in `tests/test_scope_api.py` for each query function using an in-memory SQLite DB populated via `init_db()` + synthetic data inserts.

## 3. HTTP server

- [x] 3.1 Create `scope/api/server.py` with a `ScopeHandler(BaseHTTPRequestHandler)` class and a `start_scope_server(port, db_path)` function.
- [x] 3.2 Open the SQLite DB with `PRAGMA query_only = ON` and `PRAGMA busy_timeout = 5000`.
- [x] 3.3 Implement request routing in `do_GET`: parse the URL path, match against endpoint patterns, dispatch to handler methods.
- [x] 3.4 Implement `GET /api/health` — return `{"status": "ok"}`.
- [x] 3.5 Implement `GET /api/cycles` — parse `?date=`, `?limit=`, `?offset=` query params, call `get_cycles()`, return JSON.
- [x] 3.6 Implement `GET /api/cycles/:id` — extract ID from path, call `get_cycle()`, return JSON or 404.
- [x] 3.7 Implement `GET /api/cycles/:id/trace` — call `get_cycle_trace()`, return JSON or 404.
- [x] 3.8 Implement `GET /api/cycles/:id/corrections` — call `get_cycle_corrections()`, return JSON.
- [x] 3.9 Implement `GET /api/corrections` — parse pagination params, call `get_corrections()`, return JSON.
- [x] 3.10 Implement `GET /api/sessions` and `GET /api/sessions/:id`.
- [x] 3.11 Implement `GET /api/stats/correction-rate`, `GET /api/stats/confidence-calibration`, `GET /api/stats/per-task-accuracy`.
- [x] 3.12 Add CORS headers (`Access-Control-Allow-Origin: http://localhost:5173`) to all responses. Handle `OPTIONS` preflight requests.
- [x] 3.13 Bind to `127.0.0.1` only. Refuse to start if binding fails (same pattern as Pulse's `start_dashboard_server`).
- [x] 3.14 Suppress access log noise (override `log_message` to no-op, same as Pulse).
- [x] 3.15 Add a `_send_json(handler, data, status=200)` helper for consistent JSON response formatting.
- [x] 3.16 Add a `_send_error(handler, status, message)` helper for consistent error formatting.

## 4. Entrypoint

- [x] 4.1 Create `scope_api.py` at the repo root as the top-level entrypoint. It should: load config via `focusmonitor.config.load_config()`, read `scope_api_port`, print the URL, and start the server.
- [x] 4.2 Add a `--port` CLI argument that overrides the config value.

## 5. HTTP endpoint tests

- [x] 5.1 Add HTTP-level tests in `tests/test_scope_api.py` that start the handler against an in-memory DB, issue requests, and verify response status and JSON structure for: `/api/health`, `/api/cycles`, `/api/cycles/:id`, `/api/cycles/:id/trace`, `/api/corrections`, `/api/stats/correction-rate`.
- [x] 5.2 Test that a request for a non-existent cycle returns 404 with a JSON error.
- [x] 5.3 Test that CORS headers are present on responses.

## 6. Verification

- [x] 6.1 Run `.venv/bin/pytest tests/` — all tests pass.
- [x] 6.2 Run the `privacy-review` skill against the diff. Confirm no new outbound URL, no new non-localhost binding.
- [ ] 6.3 Manual: start the API with `python scope_api.py`, curl `http://127.0.0.1:9877/api/health`, verify JSON response.
