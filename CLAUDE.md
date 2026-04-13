# focus-monitor — agent instructions

This file is loaded into every Claude Code session in this repo. Keep it tight and
focused on invariants that rarely change. Per-file documentation belongs in code
comments, not here.

## What this project is

A local, privacy-first AI productivity tracker for macOS. It watches your activity
via ActivityWatch, takes periodic screenshots, and asks a locally-running Ollama
model (`llama3.2-vision` by default) to classify the activity against your planned tasks.

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
  `activitywatch.py`, `analysis.py`, `cleanup.py`, `config.py`, `corrections.py`,
  `dashboard.py`, `db.py`, `install.py`, `main.py`, `nudges.py`, `ollama.py`,
  `screenshots.py`, `sessions.py`, `tasks.py`.
- `focusmonitor/static/` — vendored browser assets (htmx). Served locally
  because the no-CDN network policy forbids loading scripts from the internet.
  `PROVENANCE.md` tracks origin, version, and SHA256 for each file.
- `monitor.py`, `dashboard.py`, `cli.py`, `setup.py` — top-level entrypoints.
- `tests/` — pytest suite. Subdirectory layout:
  - `tests/test_*.py` — test files (pytest discovers these)
  - `tests/conftest.py` — `tmp_home`, `freeze_clock`, `pytest-socket` guard
  - `tests/fixtures/` — reusable fixtures (db, ollama, activitywatch)
  - `tests/cassettes/{ollama,activitywatch}/` — committed vcrpy cassettes
  - `tests/__snapshots__/` — committed syrupy dashboard HTML snapshots
  - `tests/data/` — deterministic PNG and task fixtures
- `scripts/seed_aw_fixture_buckets.py` — seeds the testing aw-server
  (`--testing` mode on `:5666`) with deterministic fixture buckets; used
  only during cassette re-records.
- `~/.focus-monitor/` — user data: `config.json`, `planned_tasks.txt`, the
  SQLite DB, the screenshot cache. Never hardcode this path; read it from
  `focusmonitor.config`. Tests **never** touch the real dir — the
  `tmp_home` fixture in `tests/conftest.py` redirects every config path
  into a per-test `tmp_path`.

## Tests and dev environment

Tests run via pytest inside a local `.venv`. First-time setup (one-time
online install, developer-machine action only — never invoked by
runtime):

```
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

Day-to-day:

```
.venv/bin/pytest tests/
```

Hard rules:

- **Offline-at-runtime is enforced, not a convention.** `pytest-socket`
  is wired via `pyproject.toml` with `--disable-socket` +
  `--allow-hosts=127.0.0.1,localhost,::1`. Any test that inadvertently
  reaches a non-loopback host fails loudly with
  `SocketConnectBlockedError`. `tests/conftest.py` also guards against
  accidental removal of the flag.
- **`focusmonitor/` runtime code imports nothing from `requirements-dev.txt`.**
  Dev deps (pytest, vcrpy, hypothesis, syrupy, freezegun, coverage,
  pytest-socket) are dev-only. The "prefer stdlib" default still applies
  to runtime code; the pytest ecosystem is the tooling-layer exception.
- **Cassette-backed tests replay from committed fixtures.** `tests/cassettes/`
  holds real HTTP recordings from local Ollama and a testing ActivityWatch
  instance. A fresh clone runs the full suite offline after install — no
  capture step required.
- **Re-recording cassettes is an explicit sub-workflow**, not a default.
  Trigger only when bumping the Ollama model, upgrading ActivityWatch,
  or investigating an upstream-drift failure. See
  `.claude/skills/test-focusmonitor/SKILL.md` for the step-by-step flow.
- **Cassettes must never contain personal data.** Ollama cassettes are
  captured against the PNG fixtures under `tests/data/screenshots/`.
  ActivityWatch cassettes are captured against `aw-server --testing`
  (port 5666, isolated database) seeded from `scripts/seed_aw_fixture_buckets.py`
  — never against production AW. Privacy-review every new cassette diff
  before committing.
- **Dashboard snapshots are full-page HTML.** `syrupy` asserts that
  `build_dashboard()` output is byte-identical to
  `tests/__snapshots__/test_dashboard.ambr`. Update with
  `pytest --snapshot-update` only when you've intentionally changed the
  template, and include the snapshot diff in the same PR as the change.

## Network policy (the important part)

Only `localhost` and `127.0.0.1` may be contacted. That means:

- ActivityWatch on `http://localhost:5600/` (production) or
  `http://localhost:5666/` (`aw-server --testing`) — OK.
