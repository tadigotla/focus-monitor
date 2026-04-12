---
name: test-focusmonitor
description: Run focus-monitor's pytest suite inside the dev `.venv`. Offline-only by default; includes a documented re-record sub-workflow for vcrpy cassettes. Use when you want to verify the project still works after a change.
---

# test-focusmonitor

focus-monitor's tests live under `tests/` and run via pytest inside a
local dev virtualenv. Test runs are **offline by default** — `pytest-socket`
is wired to block every non-loopback connection, and cassette-backed
tests for `ollama`/`activitywatch` replay from committed vcrpy cassettes
under `tests/cassettes/`.

## Hard rules

- **DO NOT** modify any `tests/**/*.py` file as part of running this skill.
  Fixing a failing test is a separate task; this skill only reports.
- **DO NOT** run `pip install`, `pip upgrade`, or touch `requirements-dev.txt`
  from this skill. If a dependency is missing, report it and stop — the
  user will handle the install explicitly.
- **DO NOT** run tests from any directory other than the repo root.
- **DO NOT** re-record cassettes from the main report flow. Re-recording
  is a separate sub-workflow (see below) that requires real local services
  and deliberate approval.

## How to invoke

Ask: "Run test-focusmonitor" or "Run the focus-monitor tests".

For cassette re-record: "Re-record the Ollama cassettes" or
"Re-record the ActivityWatch cassettes".

## What to do (default: run + report)

1. Confirm you are at the repo root (directory containing `monitor.py`,
   `dashboard.py`, `setup.py`, and the `focusmonitor/` package).
2. Confirm `.venv/bin/pytest` exists. If not, report "dev venv not set up;
   run `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`"
   and stop. Never run the install yourself.
3. Run:
   ```
   .venv/bin/pytest tests/
   ```
4. Capture the final summary line (e.g. `214 passed in 9.48s`) and any
   `FAILED` lines plus the last ~20 lines of each failure's output.
5. Report in the format below.
6. If the run crashes with an import error, report it and stop — import
   errors usually indicate a broken repo state or a missing dev dep.

## Report format

```
# test-focusmonitor report

| File                              | Collected | Result |
|-----------------------------------|----------:|--------|
| tests/test_activitywatch.py       |        14 | PASS   |
| tests/test_afk_gating.py          |        19 | PASS   |
| tests/test_analysis.py            |        43 | PASS   |
| tests/test_cleanup.py             |        11 | PASS   |
| tests/test_conftest_smoke.py      |        11 | PASS   |
| tests/test_dashboard.py           |        13 | PASS   |
| tests/test_dashboard_mutations.py |        41 | PASS   |
| tests/test_discovered_activities.py|       15 | PASS   |
| tests/test_nudges.py              |         7 | PASS   |
| tests/test_ollama.py              |        10 | PASS   |
| tests/test_screenshots.py         |        12 | PASS   |
| tests/test_tasks.py               |        18 | PASS   |

## Failures

(omit this section if zero failures)

### tests/test_foo.py::TestBar::test_baz
<traceback / assertion diff, ~20 lines>

## Summary
214/214 passed in 9.5s. All tests green.
```

(If anything fails, replace the summary with `N/M passed, K failed`.)

## Cassette re-record sub-workflow

Re-record cassettes when any of the following are true:
- You bumped `DEFAULT_CONFIG["ollama_model"]` or upgraded Ollama.
- You upgraded ActivityWatch.
- A cassette-backed test is failing for a reason you suspect is upstream
  drift (response shape change, new required header, etc.).
- You are intentionally adding a new interaction to an existing test.

Do NOT re-record for any other reason. Cassettes are the authoritative
record of real service behaviour — re-recording "just because" loses that
signal.

### Ollama re-record

1. Confirm real Ollama is running on `localhost:11434` and the
   `DEFAULT_CONFIG["ollama_model"]` is pulled:
   ```
   curl -s http://localhost:11434/api/tags | grep <model_name>
   ```
2. From the repo root:
   ```
   .venv/bin/pytest --record-mode=rewrite tests/test_ollama.py::TestQueryOllamaText tests/test_ollama.py::TestQueryOllamaWithImages
   ```
3. Review the diff:
   ```
   git diff tests/cassettes/ollama/
   ```
   Scan the cassette contents for anything that looks personal (window
   titles, file paths, app names, model-quality errors you didn't expect).
   If the captures contain anything beyond fixture strings and stdlib
   User-Agent, **discard the diff** (`git checkout tests/cassettes/ollama/`)
   and investigate why.
4. Update the `capture_date` and `model` metadata in the YAML header of
   each touched cassette.
5. Run once more in replay mode to confirm green:
   ```
   .venv/bin/pytest tests/test_ollama.py
   ```
6. Commit in a dedicated PR with message `tests: re-record ollama
   cassettes (<reason>)`.

### ActivityWatch re-record

ActivityWatch re-records talk to a **separate testing instance**, not
your production `:5600`. This is strictly enforced by `scripts/seed_aw_fixture_buckets.py`,
which refuses to run if the server reports `testing=false`.

1. In a separate terminal, start the testing instance:
   ```
   /Applications/ActivityWatch.app/Contents/MacOS/aw-server --testing
   ```
   (It binds `localhost:5666` and uses a separate database; production
   AW on `:5600` is unaffected.)
2. Seed the fixture buckets:
   ```
   python3 scripts/seed_aw_fixture_buckets.py
   ```
3. From the repo root:
   ```
   .venv/bin/pytest --record-mode=rewrite tests/test_activitywatch.py::TestGetAwEvents tests/test_activitywatch.py::TestGetAfkState
   ```
4. Review the diff:
   ```
   git diff tests/cassettes/activitywatch/
   ```
   Every string in a clean re-record should be a fixture I seeded
   (`test-fixture`, `fixture-editor`, etc), an AW framework constant, or
   a stdlib version. If a real hostname, window title, or app name
   appears, **discard the diff** and check whether testing mode was
   actually active (the `hostname` field in the cassette body should say
   `test-fixture`, not the developer's machine name).
5. Update the `capture_date` and `aw_version` metadata.
6. Run once more in replay mode:
   ```
   .venv/bin/pytest tests/test_activitywatch.py
   ```
7. Commit in a dedicated PR.

## What this skill does NOT do

- It does not fix failing tests.
- It does not add new tests.
- It does not run linters, type checkers, or static analysers.
- It does not install dependencies.
- It does not re-record cassettes except via the explicit sub-workflow
  above, which requires the user to have already started the real
  services.
- It does not regenerate the snapshot files under `tests/__snapshots__/`
  — that is `pytest --snapshot-update`, a separate deliberate step that
  belongs in the PR that changes the dashboard template.
