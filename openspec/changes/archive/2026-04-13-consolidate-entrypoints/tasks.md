## 1. Shell shim and plist templates

- [x] 1.1 Create `bin/focusmonitor-service` POSIX shell shim that resolves `REPO_ROOT` from its own location, prefers `.venv/bin/python3`, falls back to `command -v python3` then `/opt/homebrew/bin/python3` then `/usr/bin/python3`, logs `focusmonitor-service: resolved python=<path>` to stderr, and `exec`s with `$REPO_ROOT/cli.py "$@"`
- [x] 1.2 Mark shim executable (`chmod +x bin/focusmonitor-service`) and add it to the git index
- [x] 1.3 Add plist-template helpers to a new module `focusmonitor/service.py` that generate the Pulse and Scope plist strings deterministically from a single `(label, args, log_dir)` tuple, with no hardcoded python path

## 2. `cli.py` new verbs — foreground

- [x] 2.1 Add `start` subcommand with optional `component` positional (`pulse` | `scope` | absent)
- [x] 2.2 When `component == "pulse"`, exec `python -m focusmonitor.main` via `os.execvp`
- [x] 2.3 When `component == "scope"`, exec the Scope API entrypoint via `os.execvp` (see task 4.1)
- [x] 2.4 When component is absent, `subprocess.Popen` both children with `PYTHONUNBUFFERED=1`, line-buffered stdout, and a readline loop that prefixes each line with `[pulse]` / `[scope]`
- [x] 2.5 Install `SIGINT` and `SIGTERM` handlers on the parent that send `SIGTERM` to both children, wait up to 10 seconds, then `SIGKILL` any survivor
- [x] 2.6 If either child exits with non-zero status while the other is still running, tear down the survivor using the same sequence and exit the parent non-zero with a one-line identifier
- [x] 2.7 Default subcommand is `start` (matches the existing default-dispatch pattern in `cli.py`)
- [x] 2.8 Add `stop` subcommand that prints `no foreground session to stop` and exits 0 when no session is tracked in the current tty; no launchd interaction

## 3. `cli.py` new verbs — service

- [x] 3.1 Add `service` subcommand group with `install`, `uninstall`, `start`, `stop`, `status` children
- [x] 3.2 `service install` writes `~/Library/LaunchAgents/com.focusmonitor.pulse.plist` and `~/Library/LaunchAgents/com.focusmonitor.scope.plist`, both pointing at the shim with `ProgramArguments = [<shim>, "start", "pulse"|"scope"]`, both with `RunAtLoad=true` `KeepAlive=true`, and stdout/stderr under `~/.focus-monitor/logs/{pulse,scope}.{out,err}.log`
- [x] 3.3 `service install` detects `~/Library/LaunchAgents/com.focusmonitor.agent.plist` and prints the loud legacy-upgrade warning with the exact unload + rm commands; it does NOT touch the old file
- [x] 3.4 `service start` runs `launchctl bootstrap gui/$(id -u) <plist>` for both labels, falling back to `launchctl load` on macOS versions where `bootstrap` is unavailable
- [x] 3.5 `service stop` runs `launchctl bootout gui/$(id -u)/<label>` (or `launchctl unload`) for both labels
- [x] 3.6 `service uninstall` calls `service stop` first, then removes both plist files
- [x] 3.7 `service status` shells out to `launchctl print gui/$(id -u)/<label>` for each label and renders one line per component with one of: `not-installed`, `installed-but-not-loaded`, `loaded-and-running`, `loaded-but-crashing`

## 4. Scope entrypoint alignment

- [x] 4.1 Add a `__main__.py` (or equivalent `python -m` target) under `scope/api/` so `python -m scope.api` starts the Scope server identically to running `scope_api.py`
- [x] 4.2 Keep top-level `scope_api.py` as a thin 3-line shim that calls into the new `python -m` target; do NOT delete it in this change
- [x] 4.3 Verify `scope/api/server.py` binds `127.0.0.1` only (no regression)

## 5. Deletions and deprecated aliases

- [x] 5.1 Delete top-level `monitor.py`
- [x] 5.2 Delete top-level `dashboard.py` (the one-shot HTML opener, not `focusmonitor/dashboard.py`)
- [x] 5.3 Retain `cli.py run` as a deprecated alias that prints `run is deprecated; use 'start' instead` on stderr and dispatches to `start`
- [x] 5.4 Retain `cli.py dashboard` as a deprecated alias that prints `dashboard is deprecated; use 'start pulse' instead` on stderr and dispatches to `start pulse`
- [x] 5.5 Grep the repo for remaining references to `monitor.py` and `dashboard.py` (as top-level scripts) and update them — tests, docs, comments, READMEs

