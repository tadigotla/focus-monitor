## 1. Config & Defaults

- [x] 1.1 Update `DEFAULT_CONFIG` in monitor.py: change `ollama_model` from `"llava"` to `"llama3.2-vision"`, add `max_parse_retries` (1), `dedup_size_threshold_pct` (2), `two_pass_analysis` (true), `history_window` (3)
- [x] 1.2 Update setup.py default config generation to match new defaults

## 2. Structured JSON Parsing

- [x] 2.1 Extract JSON parsing into a `parse_analysis_json(raw: str) -> dict` function implementing the three-strategy pipeline: direct parse, strip fences, regex extract first `{...}` block
- [x] 2.2 Add `validate_analysis_result(result: dict) -> dict` function that ensures all required keys exist with correct types, fills defaults for missing fields, and clamps `focus_score` to 0-100
- [x] 2.3 Add retry logic to `run_analysis`: on parse failure, send a short correction prompt ("Your response was not valid JSON. Return only the JSON object:") and re-attempt parsing, up to `max_parse_retries` times

## 3. Screenshot Deduplication

- [x] 3.1 Add `deduplicate_screenshots(paths: list, threshold_pct: float) -> list` function that compares consecutive screenshot file sizes and removes duplicates within the threshold, always keeping at least 1 screenshot
- [x] 3.2 Integrate dedup into `run_analysis` — call `deduplicate_screenshots` on the result of `recent_screenshots` before sending to the model, log how many were deduped

## 4. Two-Pass Analysis Pipeline

- [x] 4.1 Add `describe_screenshots(cfg, screenshots: list) -> list[str]` function that queries the model once per unique screenshot with a short prompt ("Describe what application and activity is visible. Be brief: app name, content type, what the user is doing.") and returns a list of descriptions
- [x] 4.2 Add `get_recent_history(db, window: int) -> str` function that queries the last N `activity_log` entries and formats their summaries and focus scores as a text block
- [x] 4.3 Refactor `run_analysis` to support two-pass mode: when `two_pass_analysis` is true, call `describe_screenshots` then build a classification prompt from descriptions + ActivityWatch + tasks + history; when false, use a single improved prompt with screenshots attached
- [x] 4.4 Write the improved classification prompt with explicit focus score criteria (80-100: on-plan, 50-79: productive off-plan, 20-49: mixed, 0-19: distracted/idle) and trend awareness instructions

## 5. Integration & Cleanup

- [x] 5.1 Update the main `run_analysis` function to wire everything together: dedup → describe (if two-pass) → classify with history → parse with retry → validate → store
- [x] 5.2 Update startup banner in `main()` to print new config values (two-pass mode, history window, dedup threshold)
- [x] 5.3 Test the full pipeline end-to-end: verify JSON parsing with malformed inputs, dedup with same-size files, two-pass prompt construction, and history context formatting
