## Context

focus-monitor's analysis pipeline (`run_analysis` in `analysis.py`) builds prompts, sends them to Ollama, parses responses, and writes a result row to `activity_log`. The prompt text and raw responses are ephemeral — used once, never stored. Timing is not measured. There's no record of which few-shot corrections were in the prompt window for any given cycle.

This change adds a write-only trace table that captures these ephemeral artifacts. The table is designed for a planned companion tool ("Scope") to read, but Pulse itself never reads from it. The coupling is strictly one-directional: Pulse writes, Scope reads, no imports cross the boundary.

The existing patterns this change follows:
- `db.py`: `CREATE TABLE IF NOT EXISTS` in `init_db()`, same as `sessions`, `corrections`, `pending_data`
- `config.py`: new key in `DEFAULT_CONFIG`, same as `trace_logging`, `session_aggregation_enabled`, etc.
- `cleanup.py`: `DELETE FROM ... WHERE timestamp < ?` in `cleanup_old_db_rows`, same as `activity_log`, `nudges`
- `ollama.py`: keyword-only args on `query_ollama`, same as `temperature`, `format_`
- `test_db_schema.py`: `_table_exists` + `_column_names` pattern for schema assertions

## Goals / Non-Goals

**Goals:**
- Capture the full prompt text, raw response, and wall-clock timing for every Pass 1 and Pass 2 Ollama call in a durable, queryable format
- Record which few-shot correction IDs were injected into each cycle's classification prompt
- Record which screenshot paths were used (so the companion can display them if they haven't been cleaned up yet)
- Record parse retry count for observability
- Preserve all existing privacy invariants and introduce zero new runtime dependencies
- Make trace logging toggleable via config without removing the table

**Non-Goals:**
- Reading traces from Pulse (dashboard, nudges, sessions — none of these consume trace data)
- Building a trace viewer (that's the Scope companion, a separate change)
- Instrumenting the legacy `describe_screenshots` path (only the structured `extract_screenshot_artifacts` path is traced)
- Storing screenshot image bytes in the trace (only paths)
- Adding a separate Pass 1 prompt column per screenshot (they all use the same `_EXTRACTION_PROMPT`; the prompt is stored once, responses are an array)

## Decisions

### D1. Separate `analysis_traces` table, not a new column on `activity_log`

**Decision:** Create a new table with a foreign key to `activity_log.id` rather than adding columns to `activity_log`.

**Why:**
- `activity_log` is the hot read path (dashboard queries it on every page load). Adding ~3 KB of prompt text per row would bloat every `SELECT` that doesn't need it.
- Separation makes the write-only contract explicit: Pulse writes `analysis_traces`, never reads it. If we added columns to `activity_log`, future Pulse code might accidentally depend on them.
- Cleanup can use different retention policies if needed (though v1 uses the same `db_retention_days`).
- The companion tool can query `analysis_traces` with a simple `JOIN` to `activity_log` on `activity_log_id`.

### D2. `query_ollama` returns timing via `return_timing` kwarg

**Decision:** Add `return_timing=False` as a keyword-only argument. When `True`, return `(response_text, elapsed_ms)` tuple. When `False` (default), return `response_text` as before.

**Why not always return a tuple or dataclass:**
- `query_ollama` has 15+ call sites across production code and tests. Changing the return type everywhere is high-churn, high-risk for a feature that only the trace logger needs.
- The `return_timing=False` default means zero changes to any existing caller — the function signature is backwards-compatible.
- If we later want a richer return type (token count, model version, etc.), we can evolve the kwarg into a `return_meta=True` that returns a dict. For now, a 2-tuple is the simplest thing that works.

**Timing measurement:** Wrap the `urlopen` call with `time.monotonic()` (not `time.time()` — monotonic is immune to clock adjustments). The elapsed time includes network round-trip + model inference + response transfer. This is the right granularity for "how long did this Ollama call take."

### D3. Pass 1 stores one prompt + N responses (not N prompts + N responses)

**Decision:** `pass1_prompts_json` stores the single extraction prompt template (since it's the same for every screenshot). `pass1_responses_json` stores a JSON array of raw response strings, one per screenshot. `pass1_elapsed_ms_json` stores a JSON array of per-call timings.

**Why:** The extraction prompt (`_EXTRACTION_PROMPT`) is a module-level constant — identical for every screenshot in every cycle. Storing it N times wastes space. Storing it once alongside the N responses and N timings is sufficient to reconstruct every call.

### D4. Few-shot correction IDs are stored, not the full correction text

**Decision:** `few_shot_ids_json` stores a JSON array of `corrections.id` values, not the rendered prompt text. The companion can join to the `corrections` table to reconstruct the full few-shot block.

**Why:** The rendered text is already deterministically derivable from the correction rows via `render_few_shot_corrections`. Storing IDs avoids duplication and keeps the trace row smaller. The companion tool will have access to the `corrections` table anyway.

### D5. Trace logging is on by default, toggleable via config

**Decision:** `trace_logging` defaults to `True`. When `False`, `run_analysis` skips the trace write entirely (no INSERT, no timing measurement).

**Why on by default:** The whole point is to capture data for learning. An opt-in flag that users don't know about defeats the purpose. The storage cost is small (~120 KB/day at one cycle per hour) and is bounded by the same `db_retention_days` cleanup that governs `activity_log`.

**Why toggleable:** If someone runs focus-monitor on a constrained device or has unusually high cycle frequency, they should be able to turn it off. Config > hardcoded.

### D6. Trace write failure must not break the analysis cycle

**Decision:** The `analysis_traces` INSERT is wrapped in a `try/except` that prints a warning and continues. A failed trace write must never prevent `run_analysis` from completing its core work (writing `activity_log`, running session aggregation, firing nudges).

**Why:** Trace logging is observability infrastructure, not core functionality. The same pattern is used for `aggregate_day` at `analysis.py:660-663`.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| **Trace rows grow the DB.** ~3-5 KB per cycle, ~120 KB/day. | Bounded by `db_retention_days` cleanup (default 30 days = ~3.6 MB). Negligible next to screenshot storage. |
| **`return_timing` tuple changes `query_ollama` contract for opt-in callers.** | Default `False` preserves existing contract. Only trace-logging call sites opt in. Type is a simple 2-tuple, not a complex object. |
| **Screenshots may be cleaned up before the companion reads the trace.** | Trace stores paths, not bytes. The companion shows a "screenshot unavailable" placeholder. This is acceptable — the structured artifacts and prompt text carry the signal. |
| **Privacy.** | No new outbound target, no new dependency. Trace data contains the same information already stored in `activity_log.raw_response` (window titles, file paths, URLs) plus the prompt framing around it. No new privacy surface. |

## Migration Plan

1. Add `analysis_traces` table and `trace_logging` config key. Run tests.
2. Add `return_timing` to `query_ollama`. Run tests.
3. Instrument `extract_screenshot_artifacts` to capture per-screenshot timing and responses.
4. Instrument `run_analysis` to capture Pass 2 prompt/response/timing and write the trace row.
5. Extend cleanup. Run full test suite.
6. Dogfood: run Pulse with trace logging for a few cycles, inspect the `analysis_traces` table via `sqlite3` CLI to verify data looks correct.
