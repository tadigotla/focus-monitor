## ADDED Requirements

### Requirement: Test runner

The project SHALL use pytest as the single test runner. Tests SHALL live under `tests/` and SHALL be discovered by pytest's default collection rules. Direct execution of individual test files via `python3 tests/<file>.py` SHALL NOT be a supported workflow.

#### Scenario: Default invocation from the repo root

- **WHEN** a developer runs `pytest` from the repo root with the dev venv active
- **THEN** pytest discovers every `tests/test_*.py` file and runs all collected tests
- **AND** the run exits with code `0` on full success

#### Scenario: Selection by keyword

- **WHEN** a developer runs `pytest -k parse_analysis_json`
- **THEN** only tests whose node ID matches the keyword are collected and run

#### Scenario: Direct-execution path is removed

- **WHEN** a developer runs `python3 tests/test_analysis.py` directly
- **THEN** the file either does nothing visible or errors out
- **AND** the documented path is `pytest` inside the dev venv

### Requirement: Offline-at-runtime enforcement

Test runs SHALL NOT open network sockets to any host outside the loopback range. The harness SHALL enforce this with `pytest-socket` configured to allow only `127.0.0.1` and `localhost`, so that any inadvertent outbound connection fails the test loudly rather than succeeding silently.

#### Scenario: Test tries to reach a non-loopback host

- **WHEN** a test attempts to open a socket to `example.com` or any non-loopback address
- **THEN** `pytest-socket` raises `SocketBlockedError`
- **AND** the offending test fails with a clear message naming the blocked host

#### Scenario: Test talks to Ollama via cassette replay

- **WHEN** a test makes an HTTP request to `http://127.0.0.1:11434/` with a vcrpy cassette active
- **THEN** vcrpy intercepts the request and returns the recorded response
- **AND** `pytest-socket` does not block the request because the host is in the loopback allow-list

#### Scenario: Full suite with no network available

- **WHEN** a developer disconnects from the network and runs `pytest`
- **THEN** every test passes
- **AND** no test depends on reaching any external host

### Requirement: HTTP record and replay for external services

Tests that exercise `focusmonitor.ollama` or `focusmonitor.activitywatch` SHALL use vcrpy cassettes captured from real local services. Cassettes SHALL be committed to the repository under `tests/cassettes/<service>/`. Hand-written fake HTTP responses for these services SHALL NOT be used as a primary testing mechanism.

#### Scenario: First run uses a committed cassette

- **WHEN** a fresh clone runs the Ollama tests after `pip install -r requirements-dev.txt`
- **THEN** vcrpy loads the committed cassette and replays it
- **AND** no connection to `127.0.0.1:11434` is actually attempted

#### Scenario: Re-recording a cassette

- **WHEN** a developer runs `pytest --record-mode=rewrite -k test_ollama` with real Ollama running on `localhost:11434`
- **THEN** vcrpy contacts the real service, records the interaction, and overwrites the cassette
- **AND** the resulting cassette diff is visible in `git status` for review

#### Scenario: Cassette staleness marker

- **WHEN** a developer reviews a cassette file
- **THEN** the cassette contains a comment or metadata field naming the capture date and the model version (for Ollama) or the ActivityWatch version
- **AND** this metadata is sufficient to judge whether a re-record is needed

### Requirement: Cassette privacy review

Cassettes SHALL be captured against the deterministic fixture corpus under `tests/data/`, not against live `~/.focus-monitor/` data. Before a newly-recorded cassette is committed, the developer SHALL review it for any user-identifying content and reject the commit if such content is present.

#### Scenario: Capture uses fixture corpus

- **WHEN** a developer records an Ollama cassette
- **THEN** the screenshots and task lists used during capture come from `tests/data/screenshots/` and `tests/data/tasks/`
- **AND** no data from the developer's own `~/.focus-monitor/` directory is sent to the local Ollama instance during capture

#### Scenario: Privacy review before commit

- **WHEN** a developer stages a new or updated cassette for commit
- **THEN** the developer has inspected the cassette content for personal names, file paths, window titles, or other identifying information
- **AND** any such content is either removed, or the cassette is discarded and re-recorded from a cleaner corpus

### Requirement: Property testing for parsers

Parser functions whose job is to tolerate arbitrary or hostile input — at minimum `focusmonitor.analysis.parse_analysis_json` — SHALL have property-based tests using `hypothesis`. Property tests SHALL assert safety properties (does not crash, returns `None` or a valid dict) rather than exact equality.

#### Scenario: Random garbage input does not crash the parser

- **WHEN** `parse_analysis_json` is called with arbitrary text generated by hypothesis strategies
- **THEN** it either returns `None` or returns a dict with the expected keys
- **AND** it never raises an uncaught exception

#### Scenario: Valid JSON embedded in noise is still extracted

- **WHEN** hypothesis generates a valid JSON object surrounded by arbitrary prose and markdown fences
- **THEN** `parse_analysis_json` returns the embedded object intact

### Requirement: Snapshot testing for dashboard rendering

Dashboard HTML output SHALL be validated via full-page snapshot tests using `syrupy`. Snapshots SHALL be committed under `tests/__snapshots__/` and updated explicitly via `pytest --snapshot-update`. Substring-based structural assertions SHALL NOT be the primary mechanism for validating dashboard rendering.

