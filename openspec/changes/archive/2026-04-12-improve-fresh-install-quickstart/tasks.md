## 1. Probe module

- [x] 1.1 Create `focusmonitor/install.py` with stdlib-only imports (`urllib.request`, `urllib.error`, `json`, `subprocess`, `shutil`, `pathlib`)
- [x] 1.2 Implement `probe_ollama(url="http://127.0.0.1:11434", expected_model="llama3.2-vision", timeout=2.0)` returning a small named result: `state` (one of `"missing"`, `"daemon_down"`, `"wrong_state"`, `"ok"`, `"unknown"`), `message`, `next_command`
- [x] 1.3 Implement `probe_activitywatch(url="http://127.0.0.1:5600", timeout=2.0)` with the same shape but states limited to `"missing"`, `"daemon_down"`, `"ok"`, `"unknown"` (no `wrong_state` — the AW probe deliberately does not check buckets)
- [x] 1.4 Add small helpers `_ollama_binary_present()` and `_aw_app_present()` that use `shutil.which` and `Path.exists` respectively
- [x] 1.5 Add module-level constants for the default URLs and model name so tests can monkeypatch them cleanly

## 2. Wire probes into setup.py

- [x] 2.1 Replace the current inline `subprocess.run(["which", "ollama"], …)` block in `setup.py` with a call to `focusmonitor.install.probe_ollama()` and print the result using the same ✅/⚠️/❌ pattern the rest of `setup.py` already uses
- [x] 2.2 Replace the current inline `Path("/Applications/ActivityWatch.app")` block with a call to `focusmonitor.install.probe_activitywatch()`
- [x] 2.3 Keep the Screen Recording permission reminder (it's not automatable — README-only fix for the ordering issue lands in task 4)
- [x] 2.4 Fix the stale `planned_tasks.txt` reference in the "Next steps" print block to `planned_tasks.json`
- [x] 2.5 Verify the `cli.py` path in the "Next steps" print block is resolved via `Path(__file__).parent / "cli.py"` (it already is — keep the existing line)
- [x] 2.6 Manually run `python3 setup.py` on the current machine and confirm the output is clean (Ollama ok, AW ok, model present)

## 3. Unit tests

- [x] 3.1 Create `tests/test_install_flow.py`
- [x] 3.2 Write tests for `probe_ollama` covering: binary missing (`shutil.which` returns None), daemon down (`urlopen` raises `URLError`), wrong state (daemon returns valid JSON but model list excludes `llama3.2-vision`), healthy (daemon returns valid JSON with model present), unknown (daemon returns HTML / invalid JSON)
- [x] 3.3 Write tests for `probe_activitywatch` covering: app missing (`Path.exists` returns False for both candidate paths), daemon down (`urlopen` raises `URLError`), healthy (daemon returns 200 `/api/0/info`), unknown (daemon returns malformed response)
- [x] 3.4 Use `monkeypatch.setattr` on `focusmonitor.install.urllib.request.urlopen` and `focusmonitor.install.shutil.which` — never open a real socket
- [x] 3.5 Run `.venv/bin/pytest tests/test_install_flow.py` and confirm green
- [x] 3.6 Run full suite (`.venv/bin/pytest tests/`) and confirm total stays green (no cross-file regressions)

## 4. README rewrite

- [x] 4.1 Rewrite the "Quick Start" block with a clearly-marked "Prerequisites (one-time)" subsection containing: `brew install ollama`, the Ollama daemon start command(s), `ollama pull llama3.2-vision`, the ActivityWatch install command (brew cask + manual link fallback), and the Screen Recording permission step
- [x] 4.2 Inline the Screen Recording permission note into the sequence immediately before the `python3 cli.py run` step, with the exact System Settings path
- [x] 4.3 Add a "Verifying your install" section right after the Quick Start, with `curl` one-liners against `localhost:11434/api/tags` and `localhost:5600/api/0/info`, plus instructions for running `cli.py run` briefly to confirm a row lands in `~/.focus-monitor/activity.db`
- [x] 4.4 Mention the optional pytest-based smoke check (`.venv/bin/pytest tests/`) as a final verification for users who want the rigorous path, flagged as optional and requiring the dev venv setup from the Contributing section
- [x] 4.5 Visual-check the rendered README on GitHub (or local preview) to confirm the code fences, list markers, and section headings all parse correctly

## 5. Privacy + validation

- [x] 5.1 Run the `privacy-review` skill over the diff and confirm zero findings (no new non-localhost URLs, no new outbound imports, no new dependencies)
- [x] 5.2 Grep the diff for `https?://` and confirm every hit resolves to 127.0.0.1 / localhost / activitywatch.net / ollama.com (the last two are documentation links, not runtime fetches)
- [x] 5.3 Full pytest run (`.venv/bin/pytest tests/`) green, offline, under 10 seconds
- [x] 5.4 `python3 -c "import focusmonitor.install"` with stock macOS Python to confirm no third-party imports leaked in
- [x] 5.5 Walk the README Quick Start end-to-end on the current machine as a sanity check — every step should either already be satisfied (because the machine is set up) or the probe should correctly report the state
