## 1. Dev environment

- [x] 1.1 Create `requirements-dev.txt` with pinned versions: `pytest`, `pytest-recording`, `pytest-socket`, `hypothesis`, `syrupy`, `coverage`, `freezegun`
- [x] 1.2 Add `.venv/`, `.coverage`, `htmlcov/`, `.pytest_cache/`, and `.hypothesis/` to `.gitignore`
- [x] 1.3 Create `.venv` locally and install `requirements-dev.txt` (one-time network event — approve the `block-network.sh` hook prompt explicitly)
- [x] 1.4 Verify install by running `pytest --version` inside the venv
- [x] 1.5 Add `pyproject.toml` or `pytest.ini` with minimal pytest config: `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, and `addopts = "--disable-socket --allow-hosts=127.0.0.1,localhost"`

## 2. Test scaffolding

- [x] 2.1 Create `tests/` directory with `__init__.py`
- [x] 2.2 Create `tests/data/screenshots/` and add two or three deterministic PNG fixtures representing clearly focused and clearly unfocused activity
- [x] 2.3 Create `tests/data/tasks/` and add a canned `planned_tasks.json` fixture
- [x] 2.4 Create `tests/cassettes/ollama/` and `tests/cassettes/activitywatch/` directory stubs with a README explaining the re-record workflow
- [x] 2.5 Create `tests/fixtures/` with `db.py` (seeded-sqlite factory), `ollama.py`, and `activitywatch.py` placeholder modules
- [x] 2.6 Create `tests/conftest.py` with the three core fixtures: `tmp_home` (redirects every `focusmonitor.config` path into a per-test `tmp_path`), `freeze_clock` (freezegun pin to a fixed timestamp), and a session-scoped verification that `pytest-socket` is active and allowing only loopback
- [x] 2.7 Verify `tmp_home` fixture by writing a trivial smoke test that imports `focusmonitor.config` and asserts `DB_PATH` lives under `tmp_path`

## 3. Pilot: rewrite test_analysis.py with hypothesis

- [x] 3.1 Create `tests/test_analysis.py` and port the existing `parse_analysis_json` cases as pytest functions with `assert` diffs
- [x] 3.2 Add hypothesis-based property tests for `parse_analysis_json`: "never crashes on arbitrary text" and "recovers valid JSON embedded in arbitrary prose"
- [x] 3.3 Port `validate_analysis_result`, `build_classification_prompt`, `get_recent_history` cases as pytest functions
- [x] 3.4 Run `pytest tests/test_analysis.py` and confirm green, offline, under 30 seconds

## 4. Ollama cassette-backed tests

- [x] 4.1 Implement `tests/fixtures/ollama.py`: a fixture that yields a configured `focusmonitor.ollama` client ready for recording, plus a helper that applies vcrpy cassette settings (`tests/cassettes/ollama/{test_name}.yaml`, `record_mode=none` by default)
- [x] 4.2 Start real Ollama on `localhost:11434` with the project's default model; run `pytest --record-mode=rewrite tests/test_ollama.py` (second network-policy event — localhost-only, should not trip `block-network.sh`)
- [x] 4.3 Write cassette-backed tests for every public function in `focusmonitor/ollama.py`, covering at minimum: successful classification, malformed response handling, and whatever error paths the module exposes
- [x] 4.4 Review captured cassettes for any user-identifying content before committing; confirm captures used only `tests/data/` inputs
- [x] 4.5 Add capture-date and model-version metadata to each cassette header
- [x] 4.6 Commit cassettes. Run `pytest tests/test_ollama.py` fresh (replay mode) and confirm green

## 5. ActivityWatch cassette-backed tests

- [x] 5.1 Implement `tests/fixtures/activitywatch.py` with the same shape as the Ollama fixture
- [x] 5.2 Start real ActivityWatch on `localhost:5600`; run `pytest --record-mode=rewrite tests/test_activitywatch.py`
- [x] 5.3 Write cassette-backed tests for every public function in `focusmonitor/activitywatch.py`, covering at minimum: fetching events, querying buckets, AFK gating inputs
- [x] 5.4 Review captured cassettes for user-identifying content (window titles, URLs, app names) before committing — this module is the highest risk for personal data leakage into a cassette
- [x] 5.5 Add capture-date and AW-version metadata
- [x] 5.6 Commit cassettes, run replay, confirm green

## 6. Dashboard snapshot tests

- [x] 6.1 Create `tests/test_dashboard.py` using the `tmp_home`, `freeze_clock`, and seeded-db fixtures
- [x] 6.2 Write a snapshot test that calls `build_dashboard()` with a seeded DB and asserts the HTML matches a syrupy snapshot
- [x] 6.3 Run `pytest --snapshot-update tests/test_dashboard.py` to create the initial snapshot under `tests/__snapshots__/`
- [x] 6.4 Review the snapshot: confirm the frozen timestamp is present, confirm no developer-machine paths leak into the rendered HTML
- [x] 6.5 Add snapshot tests for the alternate range views (`yesterday`, `week` — whichever your dashboard actually supports) and any other stable routes
- [x] 6.6 Port useful structural assertions from the old `test_dashboard_render.py` that the snapshot doesn't cover (HTML-escaping of untrusted input, empty-state branching) as focused pytest functions alongside the snapshot
- [x] 6.7 Port dashboard mutation tests from `test_dashboard_mutations.py` as focused pytest functions, using the seeded-db and `tmp_home` fixtures

## 7. Convert remaining tests

- [x] 7.1 Port `test_cleanup.py` → `tests/test_cleanup.py`, using fixtures for DB and `tmp_home`
- [x] 7.2 Port `test_structured_tasks.py` → `tests/test_tasks.py`
- [x] 7.3 Port `test_afk_gating.py` → `tests/test_afk_gating.py`
- [x] 7.4 Port `test_discovered_activities.py` → `tests/test_discovered_activities.py`
- [x] 7.5 Add `tests/test_screenshots.py` covering `deduplicate_screenshots` and any other public helpers in `focusmonitor/screenshots.py`, using the PNG fixtures from `tests/data/screenshots/`
- [x] 7.6 Run the full suite (`pytest`) and confirm green, offline, under 60 seconds

## 8. Remove old harness and wire coverage

- [x] 8.1 Delete the repo-root `test_*.py` files in a single commit along with the final port
- [x] 8.2 Run `coverage run -m pytest && coverage report` and record the baseline coverage per module in the PR description (no threshold enforcement)
- [x] 8.3 Add an optional `pytest-cov` invocation note to the dev docs (not enforced)

## 9. Skill and documentation

- [x] 9.1 Rewrite `.claude/skills/test-focusmonitor/SKILL.md` to invoke `pytest` inside `.venv`, document the report format, and keep the existing hard rules (do not modify test files, do not install deps, stop on import errors)
- [x] 9.2 Add a documented sub-workflow to the skill for cassette re-record: command, review step, commit expectations
- [x] 9.3 Update `CLAUDE.md`: `tests/` layout, dev-venv workflow, offline-at-runtime hard rule, cassette re-record workflow, cassette privacy-review rule, note that pytest-ecosystem deps are dev-only and do not break the "stdlib for runtime" default
- [x] 9.4 Verify `grep -r "python3 test_" .claude CLAUDE.md README* 2>/dev/null` returns nothing stale
- [x] 9.5 Final validation: in a clean checkout, run `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest` and confirm green
      _(Literal clean-install skipped by request; verified via `pip check` (no broken requirements), `pip freeze` matches pins + transitive only, static-analysed every `tests/` import resolves to declared deps, full suite green offline.)_
