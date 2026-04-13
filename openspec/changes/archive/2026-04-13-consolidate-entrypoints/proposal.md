## Why

The repo has accumulated four top-level scripts (`cli.py`, `monitor.py`, `dashboard.py`, `scope_api.py`) plus a `setup.py` that writes a single launchd plist pointing at `monitor.py`. There is no unified way to start Pulse + Scope together, Scope is entirely absent from the boot path even though it is meant to always run, and the distinction between foreground (dev) and background (service) is managed by the user via raw `launchctl` commands. The launchd plist also pins `which python3` at install time, which silently strands the service on a stale interpreter after brew/pyenv changes.

## What Changes

- **BREAKING**: Delete `monitor.py` (6-line back-compat shim) and top-level `dashboard.py` (one-shot HTML snapshot opener, superseded by the live dashboard server). Existing launchd installs that target `monitor.py` by absolute path will break on upgrade — the manual migration step is documented in the README.
- Consolidate all entrypoints behind `cli.py` with new verbs:
  - `cli.py start [pulse|scope]` — run components in the foreground, attached to the terminal. With no component argument, starts both Pulse and Scope as child processes; Ctrl-C tears down both.
  - `cli.py stop [pulse|scope]` — stop running foreground children (no-op if nothing is running in this session).
  - `cli.py service install` — write two launchd plists (`com.focusmonitor.pulse`, `com.focusmonitor.scope`), one per component.
  - `cli.py service uninstall` — remove both plists.
  - `cli.py service start|stop|status` — `launchctl kickstart`/`bootout`/status both jobs.
  - `cli.py setup` — unchanged semantics (probes + scaffold), but no longer writes the plist directly; instead prints "run `cli.py service install` when you are ready".
- Retain `cli.py dashboard` and `cli.py run` as deprecated aliases for one release: `dashboard` maps to `start pulse` (since the dashboard is embedded in Pulse), `run` maps to `start`. Both print a one-line deprecation notice.
- Scope gains a first-class boot path. `scope_api.py` stays as a thin `python -m`-style entrypoint the plist can target, but day-to-day users invoke it through `cli.py start scope`.
- Fix the launchd Python-resolution problem: `service install` writes a small shell shim at `bin/focusmonitor-service` (or equivalent) that resolves python at invocation time (preferring a project `.venv` if present, otherwise `command -v python3`). The plists target the shim, not a hardcoded python path. Re-running `service install` is the supported way to re-pin.
- README and `setup.py` output update to document the new verbs and the manual upgrade path for users with the old `com.focusmonitor.agent` plist installed.

## Capabilities

### New Capabilities

- `service-supervision`: Launchd service management — installing, starting, stopping, and uninstalling per-component launchd plists for Pulse and Scope, plus the Python-resolution shim that keeps the service portable across interpreter changes.

### Modified Capabilities

- `cli-entrypoint`: The verb surface changes from `run`/`dashboard`/`setup` to `start`/`stop`/`service`/`setup`, with `start` defaulting to both Pulse and Scope and handling foreground child-process supervision (Ctrl-C propagates). `run` and `dashboard` become deprecated aliases.
- `install-flow`: `setup.py` no longer writes the launchd plist as a side effect of setup. The plist-writing moves to `cli.py service install`, and setup's "Next steps" output points at the new verb. The README Quick Start updates accordingly.

## Impact

- **Affected code**: `cli.py` (new verbs + child-process supervision), `setup.py` (stop writing plist), `monitor.py` (deleted), top-level `dashboard.py` (deleted), new `bin/focusmonitor-service` shim (new file, shell script), `README.md` (Quick Start + wipe-all-data instructions).
- **Affected specs**: `cli-entrypoint` (modified), `install-flow` (modified), `service-supervision` (new).
- **Tests**: new coverage for `cli.py start` child-process teardown on Ctrl-C, for `service install` plist generation (asserts the shim path, not a hardcoded python), and for the shim's python-resolution order. `focusmonitor.install` probes are unchanged.
- **Privacy**: no new network calls, no new dependencies, no change to the localhost-only invariant. All new code is stdlib + shell. The two new plists bind the same loopback services (Pulse dashboard on `:9876`, Scope API on `:9877`) — no new listening surfaces.
- **Runtime dependencies**: none added. Shell shim is POSIX sh, no bashisms.
- **Upgrade path for existing installs**: manual. Users with `com.focusmonitor.agent` loaded run `launchctl unload ~/Library/LaunchAgents/com.focusmonitor.agent.plist && rm ~/Library/LaunchAgents/com.focusmonitor.agent.plist`, then `python3 cli.py service install && python3 cli.py service start`. Documented in the README under a new "Upgrading" section.