## 6. `setup.py` changes

- [x] 6.1 Remove the `create_plist()` function and its call site in `setup.py`
- [x] 6.2 Update `setup.py`'s "Next steps" output to show `python3 <abs cli.py> start` as the foreground-test step and `python3 <abs cli.py> service install && python3 <abs cli.py> service start` as the background step
- [x] 6.3 Remove any `launchctl load`/`unload` commands from `setup.py`'s output
- [x] 6.4 Verify `setup.py` still runs on stock `/usr/bin/python3` with no dev-venv (import-path check)

## 7. README updates

- [x] 7.1 Update Quick Start step 4 from `python3 cli.py run` to `python3 cli.py start`
- [x] 7.2 Update Quick Start step 6 from raw `launchctl load` to `python3 cli.py service install && python3 cli.py service start`
- [x] 7.3 Update the "Verifying your install" section to curl both `:9876` and `:9877` (Pulse dashboard and Scope API)
- [x] 7.4 Add a new "Upgrading from the old launchd agent" section with the manual `launchctl bootout com.focusmonitor.agent` + `rm` + `service install` + `service start` recipe, including the respawn-loop warning
- [x] 7.5 Update the "How to wipe all your data" section to use `cli.py service uninstall` as the primary command, with raw launchctl commands for both new labels as a fallback
- [x] 7.6 Update all references to `python3 cli.py run` elsewhere in the README to `python3 cli.py start`

## 8. Tests

- [x] 8.1 Add `tests/test_cli_start.py`: exercise `cli.py start` with a fake component that sleeps; assert both children are spawned, that `SIGINT` to the parent tears both down within the timeout, and that an unexpected child exit tears down the survivor
- [x] 8.2 Add `tests/test_service_install.py`: call the plist-generation helper from `focusmonitor/service.py` and snapshot-assert both plist contents byte-for-byte (using syrupy or `assert str == str`); the snapshot MUST NOT contain a hardcoded python path and MUST contain the shim path
- [x] 8.3 Add `tests/test_service_install.py::test_legacy_plist_warning`: create a fake `com.focusmonitor.agent.plist` in a tmp `LaunchAgents` dir and assert the CLI prints the upgrade warning and still writes the new plists
- [x] 8.4 Add `tests/test_shim.sh` (or a Python test that invokes the shim via `subprocess`): set up a fake `.venv/bin/python3` and assert the shim picks it; unset it and assert the fallback order resolves correctly; grep the shim for forbidden network calls (`curl`, `wget`, `nc`, `ssh`, `http://`, `https://`)
- [x] 8.5 Delete any existing test that imports `monitor.py` or top-level `dashboard.py` as an entry point; replace with `cli.py` equivalents
- [x] 8.6 Update `tests/test_install_flow.py` (or equivalent) to assert `setup.py` no longer creates a plist on disk
- [x] 8.7 Run the full suite offline: `.venv/bin/pytest tests/` — must pass with `pytest-socket` enabled

## 9. Privacy review

- [x] 9.1 Run the `privacy-review` skill over the full diff, with particular attention to: the new shim, the two new plist templates, any new subprocess calls, and the deletion of old scripts
- [x] 9.2 Manually grep the shim and `focusmonitor/service.py` for non-loopback patterns: `https?://`, `0\.0\.0\.0`, `curl`, `wget`, `nc `, `ssh`
- [ ] 9.3 After `service install` + `service start` on a real machine, run `lsof -iTCP -sTCP:LISTEN -P -n | grep -E 'python|focusmonitor'` and confirm every listening socket is bound to `127.0.0.1`

## 10. Manual acceptance

- [ ] 10.1 Fresh-clone smoke test: clone the repo into a scratch directory, run `python3 cli.py setup`, then `python3 cli.py start`, verify dashboard at `http://localhost:9876` and Scope at `http://localhost:9877`, Ctrl-C, verify both children exit
- [ ] 10.2 Background smoke test: `python3 cli.py service install && python3 cli.py service start`, verify both services report `loaded-and-running` via `service status`, kill the Scope process with `kill -9` and verify launchd respawns only Scope (Pulse PID unchanged)
- [ ] 10.3 Legacy-plist upgrade test: on a machine that still has `com.focusmonitor.agent` loaded, pull this change, run `python3 cli.py service install`, verify the warning appears, manually run the documented `bootout` + `rm` + `service start` sequence, verify the old label is gone and both new labels are running
- [ ] 10.4 Python-swap test: rename `/opt/homebrew/bin/python3` temporarily, run `launchctl kickstart` on the Pulse service, verify the shim's stderr line in `~/.focus-monitor/logs/pulse.err.log` shows the fallback interpreter path
