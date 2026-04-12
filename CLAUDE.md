# focus-monitor — agent instructions

This file is loaded into every Claude Code session in this repo. Keep it tight and
focused on invariants that rarely change. Per-file documentation belongs in code
comments, not here.

## What this project is

A local, privacy-first AI productivity tracker for macOS. It watches your activity
via ActivityWatch, takes periodic screenshots, and asks a locally-running Ollama
model (`llava` by default) to classify the activity against your planned tasks.

Everything runs on the user's Mac. **No data leaves the machine.** This is the
entire product promise — treat it as a hard invariant, not a nice-to-have.

## Platform & runtime

- **Target:** macOS on Apple Silicon (M1/M2/M4). Do not add x86-only assumptions.
- **Python:** 3.10+ floor. Prefer standard-library solutions before reaching for
  third-party packages.
- **External runtime deps:** ActivityWatch and Ollama, both running on localhost.
  Anything else that wants to bind to a non-loopback address needs an explicit
  design discussion first.

## Where things live

- `focusmonitor/` — importable package. Modules split by concern:
  `activitywatch.py`, `analysis.py`, `cleanup.py`, `config.py`, `dashboard.py`,
  `db.py`, `main.py`, `nudges.py`, `ollama.py`, `screenshots.py`, `tasks.py`.
- `monitor.py`, `dashboard.py`, `cli.py`, `setup.py` — top-level entrypoints.
- `test_*.py` at the repo root — tests run directly via `python3 <file>`. There is
  no pytest, no unittest discovery, no test framework. If you want to add one,
  propose it as an openspec change first.
- `~/.focus-monitor/` — user data: `config.json`, `planned_tasks.txt`, the
  SQLite DB, the screenshot cache. Never hardcode this path; read it from
  `focusmonitor.config`.

## Network policy (the important part)

Only `localhost` and `127.0.0.1` may be contacted. That means:

- ActivityWatch on `http://localhost:5600/` — OK.
- Ollama on `http://127.0.0.1:11434/` (or via the `ollama` CLI) — OK.
- **Anything else — not OK**, including package installs, telemetry, auto-update
  checks, error reporting, cloud LLM calls, and "just pulling down a quick
  dependency." If a task seems to require one, stop and ask.

`.claude/settings.json` wires a `PreToolUse` hook
(`.claude/hooks/block-network.sh`) that blocks `Bash` commands matching
outbound-network patterns. The hook is a safety net, **not** a security boundary:
regex cannot catch every exfiltration vector. The primary enforcement is this
policy; the hook just makes mistakes loud.

If you have a genuinely legitimate one-off external call (e.g., reading upstream
documentation during exploration), say so explicitly in chat before attempting
the command, and ask the user to approve the tool call when the hook blocks it.

`.mcp.json` at the repo root is intentionally empty (`{"mcpServers": {}}`) for
the same reason: MCP servers can reach the network, and adding one silently
would defeat the privacy invariant. To add an MCP server, update this file
*and* add a "Privacy impact" section to the openspec proposal that introduces
it.

## Project-local skills

Two skills live under `.claude/skills/` and should be used where they fit:

- `privacy-review` — before committing a change, run this over the diff to
  catch privacy regressions (non-localhost URLs, new outbound-HTTP imports,
  weaker screenshot retention, 127.0.0.1 rebinds).
- `test-focusmonitor` — runs the `test_*.py` files at the repo root.

Everything else should go through base Claude behavior. Don't add more skills
unless the workflow is genuinely unique to this repo.

## Style

- Small, surgical edits. This codebase is single-developer and deliberately
  small — resist the urge to refactor surrounding code while fixing something.
- No docstrings on every function. Comments only where the *why* is non-obvious.
- Prefer explicit over clever. Prefer standard library over a new dependency.
- Privacy invariants beat ergonomics when they conflict.
