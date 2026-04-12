## 1. Config

- [x] 1.1 Add `idle_skip_grace_sec` (default `60`) to `DEFAULT_CONFIG` in [focusmonitor/config.py](focusmonitor/config.py).
- [x] 1.2 Verify a fresh install writes the key into `~/.focus-monitor/config.json` and that an existing config without the key falls back to the default via the `cfg.update(...)` merge in `load_config()`.

## 2. AFK helper in activitywatch.py

- [x] 2.1 Add `get_afk_state(cfg)` to [focusmonitor/activitywatch.py](focusmonitor/activitywatch.py) that returns a small tuple/dict describing the current state: `{"status": "afk" | "not-afk" | "unknown", "since": <datetime | None>}`.
- [x] 2.2 Inside the helper: GET `/api/0/buckets`, find the first bucket whose name starts with `aw-watcher-afk`, then POST a query for events in the last ~10 minutes scoped to that bucket (reuse the existing query-endpoint pattern from `get_aw_events`).
- [x] 2.3 Pick the most recent event, read `data.status`, compute `since = event.timestamp` when the status is `afk`, and return it.
- [x] 2.4 On any failure path (URLError, no bucket, missing/unknown `status`, empty events list), return `status="unknown"` with `since=None`. Log a single warning line in the same style as `get_aw_events`.
- [x] 2.5 Add a module-level `_afk_warning_printed` guard (or accept a one-warning-per-run approach) so the warning line is not spammed every tick when AW is down.

## 3. Main loop gating in main.py

- [x] 3.1 In [focusmonitor/main.py](focusmonitor/main.py), add a helper `should_skip_tick(cfg)` that calls `get_afk_state(cfg)` and returns `True` only when `status == "afk"` AND `now - since >= cfg["idle_skip_grace_sec"]`.
- [x] 3.2 Track previous idle state in a local variable so transitions can be detected (`was_idle`).
- [x] 3.3 Wrap the screenshot-capture branch and the analysis branch inside a single `if should_skip_tick(cfg): ... else: ...`. Leave `run_cleanup` OUTSIDE the gate so retention keeps running during idle stretches.
- [x] 3.4 On transition to idle (`was_idle == False and skipping now == True`), print `💤 idle — skipping capture`. On transition out of idle, print `▶️  resumed`.
- [x] 3.5 Do not print anything on stable-idle ticks.
- [x] 3.6 When a tick is skipped, still advance `last_screenshot` / `last_analysis` to `now` so the loop doesn't try to catch up with a burst of work the moment the user returns.

## 4. Privacy verification

- [x] 4.1 Run the `privacy-review` skill over the diff — confirm no new hosts, no new imports that touch the network, no changes to screenshot retention or storage paths.
- [x] 4.2 Confirm the change only adds calls to `http://localhost:5600` and does NOT touch `ollama_url` or introduce any new URL constants.

## 5. Tests

- [x] 5.1 Add `test_afk_gating.py` at the repo root following the existing `python3 test_*.py` convention (no pytest).
- [x] 5.2 Unit-test `get_afk_state` parsing: fake a buckets response and an events response via a small monkey-patch on `urlopen`, and assert the returned tuple for `afk`, `not-afk`, and malformed cases.
- [x] 5.3 Unit-test the skip-decision helper: given a fake `get_afk_state` returning various `(status, since)` pairs and a fixed `now`, assert skip vs. run for the grace-window edges (just under, just over, zero, very large).
- [x] 5.4 Unit-test the fail-open path: `get_afk_state` returning `unknown` must NOT cause a skip.
- [x] 5.5 Run all repo-root `test_*.py` files via `python3` to confirm no regressions in existing tests.

## 6. Documentation

- [x] 6.1 Add a one-line comment next to `idle_skip_grace_sec` in `DEFAULT_CONFIG` explaining the unit (seconds) and the "set very large to disable, set to 0 for immediate skip" extremes.
- [x] 6.2 Update the startup banner in `main.py` to print the current grace window alongside the other intervals so users can see gating is active.

## 7. Archive

- [x] 7.1 After implementation and tests pass, run the `openspec-archive-change` (a.k.a. `opsx:archive`) skill to fold the delta into the top-level `openspec/specs/` tree and move this change to `openspec/changes/archive/`.
