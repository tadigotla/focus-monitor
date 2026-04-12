## Why

A new user on a fresh Mac cannot follow the README's Quick Start end-to-end without hitting silent gaps: prerequisites (Ollama install, Ollama daemon running, pulling `llama3.2-vision` ~7.8 GB, installing + starting ActivityWatch) are *listed* in Requirements but have no runnable commands in the install flow. The Screen Recording permission note lives below the code block instead of inline where it matters. `setup.py` checks that Ollama and ActivityWatch *binaries* exist but not whether their *daemons* are actually up — so a user with Ollama installed but not running gets a green setup followed by a silent failure on the first analysis tick. And `setup.py`'s printed "Next steps" still references a `planned_tasks.txt` path that the code hasn't scaffolded since the JSON migration landed. The tool works fine once set up; the onboarding just lies a little at every step.

## What Changes

- Rewrite the README "Quick Start" to lead with an executable prerequisites block: `brew install ollama`, start Ollama daemon, `ollama pull llama3.2-vision`, install + start ActivityWatch, grant Screen Recording permission. Every step a copy-pasteable command.
- Move the Screen Recording permission callout from an afterthought below the code block to an explicit step in the install sequence.
- Add live-daemon health checks to `setup.py`:
  - Probe `http://127.0.0.1:11434/api/tags` (Ollama) and report running / not-running / binary-present-but-daemon-down with a fix command.
  - Probe `http://127.0.0.1:5600/api/0/info` (ActivityWatch) with the same pattern.
  - Both probes use stdlib `urllib.request` against localhost only — no new deps, no new network reach.
- Fix `setup.py`'s "Next steps" output to say `planned_tasks.json` (matching what `load_config()` actually writes) and point at `cli.py` with the correct resolved path.
- Add a documented "verifying your install" section to the README that a user can run after setup to confirm the full pipeline works: check Ollama reachable, check AW reachable, run `cli.py run` for one analysis tick, confirm a row lands in `~/.focus-monitor/activity.db`.
- **No product behaviour changes.** No runtime dependency changes. No network-policy changes — every new probe targets loopback. No test-harness changes.

## Capabilities

### New Capabilities
- `install-flow`: the fresh-install user journey. Covers README Quick Start completeness, `setup.py` preflight contract (what it checks, what it reports, what it scaffolds), and the self-verify recipe. Owns the invariant that a new user following the documented steps in order lands at a working install with no silent gaps.

### Modified Capabilities
<!-- None. cli-entrypoint still owns the `cli.py` subcommand surface; this change only touches setup.py's preflight + README, not the CLI contract. -->

## Impact

- **Docs:** `README.md` — Quick Start block rewritten; Screen Recording permission moved inline; new "Verifying your install" section; no other structural changes.
- **Code:** `setup.py` — add two small localhost probe helpers (~30 lines); fix the stale `planned_tasks.txt` string to `planned_tasks.json`; fix the resolved path in the "Next steps" message. No new imports beyond `urllib.request` / `urllib.error` (both stdlib).
- **Specs:** new `openspec/specs/install-flow/spec.md` with requirements covering README completeness, setup.py preflight, and the self-verify path.
- **Tests:** `tests/test_install_flow.py` covers the new `setup.py` probe helpers — success, daemon-down, binary-missing — using `monkeypatch` on `urllib.request.urlopen` and `subprocess.run`. No cassettes needed: these are deterministic unit tests of the preflight logic, and the tests never talk to real services.
- **Runtime behaviour:** unchanged. The monitor itself doesn't know or care whether `setup.py` performed these checks. A user who skips `setup.py` entirely still gets a working install if they follow the README.

## Privacy impact

None. Every new network call (`urllib.request.urlopen` against `http://127.0.0.1:11434` and `http://127.0.0.1:5600`) targets the already-permitted loopback services. No new hosts, no new dependencies, no new data collected. The probes request public `/api/tags` and `/api/0/info` endpoints that return only version/model-list metadata, not user content. The existing `block-network.sh` hook will not fire on any of these calls. `.mcp.json` remains empty.