- Ollama on `http://127.0.0.1:11434/` (or via the `ollama` CLI) — OK.
- **Anything else — not OK**, including package installs, telemetry, auto-update
  checks, error reporting, cloud LLM calls, and "just pulling down a quick
  dependency." If a task seems to require one, stop and ask.

There is **one documented exception**: the one-time dev-venv install
(`pip install -r requirements-dev.txt`) pulls from PyPI. This is a
developer-machine setup action, never invoked by focus-monitor itself,
and after it completes every test run is strictly offline (enforced by
`pytest-socket`). Treat it as a privacy-reviewable event: approve the
hook prompt explicitly, expect it exactly once per clone, never script
it.

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

## Scope — AI Decision Inspector

Scope is a companion subsystem for inspecting and learning from the AI's
decision-making. It is **not** part of the Pulse runtime — Pulse never imports
from Scope, and Scope only reads from the shared SQLite DB.

**Naming convention:**
- **Pulse** — the main focus-monitor system (`focusmonitor/`)
- **Scope** — the learning companion (`scope/`)

**Where things live:**
- `scope/api/` — Python read-only JSON API server (stdlib `http.server`)
- `scope/ui/` — React + Vite frontend (planned, Phase 3+)
- `scope_api.py` — top-level entrypoint for the API server

**Coupling boundary:**
- Pulse writes to `analysis_traces` and the existing tables. Scope reads them.
- Scope never writes to the DB. If Scope crashes, Pulse doesn't notice.
- The Scope API binds to `127.0.0.1:9877` (configurable via `scope_api_port`).

**Dev setup for Scope UI (one-time, same class as pip install):**
```
cd scope/ui && npm install
```
This is a developer-machine action that pulls from npm. It is **not** a
runtime dependency and is never invoked by Pulse. `scope/ui/node_modules/`
and `scope/ui/dist/` are in `.gitignore`.

## OpenSpec workflow

Changes to the project follow a structured propose → design → implement →
archive flow driven by the `openspec` CLI. Configuration lives in
`openspec/config.yaml`; completed changes are date-stamped and moved to
`openspec/changes/archive/`.

If you don't have the CLI installed, set it up with:

```
npm install -g @fission-ai/openspec
```

This is a one-time developer-machine install (similar to the pip venv
setup). It is **not** a runtime dependency and is never invoked by
focus-monitor itself.

## Project-local skills

Skills under `.claude/skills/`:

- `privacy-review` — before committing a change, run this over the diff to
  catch privacy regressions (non-localhost URLs, new outbound-HTTP imports,
  weaker screenshot retention, 127.0.0.1 rebinds).
- `test-focusmonitor` — runs the pytest suite inside `.venv` and reports
  results. Also hosts the cassette re-record sub-workflow for Ollama and
  ActivityWatch, with step-by-step privacy-review instructions.

Skills under `.github/skills/` (OpenSpec workflow):

- `openspec-propose` — scaffold a new change with proposal, design, and tasks.
- `openspec-apply-change` — implement tasks from an existing change.
- `openspec-archive-change` — archive a completed change.
- `openspec-explore` — thinking-partner mode for exploring ideas before or
  during a change.

Don't add more skills unless the workflow is genuinely unique to this repo.

## Style

- Small, surgical edits. This codebase is single-developer and deliberately
  small — resist the urge to refactor surrounding code while fixing something.
- No docstrings on every function. Comments only where the *why* is non-obvious.
- Prefer explicit over clever. Prefer standard library over a new dependency.
- Privacy invariants beat ergonomics when they conflict.
