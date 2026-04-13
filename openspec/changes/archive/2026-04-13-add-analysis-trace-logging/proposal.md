## Why

The analysis pipeline produces rich structured output (evidence, confidence, task classification) but discards the most valuable debugging and learning artifacts after each cycle: the full prompt text, the raw model response before parsing, the per-call timing, and which few-shot corrections were injected. Without these, a developer cannot answer:

- "What exactly did the model see when it made this classification?"
- "How long did each Ollama call take?"
- "Which corrections were in the few-shot window for this specific cycle?"
- "Did the retry loop fire, and if so, how many times?"

This data is the foundation for a planned companion tool ("Scope") that will provide full X-ray visibility into the AI's decision-making and track how the system improves over time through corrections. But independent of Scope, trace logging has standalone value: it turns every analysis cycle into a reproducible case study for prompt engineering.

## What Changes

- **New `analysis_traces` table in the existing SQLite DB.** One row per analysis cycle, linked to `activity_log` via a foreign key. Stores: Pass 1 prompts and raw responses (per-screenshot, JSON arrays), Pass 2 prompt and raw response, per-call elapsed milliseconds, which correction IDs were injected as few-shot examples, which screenshot paths were used, and how many parse retries occurred.
- **`query_ollama` gains timing measurement.** A new `return_timing` keyword-only argument (default `False`) causes the function to return a `(response_text, elapsed_ms)` tuple instead of just `response_text`. Existing callers are unchanged.
- **`run_analysis` captures and writes trace data.** When `trace_logging` is enabled (default `True`), `run_analysis` collects prompt text, raw responses, and timing from each Ollama call, then writes a single `analysis_traces` row after the main `activity_log` insert.
- **Cleanup covers the new table.** `cleanup_old_db_rows` deletes `analysis_traces` rows older than `db_retention_days`, same as `activity_log`.
- **Config key `trace_logging`.** Boolean, default `True`. Set to `False` to disable trace logging (the table still exists but stops growing).

Pulse never reads from `analysis_traces` — the table is write-only from Pulse's perspective. The planned Scope companion will read it, but that's a separate change with no coupling back into Pulse.

Explicitly out of scope:
- The Scope companion tool (separate change)
- Any new API endpoints for reading traces (that's Scope's job)
- Logging Pass 1 prompts individually when using the legacy `describe_screenshots` path (only the structured extraction path is instrumented)
- Storing screenshot image data in the trace (only paths are stored; the images live on disk under the existing retention policy)

## Capabilities

### New Capabilities
- `analysis-traces`: Persistent storage of full prompt text, raw model responses, timing, and context metadata for every analysis cycle.

### Modified Capabilities
- `contextual-analysis`: `query_ollama` gains `return_timing` parameter for elapsed-time measurement. No change to prompts or parsing.
- `data-retention`: Cleanup covers the new `analysis_traces` table alongside `activity_log`.

## Impact

**Affected code (focusmonitor/):**
- `db.py` — new `CREATE TABLE IF NOT EXISTS analysis_traces (...)` in `init_db()`
- `config.py` — add `"trace_logging": True` to `DEFAULT_CONFIG`
- `ollama.py` — `query_ollama` gains `return_timing` kwarg; wraps `urlopen` with timing
- `analysis.py` — `extract_screenshot_artifacts` and `run_analysis` capture prompt/response/timing data; `run_analysis` writes `analysis_traces` row
- `cleanup.py` — `cleanup_old_db_rows` adds `DELETE FROM analysis_traces WHERE created_at < ?`

**Affected data (~/.focus-monitor/):**
- New `analysis_traces` table in `activity.db`. Additive — no existing tables modified.
- Estimated growth: ~3-5 KB per analysis cycle (mostly the prompt text). At one cycle per hour, ~120 KB/day.

**Tests:**
- New test in `test_db_schema.py`: `init_db` creates `analysis_traces` with expected columns
- Existing `test_init_db_is_idempotent` still passes
- New test in `test_ollama.py`: `return_timing=True` returns `(str, float)` tuple; `return_timing=False` returns `str`
- New test in `test_analysis.py`: `run_analysis` with `trace_logging=True` writes trace row; with `False` writes none
- Existing tests: `cleanup_old_db_rows` extended test to verify `analysis_traces` cleanup

**Dependencies:** None added.

**Network:** No new outbound target. All changes are to localhost-only code paths (Ollama on `127.0.0.1:11434`, SQLite on disk). Privacy posture strictly preserved.
