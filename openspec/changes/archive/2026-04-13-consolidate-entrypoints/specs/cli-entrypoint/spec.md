## MODIFIED Requirements

### Requirement: Unified CLI with subcommands
The system SHALL provide a single CLI entry point (`cli.py`) with subcommands that replace direct script invocation. The canonical verbs are `start`, `stop`, `service`, and `setup`. The legacy verbs `run` and `dashboard` SHALL continue to work for one release cycle as deprecated aliases and SHALL print a one-line deprecation notice on stderr before dispatching.

#### Scenario: Start both components in foreground
- **WHEN** the user executes `python3 cli.py start` with no component argument
- **THEN** the CLI launches Pulse and Scope as child processes attached to the current terminal
- **AND** stdout from both children is prefixed with `[pulse]` / `[scope]` and interleaved into the parent's stdout
- **AND** the dashboard becomes reachable at `http://localhost:9876`
- **AND** the Scope API becomes reachable at `http://localhost:9877`

#### Scenario: Start only Pulse in foreground
- **WHEN** the user executes `python3 cli.py start pulse`
- **THEN** the CLI replaces itself with the Pulse monitor process (equivalent to `python3 -m focusmonitor.main`)
- **AND** no Scope process is started

#### Scenario: Start only Scope in foreground
- **WHEN** the user executes `python3 cli.py start scope`
- **THEN** the CLI replaces itself with the Scope API server process
- **AND** no Pulse process is started

#### Scenario: Setup
- **WHEN** the user executes `python3 cli.py setup`
- **THEN** the setup probes run (Ollama, ActivityWatch, screen-recording reminder)
- **AND** `~/.focus-monitor/` is scaffolded with default config if missing
- **AND** `setup.py` does NOT write a launchd plist
- **AND** the "Next steps" output points the user at `python3 cli.py service install` when they are ready to enable background mode

#### Scenario: Deprecated `run` alias
- **WHEN** the user executes `python3 cli.py run`
- **THEN** the CLI prints `run is deprecated; use 'start' instead` on stderr
- **AND** dispatches to `start` with both components

#### Scenario: Deprecated `dashboard` alias
- **WHEN** the user executes `python3 cli.py dashboard`
- **THEN** the CLI prints `dashboard is deprecated; use 'start pulse' instead` on stderr
- **AND** dispatches to `start pulse` (since the dashboard HTTP server is embedded in Pulse)

### Requirement: Default subcommand
The system SHALL default to the `start` subcommand when no subcommand is specified. `start` with no component argument starts both Pulse and Scope.

#### Scenario: No subcommand given
- **WHEN** the user executes `python3 cli.py` without arguments
- **THEN** the system behaves as if `python3 cli.py start` was executed
- **AND** both Pulse and Scope are launched

### Requirement: Dashboard-only mode
The dashboard HTTP server SHALL be reachable at `http://localhost:9876` whenever Pulse is running (in foreground or background). There is no standalone "dashboard without Pulse" mode — the dashboard reads data that only Pulse produces, and the embedded server lives inside the Pulse process.

#### Scenario: View live data while Pulse is running
- **WHEN** the user has run `python3 cli.py start pulse` (or `start`, or the background service is loaded)
- **THEN** the dashboard is served on `http://localhost:9876`
- **AND** the dashboard is bound to loopback only

#### Scenario: Dashboard is unavailable when Pulse is not running
- **WHEN** Pulse is not running in any mode
- **THEN** `http://localhost:9876` is not reachable
- **AND** the CLI does not offer a "dashboard-only" verb

## ADDED Requirements

### Requirement: Foreground supervision tears down both children on Ctrl-C
When `cli.py start` is running both components as children in the foreground, it SHALL install signal handlers such that `SIGINT` (Ctrl-C) and `SIGTERM` propagate to both children, wait up to a bounded timeout for clean exit, then `SIGKILL` any survivor before the parent exits.

#### Scenario: Ctrl-C while both children are running
- **WHEN** the user presses Ctrl-C in the terminal running `python3 cli.py start`
- **THEN** the parent sends `SIGTERM` to both the Pulse child and the Scope child
- **AND** waits up to 10 seconds for them to exit cleanly
- **AND** sends `SIGKILL` to any child still alive after the timeout
- **AND** the parent process exits with a non-zero status only if a child had to be killed

#### Scenario: One child crashes unexpectedly
- **WHEN** either Pulse or Scope exits with a non-zero status while `cli.py start` is running
- **THEN** the parent tears down the surviving child using the same SIGTERM → timeout → SIGKILL sequence
- **AND** the parent exits with a non-zero status
- **AND** the parent prints a one-line message identifying which child died and its exit code

### Requirement: Stop verb for foreground sessions
The `stop` verb SHALL terminate children started by a `cli.py start` invocation in the same terminal session. It SHALL NOT affect launchd-managed background services; those are managed via `service stop`.

#### Scenario: Stop with no foreground session
- **WHEN** the user runs `python3 cli.py stop` and no `cli.py start` is active in the current session
- **THEN** the CLI prints `no foreground session to stop` and exits with status 0
- **AND** any running launchd-managed Pulse or Scope processes are left untouched
