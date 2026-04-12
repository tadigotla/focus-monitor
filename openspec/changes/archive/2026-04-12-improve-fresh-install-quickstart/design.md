## Context

The tool is solid once set up, but the onboarding flow trusts too much. Reality on a fresh Mac:

```
  README promise                 What actually happens
  ────────────────────────────── ────────────────────────────────────
  git clone && python3 setup.py  ❌ setup.py errors: "Ollama not found"
                                    (user has to go install it first)
  [install Ollama]               ❌ setup.py errors: model missing
                                    (user has to pull 7.8 GB)
  [pull model]                   ✅ setup.py succeeds
                                 ⚠️  But the Ollama daemon isn't running
  nano planned_tasks.json        ✅ ok
  python3 cli.py run             ❌ First analysis tick: "Ollama query
                                    failed: Connection refused"
                                    (because `brew install ollama` doesn't
                                     auto-start the daemon)
                                 ❌ Or "No aw-watcher-window bucket"
                                    (because AW.app isn't launched)
                                 ❌ Or: black screenshots
                                    (because Screen Recording permission
                                     wasn't granted)
```

Every one of those failures is diagnosable, but each costs the user a
round-trip to the README, and some (Screen Recording → silent black PNG)
are invisible until the AI starts describing black rectangles.

`setup.py` is the natural place for these checks — it already exists,
already checks binaries, and already prints instructions. It just
doesn't go the final mile of checking that the daemons are *actually
responding*.

## Goals / Non-Goals

**Goals:**
- A fresh Mac user who follows the README top-to-bottom lands on a
  working install with no silent gaps.
- `setup.py` distinguishes four states for each external dependency:
  binary missing, binary present + daemon down, daemon up + bad state
  (e.g. Ollama up but model not pulled), and healthy. Each state
  surfaces a concrete next command.
- The user never has to read the README twice — the order of operations
  matches the order of failures, and every failure points at the next
  command to run.
- `setup.py`'s output strings match the code's actual behaviour
  (`.json`, not `.txt`).
- The probes never talk to anything but loopback.
- New unit tests cover every branch of the probe logic without ever
  touching a real service.

**Non-Goals:**
- Not touching `focusmonitor/` runtime code. The monitor itself doesn't
  know about these checks.
- Not adding a wrapper that starts Ollama / ActivityWatch automatically.
  Those are user-machine services with their own lifecycles; auto-
  starting them would be surprising and fragile. The tool advises; the
  user acts.
- Not adding brew or any other package manager as a hard dependency.
  README `brew install` commands are *suggestions*, not the only path.
  A user who prefers the Ollama desktop app or downloads AW manually is
  still first-class.
- Not running the real `cli.py run` during tests. That's an orchestrator
  with real side effects; `test_install_flow.py` tests the probes
  directly.
- Not adding a "verify install" CLI subcommand. The README can document
  the verify recipe as a handful of commands; adding a subcommand is
  scope creep.

## Decisions

### 1. Daemon probes use `urllib.request` against loopback only

**Choice:** stdlib `urllib.request.urlopen("http://127.0.0.1:<port>/api/…")`
with a short timeout (~2s).

**Alternatives considered:**
- Shelling out to `curl` — rejected. Adds a dependency on curl being
  installed (reasonable on macOS, but silly when Python can do it) and
  complicates testing.
- `socket.create_connection((host, port))` — faster and simpler, but
  only tells you a TCP listener exists, not whether it's actually the
  right service. `api/tags` and `api/0/info` confirm the response shape.

**Why this works:** the Ollama probe already parses `/api/tags` to list
pulled models, so it can distinguish "Ollama running but
`llama3.2-vision` missing" from "Ollama running + model pulled". That
gives the user a concrete next step (`ollama pull llama3.2-vision`)
instead of a generic "something is wrong".

### 2. Health-check states are a small explicit enum

**Choice:** each probe returns one of:

```
  STATE               MEANING                       NEXT STEP SHOWN
  ──────────────────  ───────────────────────────   ───────────────────────
  "missing"           Binary not installed          "brew install X" / URL
  "daemon_down"       Binary present, socket down   "ollama serve" / open app
  "wrong_state"       Daemon up, bad state          "ollama pull <model>"
  "ok"                Healthy                       (no action)
  "unknown"           Probe failed unexpectedly     Print raw error, fail-open
```

**Why:** a boolean (ok / not ok) loses the information the user actually
needs. The existing `setup.py` already makes a distinction between
"Ollama binary missing" and "model missing" — this just extends the
same pattern to "daemon running".

**fail-open on "unknown":** if the probe itself throws something
unexpected, `setup.py` should print the error and continue, not crash
the whole setup. A failed probe is a notice, not a fatal. The installer
plist still gets created; the user can retry later.

### 3. Screen Recording permission — README-only

**Choice:** move the permission note to an explicit step in the README
Quick Start. Do NOT add an automated check to `setup.py`.

**Rationale:** there's no portable way to query macOS TCC from Python
without shelling out to `tccutil` (which requires admin) or parsing
private frameworks. Every option is a layer-crossing hack that is
fragile against macOS updates. The README callout — at the right spot
in the sequence — is the cleanest lever.

**Where it goes:** right after the `python3 setup.py` line, as Step 4
(before `cli.py run`), so a user reads about the permission before the
first command that exercises `screencapture`.

### 4. `test_install_flow.py` uses stdlib mocks, not cassettes

