## 1. Extend `query_ollama` signature

- [x] 1.1 Add keyword-only parameters `temperature` (float or None, default None) and `format_` (str or None, default None) to `query_ollama` in `focusmonitor/ollama.py`.
- [x] 1.2 When `temperature` is not None, add `"options": {"temperature": temperature}` to the request payload. Merge with any existing `options` dict if one is ever added.
- [x] 1.3 When `format_` is not None, add `"format": format_` to the request payload.
- [x] 1.4 Add a unit test asserting that `query_ollama` includes `options.temperature` and `format` in the serialized payload when both are provided.
- [x] 1.5 Add a unit test asserting that `query_ollama` omits `options` and `format` keys from the payload when both are None (existing behavior preserved).

## 2. Wire Pass 1 extraction calls

- [x] 2.1 Update `extract_screenshot_artifacts` in `focusmonitor/analysis.py` to pass `temperature=0.0, format_="json"` to `query_ollama`.
- [x] 2.2 Add a unit test that mocks `query_ollama` and asserts `extract_screenshot_artifacts` passes `temperature=0.0` and `format_="json"` in the call kwargs.

## 3. Wire Pass 2 classification calls

- [x] 3.1 Update the Pass 2 `query_ollama` call in `run_analysis` (structured two-pass path, line 575) to pass `temperature=0.0, format_="json"`.
- [x] 3.2 Update the Pass 2 `query_ollama` call in `run_analysis` (two-pass with legacy descriptions path) to pass `temperature=0.0, format_="json"`.
- [x] 3.3 Verify the legacy single-pass fallback path (lines 577–584, `two_pass_analysis: false`) does NOT pass temperature or format — leave it unchanged.
- [x] 3.4 Add a unit test that mocks `query_ollama` and runs `run_analysis` with `two_pass_analysis: true`, asserting both Pass 1 and Pass 2 calls include the new kwargs.
- [x] 3.5 Add a unit test that runs `run_analysis` with `two_pass_analysis: false` and asserts the single-pass call does NOT include temperature or format kwargs.

## 4. Verify existing tests and defense-in-depth

- [x] 4.1 Run the full pytest suite (`.venv/bin/pytest tests/`) and confirm all existing tests pass unchanged. Cassette-backed tests replay fixed responses and should be unaffected by request payload changes.
- [x] 4.2 Confirm the multi-strategy parser (`_parse_json_strategies`), `\_` unescape path, and retry loop are untouched and still covered by their existing tests.
- [x] 4.3 Run the `privacy-review` skill against the diff. Confirm no new outbound URL, no new dependency, no new network target.
