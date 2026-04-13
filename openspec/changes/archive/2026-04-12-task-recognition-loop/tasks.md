## 1. Schema and config foundation

- [x] 1.1 Add new config keys to `focusmonitor/config.py` defaults: `pass1_structured` (bool, default true), `corrections_few_shot_n` (int, default 5), `session_dip_tolerance_sec` (int, default 300), `session_aggregation_enabled` (bool, default true). Ensure each key falls back to its default when missing from `~/.focus-monitor/config.json`.
- [x] 1.2 Extend `focusmonitor/db.py` schema-init path with `CREATE TABLE IF NOT EXISTS sessions (...)` matching the columns specified in `specs/session-aggregation/spec.md` (`id`, `start`, `end`, `task`, `task_name_confidence`, `boundary_confidence`, `cycle_count`, `dip_count`, `evidence_json`, `kind`).
- [x] 1.3 Extend `focusmonitor/db.py` schema-init path with `CREATE TABLE IF NOT EXISTS corrections (...)` matching the columns specified in `specs/correction-loop/spec.md`.
- [x] 1.4 Add a unit test that opens an empty SQLite file, runs the schema-init path, and asserts both new tables exist and that the existing `activity_log` table is unchanged.
- [x] 1.5 Confirm `focus_score` column on `activity_log` is untouched and existing rows from before this change still parse via the existing read paths.

## 2. Pass 1: structured screenshot extraction

- [x] 2.1 Add `extract_screenshot_artifacts(cfg, screenshots)` to `focusmonitor/analysis.py` that prompts Ollama for the typed artifact schema defined in `specs/contextual-analysis/spec.md` and returns a list of dicts (one per screenshot).
- [x] 2.2 Reuse the existing multi-strategy JSON parser (`parse_analysis_json`) to parse each per-screenshot response.
- [x] 2.3 Implement the fallback path: when the parser returns `None` after retries, build a fallback artifact whose `one_line_action` contains a truncated raw response and whose other fields are `null`.
- [x] 2.4 Wire `run_analysis` so that when `pass1_structured` is true, it calls `extract_screenshot_artifacts` instead of `describe_screenshots`. When false, retain the legacy descriptive path.
- [x] 2.5 Update `build_classification_prompt` to render structured artifacts as a labeled section (omitting null fields per artifact). Ensure the rendered section does not contain free-form descriptive prose when artifacts are present.
- [x] 2.6 Add a unit test for `extract_screenshot_artifacts` that uses an existing PNG fixture and a mocked Ollama response, asserting the returned dict has the expected fields.
- [x] 2.7 Add a unit test for the fallback path that simulates an unparseable Ollama response and asserts the artifact has only `one_line_action` populated.
- [x] 2.8 Add a unit test for `build_classification_prompt` that asserts the structured-artifact rendering omits null fields and contains no free-form descriptive sentences when artifacts are passed in.
- [ ] 2.9 Re-record (or add) the cassette `tests/cassettes/ollama/pass1_structured_v1.yaml` against the existing PNG fixtures, following the `test-focusmonitor` re-record sub-workflow. Privacy-review the recorded text for any non-fixture leakage before committing.

## 3. Pass 2: evidence and dual confidence in classification

