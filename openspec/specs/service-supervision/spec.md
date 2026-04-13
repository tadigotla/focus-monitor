### Requirement: Per-component launchd plists
The system SHALL manage Pulse and Scope as two independent launchd user agents: `com.focusmonitor.pulse` and `com.focusmonitor.scope`. Each plist SHALL have `RunAtLoad=true` and `KeepAlive=true`, and SHALL write stdout/stderr under `~/.focus-monitor/logs/` with a per-component filename (`pulse.out.log`, `pulse.err.log`, `scope.out.log`, `scope.err.log`).

#### Scenario: `service install` writes both plists
- **WHEN** the user runs `python3 cli.py service install`
- **THEN** `~/Library/LaunchAgents/com.focusmonitor.pulse.plist` exists
- **AND** `~/Library/LaunchAgents/com.focusmonitor.scope.plist` exists
- **AND** both plists declare `RunAtLoad=true` and `KeepAlive=true`
- **AND** neither plist is loaded into launchd as a side effect of `service install`

#### Scenario: Independent restart
- **WHEN** the Scope service is running under launchd and Pulse is separately running under launchd
- **AND** the Scope process is killed with SIGKILL
- **THEN** launchd respawns only the Scope process
- **AND** the Pulse process is not restarted

### Requirement: Python-resolution shim
The ProgramArguments of both launchd plists SHALL target a shell shim committed to the repo (default path: `bin/focusmonitor-service`) rather than a hardcoded Python interpreter path. The shim SHALL resolve Python at every invocation in the following order: (1) `<REPO_ROOT>/.venv/bin/python3` if it exists and is executable, (2) `command -v python3` against launchd's PATH, (3) `/opt/homebrew/bin/python3`, (4) `/usr/bin/python3`. The shim SHALL `exec` the resolved interpreter with `<REPO_ROOT>/cli.py` and all forwarded arguments.

#### Scenario: Brew upgrades Python after install
- **WHEN** a user has run `service install`
- **AND** later upgrades Python via `brew upgrade python`
- **THEN** the next launchd invocation of either service picks up the new interpreter without re-running `service install`

#### Scenario: Shim logs its resolution decision
- **WHEN** the shim runs
- **THEN** it writes a single line to stderr of the form `focusmonitor-service: resolved python=<path>` before `exec`
- **AND** that line appears in `~/.focus-monitor/logs/pulse.err.log` or `scope.err.log` on every service start

#### Scenario: Shim is POSIX sh
- **WHEN** a reviewer inspects `bin/focusmonitor-service`
- **THEN** the shebang is `#!/bin/sh` (not `/bin/bash`)
- **AND** the script contains no bashisms (arrays, `[[ ]]`, `$(( ))` beyond POSIX arithmetic)

#### Scenario: Shim contains no network calls
- **WHEN** a reviewer greps the shim for `curl`, `wget`, `nc`, `ssh`, `http://`, `https://`
- **THEN** no matches are returned

### Requirement: Service lifecycle verbs
The `cli.py service` subcommand SHALL expose `install`, `uninstall`, `start`, `stop`, and `status` verbs. `start` SHALL bootstrap both plists into launchd (`launchctl bootstrap` on modern macOS, falling back to `launchctl load` on older versions). `stop` SHALL bootout both plists. `status` SHALL report per-component state by invoking `launchctl print` on each label.

#### Scenario: Install then start
- **WHEN** the user runs `python3 cli.py service install`
- **AND** then runs `python3 cli.py service start`
- **THEN** both `com.focusmonitor.pulse` and `com.focusmonitor.scope` are loaded into the user's launchd domain
- **AND** both processes are running within 5 seconds

#### Scenario: Stop without uninstall
- **WHEN** the services are loaded and the user runs `python3 cli.py service stop`
- **THEN** both services are booted out of launchd
- **AND** the plist files in `~/Library/LaunchAgents/` remain on disk

#### Scenario: Uninstall removes plist files
- **WHEN** the user runs `python3 cli.py service uninstall`
- **THEN** both services are first booted out if loaded
- **AND** both plist files are removed from `~/Library/LaunchAgents/`

#### Scenario: Status reports per-component state
- **WHEN** the user runs `python3 cli.py service status`
- **THEN** the CLI prints a line for Pulse and a line for Scope
- **AND** each line identifies whether the service is not-installed, installed-but-not-loaded, loaded-and-running, or loaded-but-crashing

### Requirement: Services bind only to loopback
The plists managed by `cli.py service` SHALL only start processes that bind to `127.0.0.1` or `localhost`. Pulse's dashboard HTTP server SHALL remain bound to `:9876` on loopback. Scope's API SHALL remain bound to `:9877` on loopback. `service install` SHALL NOT introduce any new listening port, and SHALL NOT add environment variables or ProgramArguments that would redirect either component to a non-loopback interface.

#### Scenario: Port audit after install
- **WHEN** `service install` has been run and both services are loaded
- **AND** a reviewer runs `lsof -iTCP -sTCP:LISTEN -P -n | grep -E 'python|focusmonitor'`
- **THEN** every listening socket the services own is bound to `127.0.0.1` (not `0.0.0.0` and not a routable interface)

#### Scenario: Plist audit for non-loopback bindings
- **WHEN** a reviewer greps both generated plist files for `0.0.0.0`, any routable IP, or any non-loopback hostname
- **THEN** no matches are returned

### Requirement: Plist regeneration on re-run
Re-running `python3 cli.py service install` SHALL overwrite both plist files deterministically with the current repo path. This is the supported mechanism for re-pinning the shim location after the repo is moved on disk.

#### Scenario: Repo moved after initial install
- **WHEN** a user has installed the service, then moves the repo checkout to a new path on disk
- **AND** runs `python3 cli.py service install` from the new path
- **THEN** both plists are rewritten to point at the new `bin/focusmonitor-service` location
- **AND** running `service start` after the rewrite brings the services up against the new path

### Requirement: Detect and warn about the legacy `com.focusmonitor.agent` plist
When `cli.py service install` runs and finds `~/Library/LaunchAgents/com.focusmonitor.agent.plist` already present on disk, it SHALL print a loud warning naming the manual upgrade recipe (unload the old label, remove the old plist file, then re-run `service install` and `service start`). It SHALL NOT touch the old plist automatically.

#### Scenario: Legacy plist present
- **WHEN** `service install` runs and `~/Library/LaunchAgents/com.focusmonitor.agent.plist` exists
- **THEN** the CLI prints a multi-line warning that includes the exact `launchctl bootout` (or `launchctl unload`) command for the old label
- **AND** the CLI includes the exact `rm` command for the old plist file
- **AND** the CLI still writes the new `com.focusmonitor.pulse` and `com.focusmonitor.scope` plists
- **AND** the CLI does not run any destructive command on the user's behalf
