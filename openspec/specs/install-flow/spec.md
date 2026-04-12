## ADDED Requirements

### Requirement: Runnable Quick Start for fresh Mac

The `README.md` Quick Start SHALL be followable end-to-end on a fresh
Mac with no silent gaps. Every prerequisite SHALL be introduced with a
runnable shell command (or a direct download link for GUI installs)
before the step that depends on it.

#### Scenario: New user clones on a fresh Mac

- **WHEN** a user with no prior setup copies the README Quick Start top
  to bottom into a terminal
- **THEN** each command either succeeds or fails with a message that
  points at the next command in the sequence
- **AND** no step assumes a prerequisite that is not introduced earlier
  in the same block

#### Scenario: Screen Recording permission is presented inline

- **WHEN** a user reads the Quick Start sequence
- **THEN** the Screen Recording permission step appears before
  `python3 cli.py run` (the first command that exercises `screencapture`)
- **AND** the instructions name the exact System Settings path

#### Scenario: Prereq block is skippable by experienced users

- **WHEN** a returning user already has Ollama, `llama3.2-vision`, and
  ActivityWatch installed and running
- **THEN** the README visibly marks the prerequisite block so they can
  skip straight to the clone + setup step without reading it line by
  line

### Requirement: Ollama daemon health probe

`setup.py` SHALL check whether the Ollama daemon is actually responding
on `http://127.0.0.1:11434`, not only whether the `ollama` binary is
on PATH. The check SHALL surface one of: binary missing, daemon down,
daemon up but `llama3.2-vision` not pulled, or healthy. Each non-healthy
state SHALL print a concrete next command.

#### Scenario: Ollama binary missing

- **WHEN** `setup.py` runs and `ollama` is not on PATH
- **THEN** it prints "Ollama not found. Install: brew install ollama"
  and continues to the next check (non-fatal)

#### Scenario: Ollama binary present, daemon down

- **WHEN** `setup.py` runs, `ollama` is on PATH, and a GET to
  `http://127.0.0.1:11434/api/tags` fails (connection refused or
  timeout)
- **THEN** it reports "Ollama binary present but daemon not running"
  and prints the start command (`ollama serve` or `brew services start
  ollama` or the equivalent desktop-app launch)

#### Scenario: Ollama daemon up, model missing

- **WHEN** the probe receives a valid response from `/api/tags` and the
  model list does not contain `llama3.2-vision`
- **THEN** it reports "Ollama daemon healthy but model not pulled" and
  prints `ollama pull llama3.2-vision`

#### Scenario: Ollama healthy

- **WHEN** the daemon responds and the configured model is listed
- **THEN** `setup.py` prints a single-line success marker and moves on

#### Scenario: Probe throws an unexpected error

- **WHEN** the probe raises something other than a connection error
  (e.g. JSON decode failure because the server returned HTML)
- **THEN** `setup.py` prints the raw error as a notice and continues
  without crashing

### Requirement: ActivityWatch daemon health probe

`setup.py` SHALL check whether ActivityWatch is actually responding on
`http://127.0.0.1:5600`, not only whether `/Applications/ActivityWatch.app`
exists on disk. The check SHALL surface: binary missing, daemon down,
or healthy. It SHALL NOT check for specific buckets — bucket presence
is a runtime concern, not a setup concern.

#### Scenario: ActivityWatch app missing

- **WHEN** `setup.py` runs and neither `/Applications/ActivityWatch.app`
  nor `~/Applications/ActivityWatch.app` exists
- **THEN** it reports "ActivityWatch.app not found" and points the
  user at `activitywatch.net` for the download (or `brew install --cask
  activitywatch`)

#### Scenario: ActivityWatch app present, daemon down

- **WHEN** the app exists on disk and a GET to
  `http://127.0.0.1:5600/api/0/info` fails
- **THEN** it reports "ActivityWatch installed but not running" and
  prints `open /Applications/ActivityWatch.app`

#### Scenario: ActivityWatch healthy

- **WHEN** the probe receives any 2xx response from `/api/0/info`
- **THEN** `setup.py` prints a single-line success marker and moves on

#### Scenario: Probe never checks bucket existence

