## Context

focus-monitor has ~4.7k LOC of product code and ~2.2k LOC of hand-rolled tests. Tests are plain Python scripts at the repo root, each with a module-level `passed/failed` counter and a `test(name, condition)` helper. They share pain points:

- Path-patching of `focusmonitor.config` happens at import time, before the module under test is imported. This is brittle and leaks state between test files.
- Assertions are binary booleans — when one fails, you see `FAIL  <name>` with no diff and no context.
- No selection, no fixtures, no setup/teardown, no discovery.
- External integrations (`ollama.py`, `activitywatch.py`) have zero tests. These are the most change-prone surfaces in the codebase — model versions shift, upstream schemas drift — and the current pattern offers no cheap way to test them.

The user explicitly asked for *faithful* tests — tests that reflect real service behaviour, not mocks that encode what we think the service returns. The user also confirmed that relaxing the network policy during development (one-time online install, occasional cassette recording against local services) is acceptable. The runtime invariant — no data leaves the machine — is non-negotiable and should be *strengthened* by this change, not weakened.

## Goals / Non-Goals

**Goals:**
- Every test run is offline. Enforced by `pytest-socket`, not convention.
- External-service behaviour is captured from the real service and replayed byte-for-byte.
- Parsers that eat messy input (`parse_analysis_json`) are tested against generated inputs, not hand-picked ones.
- Dashboard rendering is snapshot-tested end-to-end against a committed golden file, not substring-checked.
- Per-test isolation of `~/.focus-monitor/` via a single fixture; no more module-global path patching.
- New tests are cheap to write — the cost of adding coverage drops so that future changes actually get tested.
- Coverage is reported, not enforced as a vanity metric.
- The `.claude/skills/test-focusmonitor` skill and `CLAUDE.md` are updated to reflect the new workflow.

**Non-Goals:**
- Not adding runtime dependencies. `focusmonitor/` continues to run on stdlib + existing runtime deps.
- Not introducing CI. This remains a single-developer repo; CI is a separate decision.
- Not chasing 100% line coverage. "Essential" coverage means: every public function in external-integration modules has at least one faithful test; every parser has a property test; dashboard has a snapshot; existing coverage for `tasks.py`, `cleanup.py`, `analysis.py` is preserved and formalised.
- Not refactoring product code to be "more testable." Small testability seams are fine; sweeping rewrites are out of scope.
- Not testing the `llava` vision output semantically. We test that the client sends correct requests and parses real responses; we do not assert that `llava` classifies screenshots correctly — that is a model-quality question, not a harness question.
- Not introducing a typechecker, linter, or formatter as part of this change.

## Decisions

### 1. Runner: pytest, not unittest

**Choice:** pytest.