**Choice:** test the probes by monkey-patching `urllib.request.urlopen`
and `subprocess.run` inside `focusmonitor_install.py` (the new module
the probes live in). No vcrpy cassettes.

**Why:** the probes are deterministic unit logic — given a specific
HTTP response shape or a specific exception, they return a specific
state. That's exactly the shape unit tests are good at. Recording
cassettes would be overkill for a 30-line helper, and would couple the
test to a real Ollama/AW happening to be running during capture.

The cassette-backed tests already cover the *real* Ollama and AW HTTP
shapes in `tests/test_ollama.py` and `tests/test_activitywatch.py` —
this change doesn't need a second copy.

### 5. Probe logic lives in `focusmonitor/install.py`, not inline in `setup.py`

**Choice:** factor the probe helpers into a new module
`focusmonitor/install.py`. `setup.py` imports and calls them.

**Why:**
- `setup.py` stays a thin orchestrator that prints + writes plist.
- The helpers become testable in isolation — the test can import
  `focusmonitor.install` and call probe functions directly, without
  standing up the full `setup.py` entrypoint.
- The `focusmonitor` package is the canonical home for runtime code;
  this aligns with the existing split (`main.py`, `dashboard.py`, etc.).

**Trade-off:** `focusmonitor/install.py` is imported by `setup.py`
before the venv is active. It must not depend on any third-party
package. Constraint satisfied: the module uses only `urllib.request`,
`urllib.error`, `json`, `subprocess`, `shutil`, `pathlib` — all stdlib.

### 6. `planned_tasks.txt` → `planned_tasks.json` in setup.py output

**Choice:** fix the stale string in setup.py's "Next steps" print
block. No other semantic change.

**Why:** this is a pure docstring bug. The code migrated to JSON
months ago; the printed text is a fossil. Fixing it costs one line and
removes a source of user confusion.

## Risks / Trade-offs

- **[Risk] A probe races against a slow-starting daemon.** User runs
  `ollama serve &` a second before `setup.py`, and the probe hits the
  socket before it's fully listening. **Mitigation:** 2s timeout on
  the probe, and if it fails, the instructions tell the user to
  "re-run `python3 setup.py`". A transient miss is easy to recover
  from; a false green is not.

- **[Risk] The Ollama `/api/tags` endpoint shape changes.** The probe
  parses JSON and looks for a specific model name — if the response
  shape moves, the probe could report "daemon_down" for a healthy
  service. **Mitigation:** existing cassette-backed tests in
  `tests/test_ollama.py` would fail first, alerting us before the
  probe regresses. Also, the probe falls open (`state="unknown"`) on
  `json.JSONDecodeError` rather than crashing.

- **[Risk] ActivityWatch on first launch has no `aw-watcher-window`
  bucket yet** (it takes a few seconds of activity to register). The
  probe could report "wrong_state" on a valid install. **Mitigation:**
  the AW probe only checks that `api/0/info` responds with
  `testing=false` (or any non-error). It deliberately does NOT check
  for buckets — that's the runtime's job, not setup's. Setup's job is
  "is AW reachable"; the monitor's job is "does the bucket exist".

- **[Risk / Privacy] New loopback probes.** Each probe is a GET to
  `127.0.0.1:11434` and `127.0.0.1:5600`. These are both already-
  permitted hosts. No new data categories, no new dependencies.
  `block-network.sh` will not match them. **Mitigation:** the
  `privacy-review` skill will still be run over the diff before
  commit; the change's proposal explicitly names these as loopback-
  only. Zero new privacy surface.

- **[Trade-off] The README Quick Start gets longer.** From ~15 lines
  to ~30. This is the price of making it runnable from a clean Mac.
  The alternative (keep it short, lose freshness-completeness) is the
  bug we're fixing. Mitigation: the prereq block is clearly marked so
  experienced users can skip past it.

- **[Trade-off] Factoring probes into `focusmonitor/install.py`
  enlarges the runtime package with code the monitor itself will
  never call.** A few dozen lines in a new small module. Acceptable —
  the win is testability.

## Migration Plan

1. Land `focusmonitor/install.py` with the probe helpers.
2. Wire `setup.py` to call them, preserving the existing print shape
   where possible.
3. Fix the `.txt` → `.json` string.
4. Add `tests/test_install_flow.py` with unit tests for every probe
   state.
5. Rewrite the README Quick Start with the prereq block and inlined
   permission step.
6. Add the "Verifying your install" section to the README.
7. Run full pytest suite; confirm green.
8. Privacy-review the diff before committing.

**Rollback:** the change is additive on `setup.py` and purely
documentation on README. If anything regresses, revert the single
commit and existing behaviour returns — the monitor never depended on
the new checks.

## Open Questions

- **Should the AW probe warn if the user is running AW in `--testing`
  mode on the production port?** Edge case, low probability, skip for
  now.
- **Should setup.py attempt to detect Homebrew vs manual install of
  Ollama and tailor the start command?** (e.g. `brew services start
  ollama` vs `ollama serve`). Probably yes, but scope-creep for this
  change — the README shows both commands and the probe just reports
  "daemon_down" without prescribing one specific start command.
- **Should the "Verifying your install" section in the README include
  the pytest command** (`.venv/bin/pytest tests/`)? Leaning yes,
  because it's the most rigorous smoke test available. Leaning no,
  because not every user will set up the dev venv. Default: mention
  it as optional.
