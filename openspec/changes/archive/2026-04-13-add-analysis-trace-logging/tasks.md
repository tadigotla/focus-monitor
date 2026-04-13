## 1. Schema and config

- [x] 1.1 Add `CREATE TABLE IF NOT EXISTS analysis_traces (...)` to `focusmonitor/db.py` in `init_db()` with columns: `id`, `activity_log_id`, `created_at`, `pass1_prompts_json`, `pass1_responses_json`, `pass1_elapsed_ms_json`, `pass2_prompt`, `pass2_response_raw`, `pass2_elapsed_ms`, `few_shot_ids_json`, `screenshot_paths_json`, `parse_retries`. Include a foreign key to `activity_log(id)`.
- [x] 1.2 Add an index on `analysis_traces(activity_log_id)` for efficient joins.
- [x] 1.3 Add an index on `analysis_traces(created_at)` for efficient cleanup queries.
- [x] 1.4 Add `"trace_logging": True` to `DEFAULT_CONFIG` in `focusmonitor/config.py`.
- [x] 1.5 Add a test in `tests/test_db_schema.py`: `test_init_db_creates_analysis_traces_table` — assert table exists with expected column set.
- [x] 1.6 Verify existing `test_init_db_is_idempotent` still passes (the new table must not break re-init).

## 2. Timing in `query_ollama`

- [x] 2.1 Add `return_timing=False` as a keyword-only argument to `query_ollama` in `focusmonitor/ollama.py`.
- [x] 2.2 Wrap the `urlopen` call with `time.monotonic()` to measure elapsed milliseconds. Store the elapsed value.
- [x] 2.3 When `return_timing=True`, return `(response_text, elapsed_ms)` on success and `(None, elapsed_ms)` on failure.
- [x] 2.4 When `return_timing=False` (default), return `response_text` or `None` as before — existing behavior unchanged.
- [x] 2.5 Add a test in `tests/test_ollama.py`: `test_return_timing_true_returns_tuple` — mock `urlopen`, assert return is a `(str, float)` tuple with elapsed_ms > 0.
- [x] 2.6 Add a test in `tests/test_ollama.py`: `test_return_timing_false_returns_string` — mock `urlopen`, assert return is a plain string (not a tuple).
- [x] 2.7 Add a test in `tests/test_ollama.py`: `test_return_timing_on_failure_returns_none_with_elapsed` — point at unreachable port with `return_timing=True`, assert return is `(None, float)`.

## 3. Instrument Pass 1

- [x] 3.1 Update `extract_screenshot_artifacts` in `focusmonitor/analysis.py` to accept an optional `_trace` dict parameter. When provided, populate `_trace["pass1_responses"]` (list of raw response strings) and `_trace["pass1_elapsed_ms"]` (list of floats) during the per-screenshot loop.
- [x] 3.2 Use `return_timing=True` on the `query_ollama` call inside the loop to capture per-screenshot elapsed time.
- [x] 3.3 Store the extraction prompt template string in `_trace["pass1_prompt"]` (the `_EXTRACTION_PROMPT` constant, stored once since it's the same for all screenshots).
- [x] 3.4 Add a test in `tests/test_analysis.py`: mock `query_ollama`, call `extract_screenshot_artifacts` with a `_trace` dict, assert the dict is populated with the expected keys and list lengths matching the number of screenshots.

## 4. Instrument Pass 2 and write trace row

- [x] 4.1 In `run_analysis`, when `trace_logging` is enabled and `two_pass_analysis` is true: capture the Pass 2 prompt text (the `prompt` variable), call `query_ollama` with `return_timing=True`, and store the raw response text and elapsed_ms.
- [x] 4.2 Capture the `few_shot_ids` — extract the `id` field from each record in `few_shot_corrections` and store as a list.
- [x] 4.3 Capture the screenshot paths used (the `screenshots` list after deduplication, converted to strings).
- [x] 4.4 Track `parse_retries` — count how many times the retry loop fires (0 if first parse succeeds).
- [x] 4.5 After the `activity_log` INSERT (which sets `cursor.lastrowid`), write the `analysis_traces` INSERT using the captured `activity_log_id`. Wrap in `try/except` with a warning print — trace failure must never break the analysis cycle.
- [x] 4.6 When `trace_logging` is `False`, skip all trace capture and the INSERT entirely.
- [x] 4.7 Add a test in `tests/test_analysis.py`: mock `query_ollama`, call `run_analysis` with `trace_logging=True`, assert a row exists in `analysis_traces` with the correct `activity_log_id`, non-empty `pass2_prompt`, and valid JSON in the array columns.
- [x] 4.8 Add a test in `tests/test_analysis.py`: call `run_analysis` with `trace_logging=False`, assert no row exists in `analysis_traces`.

## 5. Cleanup and retention

- [x] 5.1 Extend `cleanup_old_db_rows` in `focusmonitor/cleanup.py` to also delete `analysis_traces` rows where `created_at < cutoff`.
- [x] 5.2 Add a test: insert old and recent `analysis_traces` rows, run cleanup, assert only old rows are deleted.

## 6. Verification

- [x] 6.1 Run the full pytest suite (`.venv/bin/pytest tests/`). All tests must pass.
- [x] 6.2 Run the `privacy-review` skill against the diff. Confirm no new outbound URL, no new dependency, no new network target.
- [x] 6.3 Verify `activity_log` schema is unchanged (existing `test_init_db_preserves_activity_log_schema` must still pass with exact column list).