**Alternatives considered:** stdlib `unittest` (aligned with CLAUDE.md's "prefer stdlib" leaning); continue hand-rolled.

**Why pytest:**
- Assertion rewriting gives real diffs on failure — critical for snapshot and cassette tests, where failures are rich data structures, not booleans.
- Fixture composition is the mechanism that kills the repo's current path-patching pain. A single `conftest.py` fixture redirects `~/.focus-monitor/` per-test; every test inherits it for free.
- The record/replay and snapshot ecosystems we need (pytest-recording, syrupy, pytest-socket) are pytest-native. Rebuilding them on top of `unittest` is busywork.
- The user-level rule "prefer stdlib" in CLAUDE.md is a *default*, not a hard rule; the user confirmed they're comfortable breaking it when the ergonomics materially improve faithfulness. This qualifies.

### 2. HTTP record/replay: pytest-recording (vcrpy), cassettes committed to the repo

**Choice:** `pytest-recording` with cassettes under `tests/cassettes/`, committed to git.

**Alternatives considered:**
- Hand-written fake HTTP servers (`http.server` subclass) — rejected; they encode what we *think* the service returns, which is exactly the unfaithfulness we're trying to eliminate.
- `responses` / `respx` mock libraries — same problem; mocks, not recordings.
- Cassettes stored outside git in `~/.focus-monitor/test-cache/` — rejected; a fresh clone would fail until someone ran a capture step. Committed cassettes give "clone + install + pytest = green."

**Why this works:** cassettes are the actual bytes Ollama and ActivityWatch emitted on the day of capture. If the upstream shape changes, a re-record diff will make the change visible in the PR, and any code that depended on the old shape will fail loudly.

**Re-record policy:** `pytest --record-mode=rewrite` on demand, triggered by (a) bumping the `llava` model version, (b) upgrading ActivityWatch, (c) any test that starts failing for a reason suspected to be upstream drift. Re-records produce reviewable diffs in `tests/cassettes/`.

**Cassette review rule:** before committing a newly-recorded cassette, the developer must inspect it for user-identifying content from their own `~/.focus-monitor/`. Cassettes should be captured against a deterministic fixture corpus (a small set of canned screenshots + a known task list), not live user data. This rule goes into the spec and `CLAUDE.md`.

### 3. Property testing: hypothesis, scoped to parsers

**Choice:** `hypothesis`, used narrowly on functions whose job is to tolerate arbitrary input.

**Why:** `parse_analysis_json` is explicitly designed to handle garbage LLM output (see `feedback_llm_json_parsing.md` memory). Hand-picked inputs will never cover that surface. Hypothesis generates thousands of inputs per run and shrinks failures to minimal reproducers.

**Scope:** `parse_analysis_json`, `validate_analysis_result`, any future parser. Not used for business-logic tests where the input space is small and well-understood.

### 4. Snapshot testing: syrupy, full HTML

**Choice:** `syrupy`, snapshot of the full rendered dashboard HTML against `tests/__snapshots__/`.

**Alternatives considered:** `pytest-golden` (looser format); keep current substring-based structural tests.

**Why syrupy:** pytest-native, JSON/HTML-aware snapshots, single `--snapshot-update` flag to re-accept. Substring tests in `test_dashboard_render.py` assert a few keywords and miss entire page regressions. A full-page snapshot catches everything — a broken template tag, a missing CSS class, a malformed section — in a single diff.

**Stability:** snapshots must be deterministic. The dashboard currently renders timestamps and possibly computed hashes. The conftest will freeze time (`freezegun`) and seed the test DB with a fixed corpus so the rendered HTML is byte-stable across runs.

### 5. Offline enforcement: pytest-socket

**Choice:** `pytest-socket` enabled via `conftest.py`, with `allow_hosts=["127.0.0.1", "localhost"]`.

**Why:** the network policy has always been a policy. The `block-network.sh` hook is a safety net for `Bash` tool calls. Neither catches a test that decides to `urlopen("https://example.com")`. `pytest-socket` does, loudly, at the exact moment it happens. This upgrades the policy into an enforced invariant for the one surface where it matters most — automated runs that touch the whole codebase.

**Localhost allowance:** tests that use vcrpy cassettes still "talk to" localhost URLs — vcrpy intercepts the request before the socket opens, but the host string must be in the allow-list to not be blocked by pytest-socket's earlier check. Allowing `127.0.0.1` + `localhost` preserves this.

### 6. Fixture layout

```
tests/
├── conftest.py                 # tmp_home, freeze_time, socket block
├── cassettes/                  # vcrpy recordings, committed
│   ├── ollama/
│   └── activitywatch/
├── __snapshots__/              # syrupy outputs, committed
├── data/                       # deterministic fixtures (PNGs, task JSON)
│   ├── screenshots/
│   └── tasks/
├── fixtures/                   # pytest fixtures importable by tests
│   ├── db.py                   # seeded sqlite factory
│   ├── ollama.py               # real-client fixture + capture helper
│   └── activitywatch.py        # real-client fixture + capture helper
├── test_analysis.py
├── test_ollama.py              # NEW
├── test_activitywatch.py       # NEW
├── test_dashboard.py           # was test_dashboard_render + _mutations
├── test_tasks.py               # was test_structured_tasks
├── test_cleanup.py
├── test_afk_gating.py
├── test_discovered_activities.py
└── test_screenshots.py
```

**Why a `tests/` subdirectory:** the current repo-root layout forces every test file to pollute the top level. Moving under `tests/` makes the boundary clean, lets pytest discover without config, and gives `tests/data/` and `tests/cassettes/` a natural home without cluttering the root.

### 7. Dev environment: `.venv` + `requirements-dev.txt`

**Choice:** a local `.venv` at the repo root, installed via `pip install -r requirements-dev.txt`. `.venv/` is gitignored.

**Why:** keeps dev deps off the system Python and out of the runtime dep set. One-time online install; offline thereafter. Activating the venv is the only workflow change for developers.

**requirements-dev.txt pins:** every dep is pinned to an exact version to keep cassette captures reproducible. Upgrades are deliberate PRs.

### 8. The `test-focusmonitor` skill

**Choice:** rewrite the skill to run `pytest` inside `.venv`. Keep its hard rules (do not modify test files, do not install deps from the skill, stop on import errors). Add a documented "cassette re-record" sub-command that invokes `pytest --record-mode=rewrite -k <target>` and reminds the developer to diff and review cassettes before committing.

**Why:** the skill's contract is "run the tests and report." That contract survives the framework change intact — only the invocation changes. Keeping the same skill keeps muscle memory.

### 9. Migration: pilot first, then expand

**Choice:** rewrite `test_analysis.py` first as the proof of the pattern (it's already the best-shaped existing test, and the parser is the clearest hypothesis target). Then `test_ollama.py` as the first greenfield cassette-backed test — this validates the record/replay flow before it's committed to across three more modules. Then `test_activitywatch.py`, then dashboard snapshots, then the remaining conversions.

**Why:** the cassette capture workflow is the highest-risk part of this change. If recording-against-real-Ollama doesn't produce a stable cassette, we want to know before we've rewritten six other files.

## Risks / Trade-offs

- **[Risk] Cassettes drift silently from the real upstream.** If nothing ever re-records them, they become stale fakes — the exact failure mode we're trying to avoid. **Mitigation:** document re-record triggers in the spec (model bump, AW upgrade, suspicious failures), and add a comment in each cassette file with the capture date and model version so staleness is visible.

- **[Risk] Snapshots become churn if the dashboard HTML changes frequently.** Every template tweak forces a `--snapshot-update`. **Mitigation:** scope snapshot tests to stable pages (the main today/yesterday view), not every partial. Accept the churn — it's the price of catching real regressions. If it becomes unbearable, we can carve a smaller stable subtree (e.g., snapshot individual `render_*` helpers instead of the full page).

- **[Risk / Privacy] One-time dev install touches PyPI.** This is a non-localhost network event. **Mitigation:** scoped to the developer machine, triggered explicitly, never executed by focus-monitor runtime. The `block-network.sh` hook will fire on the `pip install` and the developer must explicitly approve. Documented in `CLAUDE.md` and the `test-harness` spec. No user of focus-monitor is affected.

- **[Risk / Privacy] Cassette recording against real Ollama/ActivityWatch may capture user-identifying data.** Developers have personal tasks, personal screenshots, personal AW histories on their machines. A naive cassette could embed any of that. **Mitigation:** cassettes must be captured against a deterministic fixture corpus under `tests/data/`, not live `~/.focus-monitor/` state. Cassette review before commit is a spec requirement, not a convention. Documented rule in `CLAUDE.md`.

- **[Risk] pytest-socket blocks something unexpected.** Some stdlib path (DNS lookups during `socket.gethostbyname("localhost")`, IPv6 resolution) may trip the block. **Mitigation:** allow both `127.0.0.1` and `localhost` hostnames; smoke-test the fixture early in the pilot phase; fall back to per-test `@pytest.mark.enable_socket` with documented reason if a legitimate edge case appears.

- **[Trade-off] pytest breaks the "prefer stdlib" default in CLAUDE.md.** The user has explicitly accepted this for the faithfulness gains. **Mitigation:** dev deps are fenced off in `.venv` and `requirements-dev.txt`; runtime code still imports nothing beyond the existing runtime deps. The CLAUDE.md update will make the stdlib-for-runtime / pytest-ecosystem-for-tests split explicit.

- **[Trade-off] `tests/` subdirectory is a repo-layout change that will confuse anyone holding old muscle memory.** **Mitigation:** CLAUDE.md update + the skill update make the new location the only documented path.

- **[Trade-off] Cassettes live in git and add bytes to the repo.** Small corpus, small cassettes — tens of KB, not MB. Acceptable. If they ever balloon, we revisit with git-lfs or a `.gitattributes` strategy.

## Migration Plan

1. Create `.venv`, add `requirements-dev.txt`, install with network approval. Commit `requirements-dev.txt` and `.gitignore` update.
2. Add `tests/conftest.py` with the three core fixtures (`tmp_home`, `freeze_time`, `disable_network`). Add `tests/__init__.py` if needed.
3. Move + rewrite `test_analysis.py` → `tests/test_analysis.py`. Pilot hypothesis on the parser. Verify it runs, green, offline.
4. Create `tests/fixtures/ollama.py`. Record the first cassette against real Ollama. Write `tests/test_ollama.py`. Verify replay works with pytest-socket active.
5. Repeat for `activitywatch.py`.
6. Add `tests/test_dashboard.py` with syrupy snapshot of `build_dashboard()`. Accept the initial snapshot.
7. Move + rewrite remaining `test_*.py` files under `tests/`.
8. Delete the old repo-root `test_*.py` files in the same commit that lands the replacements.
9. Rewrite `.claude/skills/test-focusmonitor/SKILL.md` to invoke pytest, add the re-record sub-workflow.
10. Update `CLAUDE.md`: dev venv story, offline-at-runtime hard rule, cassette review rule, pointer to `tests/` layout.
11. Run the full suite end-to-end, confirm coverage report, commit.

**Rollback:** the old `test_*.py` files only get deleted in step 8. Until then, both harnesses can coexist. If the pytest harness is discovered to be fundamentally broken during migration, revert the in-progress commits and the old tests still work.

## Open Questions

- **Cassette re-record cadence** — once per release? On-demand when a test fails? The design assumes on-demand for now; we can formalise a cadence later if staleness becomes real.
- **Coverage threshold** — report only, or fail under N%? The design assumes report-only for this change. A threshold can be added later once we have a sense of the honest baseline.
- **Snapshot scope for dashboard** — full page vs per-helper? Starting with full page on the pilot; may carve smaller if churn hurts.
- **Should `freezegun` be a conftest-default or opt-in?** Default is simpler but may surprise a test that wants real time. Starting as opt-in fixture; flip to default if every test ends up requesting it.