- [x] 3.1 Update the classification prompt template in `build_classification_prompt` to (a) instruct the model to populate `evidence[]`, `boundary_confidence`, `name_confidence`, `needs_user_input`, and a `task` field; (b) include explicit anchor examples for each confidence level on each axis; (c) explicitly state that `task=null` / `name_confidence="low"` / empty evidence are valid, expected outcomes when signals are mixed.
- [x] 3.2 Update `validate_analysis_result` to validate the new fields per `specs/structured-analysis/spec.md`, applying safe defaults when missing or malformed (`task=null`, `evidence=[]`, both confidences `"low"`, `needs_user_input=true`). Ensure all legacy field defaults are still applied.
- [x] 3.3 Update `validate_analysis_result` to filter malformed `evidence` entries (those that aren't `{signal, weight}` with string values) while retaining well-formed ones.
- [x] 3.4 Update `run_analysis` to insert the new fields into the row written to `activity_log` (use a dedicated column or a JSON-encoded blob — design.md leaves the choice flexible; choose the cheaper of the two without breaking existing reads).
- [x] 3.5 Add unit tests covering `validate_analysis_result` for: full valid response (legacy + new), missing new fields, missing legacy fields, invalid confidence values, malformed evidence list.
- [x] 3.6 Add a unit test that asserts the system does NOT trigger a parse-retry when `task=null` and `name_confidence="low"` are present in a valid response.
- [ ] 3.7 Re-record (or add) the cassette `tests/cassettes/ollama/pass2_with_evidence_v1.yaml` against the existing fixtures. Privacy-review the recorded text for any leakage before committing.

## 4. Session aggregation module

- [x] 4.1 Create `focusmonitor/sessions.py` with a `_GLUE_SIGNALS` module-level constant listing the glue rules from `specs/session-aggregation/spec.md`.
- [x] 4.2 Implement `aggregate(rows: list[dict]) -> list[Session]` as a pure function that takes ordered cycles (each with their structured signals + new Pass 2 fields) and returns a list of session-shaped dicts (`session | unclear | away`).
- [x] 4.3 Implement workspace / cwd / browser-host / task-name glue rules per spec.
- [x] 4.4 Implement dip tolerance: a non-matching cycle ≤ `session_dip_tolerance_sec` whose neighbors belong to the same session is absorbed; `dip_count` is incremented.
- [x] 4.5 Implement evidence aggregation: union of strong + medium signals across constituent cycles, deduplicated by signal string.
- [x] 4.6 Implement standalone `unclear` emission: a low-`name_confidence` cycle with no glue match becomes its own entry.
- [x] 4.7 Implement `aw_afk_overlay(rows, afk_events)` that converts cycles overlapping ≥50% with afk into `away` entries and merges consecutive `away` entries.
- [x] 4.8 Add a defensive path: when AW is unreachable, skip the afk overlay and continue with cycle-only aggregation; do not raise.
- [x] 4.9 Implement `persist_sessions(db, sessions)` that writes the aggregated sessions into the `sessions` table idempotently — re-aggregating the same range MUST produce the same rows.
- [x] 4.10 Wire the aggregator into the analysis cycle: after `run_analysis` writes a new `activity_log` row, re-aggregate the affected day and persist the result.
- [x] 4.11 Add unit tests for the pure aggregator using synthetic cycle inputs covering: single coherent activity → one session; genuine task switch → two sessions; dip absorbed; dip beyond tolerance splits; standalone unclear; idempotent re-aggregation.
- [x] 4.12 Add a unit test that constructs synthetic afk events and asserts cycles overlapping ≥50% become `away`, while a 30-second afk inside an active cycle does not.

## 5. Corrections store and write/read API

- [x] 5.1 Create `focusmonitor/corrections.py` with `record_correction(entry_kind, entry_id, model_state, user_state)` that inserts one row into the `corrections` table inside a single SQLite transaction and returns the inserted row id.
- [x] 5.2 Validate required fields inside `record_correction`; raise a clearly-named exception when any required column is missing.
- [x] 5.3 Validate that the referenced entry exists in `sessions` (or `activity_log` for `entry_kind='cycle'`); raise when not found.
- [x] 5.4 Implement `corrections_for(entry_kind, entry_id) -> list[dict]` returning rows ordered most-recent-first.
- [x] 5.5 Implement `recent_corrections(n) -> list[dict]` running the `SELECT ... ORDER BY created_at DESC LIMIT ?` query for the few-shot retrieval.
- [x] 5.6 Add the corrections SQLite path lookup via `focusmonitor.config` (no hardcoded paths).
- [x] 5.7 Add unit tests for `record_correction` happy path, missing-field rejection, and non-existent entry rejection.
- [x] 5.8 Add unit tests for `corrections_for` and `recent_corrections` covering empty store, partial fill, and N-limit behavior.

## 6. Few-shot retrieval into Pass 2 prompt

- [x] 6.1 Update `build_classification_prompt` to call `recent_corrections(cfg['corrections_few_shot_n'])` and render the returned rows as a "Recent corrections from the user" section in the prompt.
- [x] 6.2 Render each correction row with the model's prior verdict (task + name_confidence), the user's verdict (`corrected | confirmed`), the user's task or kind, and the structured signals visible at the time.
- [x] 6.3 Render confirmations alongside corrections with their verdict clearly labeled.
- [x] 6.4 Omit the section entirely when the corrections store is empty.
- [x] 6.5 Omit the section entirely when `corrections_few_shot_n == 0`.
- [x] 6.6 Add a unit test that asserts the section is rendered with correct formatting when N records exist, and omitted when none exist.
- [x] 6.7 Add a unit test that asserts setting `corrections_few_shot_n=0` skips the SQL query entirely (use a spy / mock to confirm no `SELECT` is issued).

## 7. Dashboard: session timeline view

- [x] 7.1 Add a `render_session_timeline(sessions)` helper to `focusmonitor/dashboard.py` that emits the HTML for the new primary view per `specs/dashboard-server/spec.md`.
- [x] 7.2 Render each session row with: time range, kind label (or task name), boundary+name confidence indicators, cycle/dip counts when > 0, and an expandable evidence drawer.
- [x] 7.3 Render `away` entries with distinct styling and no ✓ control.
- [x] 7.4 Render `unclear` entries with the ✏️ control but no ✓ control.
- [x] 7.5 HTML-escape every untrusted field (task names, signal strings, user notes) using `html.escape`.
- [x] 7.6 Wire `build_dashboard` to query the `sessions` table for the active time range and pass results into `render_session_timeline`.
- [x] 7.7 Demote (or hide) the legacy focus-score hero card in favor of the session timeline. Keep `focus_score` populated in storage; the spec leaves the visual presentation flexible.
- [x] 7.8 Add a query parameter (e.g. `?view=legacy`) that re-enables the per-cycle activity-log view for diagnostics.
- [x] 7.9 Update the syrupy snapshot in `tests/__snapshots__/test_dashboard.ambr` for the new layout. Include the snapshot diff in the same PR as the template change.
- [x] 7.10 Add a unit test for `render_session_timeline` with synthetic session data covering: a normal session, an `unclear` entry, an `away` entry, a session with dips > 0.
- [x] 7.11 Add a unit test asserting that `render_session_timeline` HTML-escapes a session whose task name contains `<script>alert(1)</script>`.

## 8. Dashboard: correction and confirmation endpoints

- [x] 8.1 Add a `POST /api/sessions/<session_id>/correct` handler that calls `_mutate(handler, required_fields=['user_kind'])` and then `record_correction(...)`. Return the re-rendered session row HTML on success.
- [x] 8.2 Validate `user_kind` is one of `{on_planned_task, thinking_offline, meeting, break, other}`; respond HTTP 400 otherwise.
- [x] 8.3 Look up the session row by id; respond HTTP 404 when not found.
- [x] 8.4 Add a `POST /api/sessions/<session_id>/confirm` handler that calls `_mutate(handler, required_fields=[])` and then `record_correction(...)` with `user_verdict='confirmed'`.
- [x] 8.5 Both handlers MUST flow through the existing `_mutate` helper for CSRF, Host, and Origin checks; no new code path SHALL bypass them.
- [x] 8.6 Add the inline correction form markup to `render_session_timeline`: a `user_kind` selector with the five labeled options, a `user_task` text input, an optional `user_note` input, and a hidden `csrf` field. Form submits via `hx-post` with `hx-target` on the session row and `hx-swap="outerHTML"`.
- [x] 8.7 Add the inline ✓ confirm control as an `hx-post` button (no extra form), targeting the confirm endpoint.
- [x] 8.8 Verify no new `<script>` tag is added beyond the vendored htmx file; no modal dialog or full-screen overlay is introduced.
- [x] 8.9 Add unit tests for the correct endpoint covering: happy path (row inserted, session row re-rendered), invalid `user_kind` → 400, non-existent session → 404, missing CSRF → 403, wrong Host → 403.
- [x] 8.10 Add a unit test for the confirm endpoint covering happy path and missing CSRF.
- [x] 8.11 Add a unit test that asserts the rendered correction form contains exactly the five `user_kind` options with their human-readable labels.

## 9. Privacy review and integration tests

- [x] 9.1 Run the project-local `privacy-review` skill against the full diff. Confirm no new outbound URL, no new HTTP target, no new third-party package, no new CDN reference, no weakened binding, no hardcoded `~/.focus-monitor/` path. Address any flag before commit.
- [x] 9.2 Confirm `pytest-socket` allow-list in `pyproject.toml` is unchanged (still `127.0.0.1, localhost, ::1`).
- [x] 9.3 Confirm `.mcp.json` is still empty (`{"mcpServers": {}}`).
- [x] 9.4 Confirm `requirements.txt`, `setup.py`, and `pyproject.toml` have no new runtime dependencies. Dev-only test deps remain dev-only.
- [x] 9.5 Run `.venv/bin/pytest tests/` end-to-end with no network access. All tests must pass offline (cassette-backed).
- [ ] 9.6 Manually verify against a populated database that the dashboard loads with the new session timeline, that ✏️ reveals the inline form, that submitting a correction inserts a row, that ✓ inserts a confirmation row, and that subsequent analysis cycles include the most-recent corrections in the prompt (eyeball the prompt log).
- [x] 9.7 Verify the legacy `?view=legacy` query parameter still produces the per-cycle view for diagnostics.

## 10. Documentation and rollout

- [ ] 10.1 Update any user-facing docs (README, dashboard help text) to describe the new timeline + correction workflow. Avoid claims about model accuracy improvements; describe the workflow and the privacy posture.
- [ ] 10.2 Add a short note to `~/.focus-monitor/config.json` defaults section in code or docs explaining the four new config keys and their defaults.
- [x] 10.3 Confirm CLAUDE.md does not need updates for this change (no new invariants introduced; existing invariants preserved).
- [ ] 10.4 Open the change for archive once all tasks are complete and the syrupy snapshot diff has been reviewed.