#### Scenario: Snapshot matches committed golden

- **WHEN** `build_dashboard()` is called with a seeded test database and frozen time
- **THEN** the returned HTML is byte-identical to the committed snapshot for that scenario

#### Scenario: Intentional template change

- **WHEN** a developer changes a template and runs `pytest --snapshot-update`
- **THEN** syrupy rewrites the affected snapshot files
- **AND** the diff is visible in `git status` for review in the same commit as the template change

#### Scenario: Unintentional regression

- **WHEN** a developer changes unrelated code and the dashboard HTML output drifts
- **THEN** the snapshot test fails with a readable diff showing the unexpected change

### Requirement: Per-test isolation of user data paths

Every test SHALL run against a temporary `~/.focus-monitor/` directory provided by a shared fixture. Tests SHALL NOT read from or write to the developer's real `~/.focus-monitor/`. Tests SHALL NOT patch `focusmonitor.config` module globals by hand.

#### Scenario: Fixture redirects user data root

- **WHEN** a test requests the `tmp_home` fixture
- **THEN** `focusmonitor.config.DB_PATH`, `DISCOVERED_FILE`, `TASKS_JSON_FILE`, `TASKS_FILE`, and any other user-data paths resolve under a per-test `tmp_path`
- **AND** on test teardown the temporary directory is removed

#### Scenario: Two tests do not see each other's state

- **WHEN** test A writes a task to `planned_tasks.json` and test B runs afterward
- **THEN** test B sees an empty `planned_tasks.json` (or no file at all)

### Requirement: Deterministic test environment

Tests whose output depends on wall-clock time SHALL use `freezegun` to pin the clock. Tests that depend on database state SHALL use a seeded fixture corpus so the same inputs produce identical outputs on every run.

#### Scenario: Time is frozen for dashboard snapshot

- **WHEN** a dashboard snapshot test runs
- **THEN** calls to `datetime.now()` and related functions return a fixed, documented timestamp
- **AND** the rendered HTML contains that timestamp verbatim

#### Scenario: Database seed is reproducible

- **WHEN** a seeded-database fixture is requested
- **THEN** the returned database contains a fixed set of rows drawn from `tests/data/`
- **AND** two consecutive test runs against the same fixture produce byte-identical query results

### Requirement: Coverage reporting

The harness SHALL produce a coverage report on request via `coverage.py`. The report SHALL cover the `focusmonitor/` package. A coverage threshold SHALL NOT be enforced by this change.

#### Scenario: Coverage report on demand

- **WHEN** a developer runs `coverage run -m pytest && coverage report`
- **THEN** a line-coverage summary for every module under `focusmonitor/` is printed
- **AND** the exit code is not influenced by the coverage percentage

### Requirement: External-integration coverage floor

Every public function in `focusmonitor.ollama` and `focusmonitor.activitywatch` SHALL have at least one test that exercises it via cassette replay. Both modules are primary network boundaries and their behaviour drift is the main thing this change exists to catch.

#### Scenario: Ollama client has cassette-backed tests

- **WHEN** the test suite runs
- **THEN** every public function in `focusmonitor/ollama.py` is covered by at least one test that replays a real recorded interaction

#### Scenario: ActivityWatch client has cassette-backed tests

- **WHEN** the test suite runs
- **THEN** every public function in `focusmonitor/activitywatch.py` is covered by at least one test that replays a real recorded interaction

### Requirement: Developer setup and dependency management

Test-only dependencies SHALL live in a committed `requirements-dev.txt` with exact version pins. They SHALL be installed into a local `.venv` that is excluded from version control. `focusmonitor/` runtime code SHALL NOT import any test-only dependency.

#### Scenario: Fresh clone setup path

- **WHEN** a developer clones the repo and runs `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`
- **THEN** the dev environment is ready
- **AND** running `pytest` afterward produces a green suite with no further setup

#### Scenario: Runtime code does not import test deps

- **WHEN** `focusmonitor/` is imported outside the dev venv (e.g., from the system Python)
- **THEN** no `ImportError` occurs for pytest, vcrpy, hypothesis, syrupy, coverage, pytest-socket, or freezegun
- **AND** the `focusmonitor` package runs normally

### Requirement: Skill and documentation updates

The `.claude/skills/test-focusmonitor` skill SHALL be rewritten to invoke `pytest` inside the dev venv. `CLAUDE.md` SHALL be updated to describe the new test layout, the dev-venv workflow, the offline-at-runtime hard rule, the cassette re-record workflow, and the cassette privacy-review rule.

#### Scenario: Skill runs pytest

- **WHEN** the `test-focusmonitor` skill is invoked
- **THEN** it runs `pytest` inside `.venv` from the repo root and reports results
- **AND** it does not attempt to execute any `test_*.py` file directly

#### Scenario: CLAUDE.md describes the harness

- **WHEN** a new agent reads `CLAUDE.md`
- **THEN** it finds a concise description of the `tests/` layout, the dev-venv setup, the `pytest` command, and the cassette re-record and privacy-review rules
