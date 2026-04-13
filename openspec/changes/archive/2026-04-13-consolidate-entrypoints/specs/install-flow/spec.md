## MODIFIED Requirements

### Requirement: Runnable Quick Start for fresh Mac

The `README.md` Quick Start SHALL be followable end-to-end on a fresh
Mac with no silent gaps. Every prerequisite SHALL be introduced with a
runnable shell command (or a direct download link for GUI installs)
before the step that depends on it. The Quick Start SHALL use the new
`cli.py start` and `cli.py service install`/`service start` verbs as
the canonical invocation; deprecated `cli.py run` and `cli.py dashboard`
SHALL NOT appear in the Quick Start.

#### Scenario: New user clones on a fresh Mac

- **WHEN** a user with no prior setup copies the README Quick Start top
  to bottom into a terminal
- **THEN** each command either succeeds or fails with a message that
  points at the next command in the sequence
- **AND** no step assumes a prerequisite that is not introduced earlier
  in the same block
- **AND** the first command that runs focus-monitor is
  `python3 cli.py start` (foreground mode)

#### Scenario: Screen Recording permission is presented inline

- **WHEN** a user reads the Quick Start sequence
- **THEN** the Screen Recording permission step appears before
  `python3 cli.py start` (the first command that exercises `screencapture`)
- **AND** the instructions name the exact System Settings path

#### Scenario: Prereq block is skippable by experienced users

- **WHEN** a returning user already has Ollama, `llama3.2-vision`, and
  ActivityWatch installed and running
- **THEN** the README visibly marks the prerequisite block so they can
  skip straight to the clone + setup step without reading it line by
  line

#### Scenario: Quick Start ends with background-mode instructions

- **WHEN** the user has verified foreground mode works
- **THEN** the Quick Start's final step is `python3 cli.py service install && python3 cli.py service start`
- **AND** the "To stop it" line uses `python3 cli.py service stop`
- **AND** no `launchctl load` / `launchctl unload` commands appear in the Quick Start

### Requirement: `setup.py` output matches code behaviour

`setup.py`'s "Next steps" output SHALL reference the actual files
created by `load_config()` and the actual verbs exposed by `cli.py`.
Stale references to pre-migration file names or pre-migration verb
names SHALL be removed. `setup.py` SHALL NOT write a launchd plist as
a side effect — plist management is owned by `cli.py service install`.

#### Scenario: Stale planned_tasks.txt reference is removed

- **WHEN** `setup.py` prints its "Next steps" block
- **THEN** it says `~/.focus-monitor/planned_tasks.json` (matching
  `focusmonitor.config.TASKS_JSON_FILE`)
- **AND** it does not mention `planned_tasks.txt`

#### Scenario: CLI path in setup output

- **WHEN** `setup.py` prints the "start the monitor manually" line
- **THEN** the command shown is `python3 <abs path>/cli.py start`
  (matching `Path(__file__).parent / "cli.py"`.resolve())
- **AND** the command shown is NOT `python3 cli.py run`

#### Scenario: `setup.py` does not write the plist

- **WHEN** `setup.py` runs to completion on a fresh install
- **THEN** no file is created under `~/Library/LaunchAgents/`
- **AND** the "Next steps" output explicitly directs the user to run
  `python3 cli.py service install` when they are ready to enable
  background mode

## ADDED Requirements

### Requirement: Upgrading section in README

`README.md` SHALL include an "Upgrading from the old launchd agent"
section that documents the manual migration path for users who
installed focus-monitor before this change. The section SHALL list the
exact commands required: unload the old `com.focusmonitor.agent`
label, remove the old plist file, then run `python3 cli.py service
install` and `python3 cli.py service start`. It SHALL explain that no
automatic migration exists and why (simplicity, auditability).

#### Scenario: Upgrading section exists

- **WHEN** a user searches the README for "Upgrading"
- **THEN** a section appears with a copy-pasteable sequence of at
  least four commands: `launchctl bootout` (or `launchctl unload`) for
  the old label, `rm` for the old plist path, `python3 cli.py service
  install`, and `python3 cli.py service start`

#### Scenario: Upgrading section warns about the respawn loop

- **WHEN** a user who has not upgraded simply pulls the new code
- **THEN** the Upgrading section explicitly warns that launchd will
  respawn-loop the old plist because `monitor.py` has been deleted
- **AND** the section tells the user to run the unload command first
  before doing anything else

### Requirement: Wipe-all-data instructions reference new labels

The README's "How to wipe all your data" section SHALL reference the
new launchd labels (`com.focusmonitor.pulse`,
`com.focusmonitor.scope`) and SHALL use `cli.py service uninstall` as
the canonical removal command, with raw `launchctl bootout` + `rm` as
a fallback for users who cannot run `cli.py`.

#### Scenario: Wipe-all-data uses the new verbs

- **WHEN** a user follows the "How to wipe all your data" recipe
- **THEN** the first command is `python3 cli.py service uninstall`
- **AND** the second command is `rm -rf ~/.focus-monitor/`
- **AND** the fallback section shows `launchctl bootout` for both new
  labels and explicit `rm` commands for both new plist paths
