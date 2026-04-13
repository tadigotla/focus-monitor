## Context

Today the repo has four top-level Python entrypoints:

```
cli.py         — run | dashboard | setup         (unified CLI, Scope-unaware)
monitor.py     — 6-line shim → focusmonitor.main  (plist targets this)
dashboard.py   — build_dashboard() → temp HTML → browser (one-shot, not a server)
scope_api.py   — starts Scope API on :9877       (no CLI integration, no plist)
setup.py       — probes + writes a single launchd plist pointing at monitor.py
```

Pulse (the monitor + embedded dashboard HTTP server at `focusmonitor/main.py`) and Scope (the read-only JSON API at `scope/api/server.py`) are independent processes that share the SQLite DB at `~/.focus-monitor/activity.db`. CLAUDE.md already pins the coupling boundary: **Pulse never imports from Scope, and Scope only reads from the DB**. This change does not touch that boundary — it only consolidates how the two processes get started.

The launchd plist that `setup.py` writes pins `which python3` at install time, which silently strands the service on a stale interpreter after brew/pyenv changes. Scope is entirely absent from the boot path.

Constraints: macOS + Apple Silicon only. Python 3.10+ stdlib only for runtime code. No non-loopback network. No new runtime dependencies. Dev venv exists but is not load-bearing for the service.

## Goals / Non-Goals

**Goals:**
- One CLI (`cli.py`) with `start`/`stop`/`service`/`setup` verbs.
- `start` with no args runs Pulse + Scope in the foreground, attached to the terminal, with Ctrl-C tearing down both.
- `service install` writes two launchd plists (one per component) so launchd supervises each independently with its own KeepAlive and restart behaviour.
- The launchd plists target a small shell shim that re-resolves Python at every invocation, so brew/pyenv changes do not strand the service.
- Delete `monitor.py` and top-level `dashboard.py`; their uses are fully subsumed.

**Non-Goals:**
- No change to Pulse's internal loop, analysis cadence, or dashboard HTTP server.
- No change to Scope's API surface or DB read-only guarantee.
- No automatic migration from the old `com.focusmonitor.agent` plist — the upgrade is a documented manual step (user explicitly confirmed this).
- No cross-platform support. Everything is macOS + launchd. No systemd, no Windows.
- No process supervisor in Python. Launchd is the supervisor for background mode; the tty session group is the supervisor for foreground mode.
- No daemonisation inside Python. "Background" means "managed by launchd", not "fork + setsid".
- No `$PATH` installation (`focusmonitor` as a bare command). Users still invoke `python3 cli.py`. That is a separate ergonomic improvement for another change.

## Decisions

### Decision 1: Two plists, not one supervisor

`service install` writes two independent launchd plists:

```
com.focusmonitor.pulse    ProgramArguments → [shim, "start", "pulse", "--service"]
com.focusmonitor.scope    ProgramArguments → [shim, "start", "scope", "--service"]
```

Each has `RunAtLoad=true`, `KeepAlive=true`, and its own stdout/stderr under `~/.focus-monitor/logs/pulse.{out,err}.log` and `~/.focus-monitor/logs/scope.{out,err}.log`.

**Alternative considered**: a single `com.focusmonitor.agent` plist that runs a Python supervisor which itself spawns Pulse and Scope as children. **Rejected** because it reimplements launchd in Python for no gain — launchd already handles crash-restart, logging, and boot-time startup. Two plists also means an independent restart of one component doesn't bounce the other. The only cost is one extra file; `service install` writes both in one call so the user never sees the plurality unless they look in `~/Library/LaunchAgents/`.

### Decision 2: The shim re-resolves Python at invocation

`bin/focusmonitor-service` is a ~20-line POSIX shell script that:
1. Computes `REPO_ROOT` from its own location (`dirname $0/..`).
2. Prefers `$REPO_ROOT/.venv/bin/python3` if it exists and is executable.
3. Otherwise uses `command -v python3` against launchd's minimal PATH, falling back to `/usr/bin/python3` and then `/opt/homebrew/bin/python3` in that order.
4. `exec`s the resolved interpreter with `$REPO_ROOT/cli.py` and all forwarded arguments.

The plists put the shim path (absolute) in `ProgramArguments[0]`. Re-running `cli.py service install` is the supported way to re-pin the shim location after the repo is moved on disk.

**Alternative considered**: write the plist with `/usr/bin/env` + `python3`. **Rejected** because launchd hands the job a minimal environment and `/usr/bin/env python3` frequently finds a different interpreter than the user's interactive shell does, which is the exact class of bug we are trying to fix. The shim makes the resolution order explicit, greppable, and debuggable by hand.

**Alternative considered**: pin `.venv/bin/python3` unconditionally. **Rejected** because CLAUDE.md currently classifies the venv as dev-only. Making the venv load-bearing for the service would be a privacy-reviewable change to the project's install story, and it's independently undesirable (the service should run on stock Python 3.10+).

### Decision 3: Foreground `start` uses `subprocess.Popen`, not threads

`cli.py start` with no args forks two child processes:

```
           ┌────────────────────────────────┐
           │  cli.py start  (parent, tty)   │
           └───────────┬────────────────────┘
                       │
           ┌───────────┴────────────┐
           ▼                        ▼
    Popen("python3",         Popen("python3",
          "-m",                    "-m",
          "focusmonitor.main")     "scope.api.cli")
    (Pulse)                 (Scope)
```

The parent installs a `SIGINT`/`SIGTERM` handler that sends `SIGTERM` to both children, waits up to N seconds, then `SIGKILL`s any survivor. The parent's `wait()` loop exits when either child dies unexpectedly (it tears down the survivor and exits non-zero) or when the user Ctrl-Cs.