- **WHEN** the AW probe runs against a freshly-launched AW with no
  watcher events yet
- **THEN** the probe reports "healthy" anyway
- **AND** bucket-existence checks remain the responsibility of
  `focusmonitor.activitywatch.get_aw_events` at runtime

### Requirement: Probes are loopback-only

All health probes in `setup.py` SHALL contact only `127.0.0.1` or
`localhost`. No probe SHALL introduce a new non-loopback network call
or a new third-party dependency.

#### Scenario: Probe URL audit

- **WHEN** a reviewer runs `grep -rn 'https\?://' focusmonitor/install.py setup.py`
- **THEN** every URL returned resolves to `127.0.0.1` or `localhost`

#### Scenario: New dependency audit

- **WHEN** a reviewer inspects the imports in the probe module
- **THEN** every import resolves to the Python standard library
  (`urllib`, `json`, `subprocess`, `shutil`, `pathlib`) and nothing in
  `requirements-dev.txt` or a third-party package

### Requirement: `setup.py` output matches code behaviour

`setup.py`'s "Next steps" output SHALL reference the actual files
created by `load_config()`. Stale references to pre-migration file
names SHALL be removed.

#### Scenario: Stale planned_tasks.txt reference is removed

- **WHEN** `setup.py` prints its "Next steps" block
- **THEN** it says `~/.focus-monitor/planned_tasks.json` (matching
  `focusmonitor.config.TASKS_JSON_FILE`)
- **AND** it does not mention `planned_tasks.txt`

#### Scenario: CLI path in setup output

- **WHEN** `setup.py` prints the "start the monitor manually" line
- **THEN** the path to `cli.py` is resolved to an absolute path
  (matches `Path(__file__).parent / "cli.py"`.resolve())

### Requirement: Self-verify recipe in README

`README.md` SHALL include a "Verifying your install" section with a
copy-pasteable sequence of commands a new user can run after `setup.py`
to confirm the full pipeline works end to end. The recipe SHALL check
the three local-service touchpoints and SHALL NOT require any
prerequisites beyond those already introduced in the Quick Start.

#### Scenario: Verify section exists

- **WHEN** a user searches the README for "verify" or "verifying"
- **THEN** a section appears with at least: a curl against Ollama's
  `/api/tags`, a curl against AW's `/api/0/info`, and instructions for
  running `cli.py run` long enough to produce a row in
  `~/.focus-monitor/activity.db`

#### Scenario: Verify recipe introduces no new prerequisites

- **WHEN** a user who followed only the Quick Start runs the verify
  recipe
- **THEN** every command in the recipe works without installing
  anything new

### Requirement: Probe logic is unit-tested without real services

The probe helpers in `focusmonitor/install.py` SHALL have unit tests
under `tests/test_install_flow.py` that cover every documented state
(missing, daemon_down, wrong_state, ok, unknown) without talking to a
real service. Tests SHALL use `monkeypatch` on `urllib.request.urlopen`
and `subprocess.run`; cassette-backed tests are not required for this
surface.

#### Scenario: Every state has a test

- **WHEN** the test file is collected by pytest
- **THEN** there is at least one test for each of the five probe
  states on both the Ollama probe and the ActivityWatch probe

#### Scenario: Tests never open a real socket

- **WHEN** the test file runs under pytest-socket
- **THEN** every network call is intercepted by `monkeypatch` before
  a socket is opened
- **AND** the tests pass without an Ollama or ActivityWatch instance
  running on the host

### Requirement: `focusmonitor/install.py` has no third-party imports

The new `focusmonitor/install.py` module SHALL import only from the
Python standard library. It SHALL NOT import any package from
`requirements-dev.txt` or any new runtime dependency. `setup.py` MUST
be runnable before the dev venv is created.

#### Scenario: stdlib-only import audit

- **WHEN** a reviewer greps `focusmonitor/install.py` for imports
- **THEN** every `import` and `from … import …` resolves to a stdlib
  module

#### Scenario: setup.py runs on stock macOS Python

- **WHEN** a user runs `/usr/bin/python3 setup.py` on a fresh macOS
  install with no `.venv` created
- **THEN** `setup.py` imports `focusmonitor.install` and the probes
  run without `ModuleNotFoundError`
