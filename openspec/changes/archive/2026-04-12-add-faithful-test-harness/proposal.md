## Why

The current tests are hand-rolled scripts with a global `passed/failed` counter and no framework. They cover ~half the package, but the modules that talk to external services (`ollama.py`, `activitywatch.py`) have zero tests — precisely the code most likely to silently break when a model version, prompt, or upstream schema shifts. Existing tests also lean on substring assertions and manual path-patching, so they pass in ways that don't guarantee the real behaviour still works. We need tests that are *faithful* — when they pass, prod actually works; when they fail, the signal is real — and a framework that makes writing more of them cheap.

## What Changes

- Introduce pytest as the test runner, with discovery, fixtures, selection, and real assertion diffs.
- Add `pytest-recording` (vcrpy) to record real HTTP responses from local Ollama and ActivityWatch into committed cassettes, then replay them offline on every run.
- Add `hypothesis` for property tests over `parse_analysis_json` and other fuzzable parsers.
- Add `syrupy` for full-HTML snapshot tests of `dashboard.py` rendering (not substring checks).
- Add `coverage.py` for honest reporting of what tests do and do not touch.
- Add `pytest-socket` to enforce that test runs cannot talk to anything outside `localhost` — making the offline-at-runtime invariant a hard guard, not a convention.
- Dev deps live in a local `.venv` via a committed `requirements-dev.txt`. One-time online install; offline thereafter.
- Add a `conftest.py` that redirects `~/.focus-monitor/` into a `tmp_path` for every test, eliminating the module-global path-patching pattern.
- Pilot the new pattern by rewriting `test_analysis.py` (hypothesis on the parser), then add cassette-backed tests for `ollama.py`, then `activitywatch.py`, then snapshot tests for `dashboard.py`, then convert the remaining `test_*.py` files.
- Update `.claude/skills/test-focusmonitor/SKILL.md` to run `pytest` and document the cassette re-record workflow. Update `CLAUDE.md` to reflect the dev-venv story and the offline-at-runtime hard rule.
- **BREAKING** for contributors only: `python3 test_*.py` direct execution is retired. Tests run via `pytest` inside the dev venv.

## Capabilities

### New Capabilities
- `test-harness`: faithful, offline-by-default automated testing of focus-monitor. Covers test runner, fixture layout, HTTP record/replay, property testing, snapshot testing, coverage reporting, and the socket-blocking runtime invariant.

### Modified Capabilities
<!-- None. No product behaviour changes; this is tooling only. -->

## Impact

- **Code:** adds `tests/` directory (cassettes, snapshots, fixtures, conftest). Existing `test_*.py` files at repo root get rewritten and moved under `tests/`. No `focusmonitor/` source changes are required by the harness itself, though porting may surface small testability seams.
- **Dependencies:** new dev-only deps in `requirements-dev.txt` — `pytest`, `pytest-recording`, `pytest-socket`, `hypothesis`, `syrupy`, `coverage`, `freezegun`. None are runtime deps; `focusmonitor/` continues to run on stdlib + existing runtime deps.
- **Tooling:** `.claude/skills/test-focusmonitor/SKILL.md` rewritten to invoke pytest. `CLAUDE.md` updated with dev-venv and offline-at-runtime rules. `.gitignore` updated for `.venv/` and coverage artifacts.
- **Ops:** developers must create the `.venv` and run `pip install -r requirements-dev.txt` once. Cassettes are committed so subsequent clones need no capture step.

## Privacy impact

This change introduces *two* network events, both scoped and visible:

1. **One-time dev install.** `pip install -r requirements-dev.txt` into `.venv` talks to PyPI. This is a developer-machine action, not a runtime action — focus-monitor itself never invokes pip. The `block-network.sh` hook will fire and the developer must explicitly approve. No user of focus-monitor is affected; no data leaves the machine as a result of this step.
2. **Cassette capture against local services.** Recording cassettes talks only to `localhost:11434` (Ollama) and `localhost:5600` (ActivityWatch). These are already-permitted hosts under the existing network policy. Captured cassettes contain the exact bytes sent to and received from local services; developers must review cassettes before committing to confirm they contain no user-identifying content from their own `~/.focus-monitor/` data. A cassette-review note goes into `CLAUDE.md` and the new capability spec.

**At runtime** — i.e., when a user runs `pytest` after install — the harness is *strictly more* privacy-preserving than the current state: `pytest-socket` blocks all non-loopback sockets for the duration of the test run. If any test inadvertently reaches out, the run fails loudly instead of silently phoning home. The localhost-only invariant is upgraded from a policy to an enforced property.

No telemetry, no auto-update, no cloud LLM calls, no MCP servers are introduced. The `.mcp.json` remains empty. The existing `block-network.sh` hook remains in place and unchanged.