Child stdout/stderr are line-buffered and tagged with a prefix (`[pulse]` / `[scope]`) before being written to the parent's stdout, so the user sees interleaved logs in one terminal.

**Alternative considered**: run Scope as a thread inside the Pulse process, mirroring how the dashboard HTTP server is embedded today. **Rejected** because it would violate the Pulse↔Scope coupling boundary that CLAUDE.md pins: "Pulse never imports from Scope". Keeping them as sibling processes preserves that boundary and matches how they will run in background mode under launchd.

**Alternative considered**: use `os.execvp` to replace the cli.py process with one of the children when the user runs `start pulse` or `start scope`. **Accepted for the single-component case**. `cli.py start pulse` directly execs into `python -m focusmonitor.main` with no middleman; only the two-component default does the Popen dance.

### Decision 4: `service install` does not autoload; `service start` does

`service install` writes the plist files and nothing else. `service start` runs `launchctl bootstrap gui/$(id -u) <plist>` (or `load` on older macOS) to actually start them. This separates "commit the config" from "touch the running system", which matches the shape of `systemctl enable` vs `systemctl start` and makes the install step safe to re-run.

### Decision 5: Deprecated aliases stay for one release, then go

`cli.py run` prints `"run is deprecated; use 'start' instead"` on the first line of its output and then dispatches to `start` (both components). `cli.py dashboard` prints `"dashboard is deprecated; use 'start pulse' instead"` and dispatches to `start pulse`. Both are removed in a follow-up change after one release cycle.

The specs for `cli-entrypoint` are updated to reflect `start`/`stop`/`service` as the canonical surface; the deprecated aliases are documented in the spec under an explicit "Deprecated" requirement so nobody accidentally re-removes them before the grace period.

### Decision 6: Scope's CLI entrypoint is `python -m scope.api.cli`, not `scope_api.py`

Today `scope_api.py` is a thin top-level script. This change moves its contents into `scope/api/cli.py` (or similar — whichever path does not collide with existing modules) and keeps `scope_api.py` as a 3-line shim that calls it. This gives `cli.py start scope` a clean `python -m` target without hardcoding a file path relative to the repo root. `scope_api.py` follows `monitor.py` and top-level `dashboard.py` into the deletion list in a later change; for now it stays to avoid breaking anyone who invokes it directly.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| Existing installs that `launchctl load`ed `com.focusmonitor.agent` will continue running the old `monitor.py`, which no longer exists after this change. On the next monitor restart the plist will fail to exec and launchd will respawn-loop. | Documented manual upgrade step in the README. `setup.py` detects the presence of the old plist on next run and prints a loud warning with the exact `unload + rm + service install` sequence. |
| A user's `$REPO_ROOT/.venv/bin/python3` points at an interpreter that is missing a module the runtime needs. Today runtime is pure stdlib so this is theoretical, but the shim's venv preference makes it possible in the future. | The shim logs its resolution decision to stderr on every invocation (`resolved python=/path/to/python3`), so a launchd respawn-loop has a visible cause in `~/.focus-monitor/logs/*.err.log`. |
| Two plists means two KeepAlive loops; a bug in Scope that crashes it hard could respawn-loop forever without anyone noticing, because Pulse looks healthy. | `cli.py service status` surfaces per-component state from `launchctl print`, and the README's "Verifying your install" section grows a line that checks both services. |
| Foreground `start` interleaves stdout from two children, which can garble if either child writes partial lines. | Log prefixing is applied line-by-line (readline loop), not chunk-by-chunk; children are configured with `PYTHONUNBUFFERED=1` in their environment so flushes are predictable. |
| Privacy: the shim is a new shell script. Shell scripts are an exfiltration vector if an attacker can write to them. | The shim lives inside the repo checkout (not a world-writable path), is version-controlled, contains no network calls, and is reviewed as part of this change. No non-loopback URLs, no `curl`, no `ssh`, no `nc`. Privacy-review the shim diff before commit (same workflow as any other file in the repo). |
| Privacy: the two new plists add two new launchd-managed processes. Each binds to a loopback-only port (`:9876`, `:9877`). No new listening surface is introduced — the ports already existed under the old manual invocation. | The proposal's Impact section and the `service-supervision` spec both pin the loopback-only requirement. No action required beyond calling it out during privacy-review. |

## Migration Plan

1. Implement the new CLI verbs and the shim behind a branch.
2. Delete `monitor.py` and top-level `dashboard.py` in the same commit that updates `setup.py` to stop writing the plist.
3. Update the README Quick Start to use `cli.py service install && cli.py service start`. Add an "Upgrading from the old launchd plist" section with the manual unload-and-reinstall recipe.
4. Update tests: delete tests that exercise `monitor.py` / top-level `dashboard.py` as entry points, add tests for `cli.py start` child-process teardown and for plist generation (assert the shim path, not a hardcoded python interpreter).
5. Privacy-review the diff (new shim, new plists, deleted scripts).
6. No rollback plan beyond `git revert`. There is no persistent state that changes — the old `~/.focus-monitor/` contents remain bit-identical, and the SQLite DB is untouched.

## Open Questions

- Does `cli.py service status` need to distinguish "plist installed but not started" from "plist installed and started but crashing"? Probably yes — `launchctl print` gives us both, but the UX of how to render it is TBD. Treating this as an implementation detail in tasks.md, not a spec requirement.
- Should the shim live at `bin/focusmonitor-service` or at the repo root as `focusmonitor-service.sh`? The `bin/` convention is cleaner but adds a new directory. Defaulting to `bin/focusmonitor-service` unless review objects.
