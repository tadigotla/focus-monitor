## 1. Add keep-alive support to Ollama client

- [x] 1.1 Add `ollama_keep_alive` key with default `"30s"` to `DEFAULT_CONFIG` in `focusmonitor/config.py`
- [x] 1.2 Pass `cfg["ollama_keep_alive"]` as the `keep_alive` field in the Ollama API payload in `focusmonitor/ollama.py`
- [x] 1.3 Add test for `query_ollama` verifying the `keep_alive` field is present in the request payload

## 2. Retune default intervals

- [x] 2.1 Change `screenshot_interval_sec` default from `120` to `300` in `focusmonitor/config.py`
- [x] 2.2 Change `analysis_interval_sec` default from `1800` to `3600` in `focusmonitor/config.py`
- [x] 2.3 Change `screenshots_per_analysis` default from `6` to `12` in `focusmonitor/config.py`

## 3. Fix affected tests

- [x] 3.1 Update any tests that assert on the old default values for `screenshot_interval_sec`, `analysis_interval_sec`, or `screenshots_per_analysis`
- [x] 3.2 Update dashboard snapshots if the dashboard renders interval/config values
- [x] 3.3 Run full test suite and fix any regressions
