## 1. Verify `discovered_activities.json` population (write the test first)

- [x] 1.1 Create `test_discovered_activities.py` at repo root following the `test_structured_tasks.py` style (tempdir + monkey-patch `focusmonitor.config.DISCOVERED_FILE`).
- [x] 1.2 Scenario: new activity — call `update_discovered_activities(["project-a"], ["project-a — VS Code"])`, assert file is created with one entry, `count == 1`, `promoted is False`, `first_seen == last_seen`, and `sample_signals` contains `"project-a"` and `"VS Code"`.
- [x] 1.3 Scenario: known activity upsert — call twice, assert `count == 2`, `last_seen >= first_seen`, and signals are merged with no duplicates and capped at 10.
- [x] 1.4 Scenario: first run with no file — delete the temp file, call once, assert the file is recreated with an `activities` array containing the new entry.
- [x] 1.5 Scenario: signal extraction — pass titles with mixed `—`, `-`, `|`, `:` separators and assert that short (≤2 chars) and overly long (>79 chars) parts are filtered out per `update_discovered_activities` logic.
- [x] 1.6 Scenario: cap eviction — seed 50 entries with varying `last_seen`, add a new one, assert length stays at 50 and the oldest non-promoted entry is gone.
- [x] 1.7 Scenario: promoted protection — seed 50 where the oldest-by-`last_seen` is `promoted: true`, add a new entry, assert the promoted one is retained and the next-oldest non-promoted is evicted.
- [x] 1.8 Scenario: all promoted, cap reached — seed 50 all promoted, add a new entry, assert the oldest-by-`last_seen` is evicted regardless of promoted status.
- [x] 1.9 Scenario: user-set `promoted: true` is preserved across upserts — seed an entry with `promoted: true`, call `update_discovered_activities` on that same name, assert `promoted` stays `true` after the upsert.
- [x] 1.10 Run `python3 test_discovered_activities.py`; if any scenario fails, STOP and report the divergence — do not silently "fix" the production code as part of this change.

## 2. Load discovered activities in the dashboard

- [x] 2.1 Add a `_load_discovered_activities()` helper in `focusmonitor/dashboard.py` that imports `DISCOVERED_FILE` from `focusmonitor.config`, returns `[]` on `FileNotFoundError`, `json.JSONDecodeError`, or `OSError`, and otherwise returns the `activities` list sorted by `last_seen` descending.
- [x] 2.2 Unit-check the helper manually by creating a temp file with a handful of entries and confirming it returns them in the expected order (can reuse the test file from section 1 if practical, otherwise quick REPL check).

## 3. Render the Discovered Activities section

- [x] 3.1 Add a `DISCOVERED_HTML` placeholder to `HTML_TEMPLATE` below the Timeline section, with a matching `<h1>` and a single card container.
- [x] 3.2 In `build_dashboard`, call `_load_discovered_activities()`, build the section HTML (one sub-entry per activity showing name, count, first_seen/last_seen as `HH:MM` or `YYYY-MM-DD`, promoted badge when applicable, and sample-signal pills), and `.replace("DISCOVERED_HTML", ...)` the template.
- [x] 3.3 Add CSS classes to the existing `<style>` block for the promoted badge and the signal pills (reuse `.tag` pill styles where possible).
- [x] 3.4 Empty-state: when the helper returns `[]`, render `<div class="empty">No activities discovered yet.</div>` in the card.
- [x] 3.5 HTML-escape activity name and sample signals before interpolation (use `html.escape`) so a pathological window title cannot break the page.

## 4. Smoke-test the dashboard end-to-end

- [x] 4.1 With a real `~/.focus-monitor/discovered_activities.json` present, run `python3 dashboard.py` (or `python3 cli.py dashboard` — whichever is the current entrypoint) and visit `http://localhost:9876/` in a browser.
- [x] 4.2 Verify the new section renders: activities present, sort order correct, promoted badge shown on hand-flipped entries, signals visible.
- [x] 4.3 Rename the JSON file aside and reload — confirm the empty-state renders and the rest of the dashboard is unaffected.
- [x] 4.4 Write deliberately broken JSON to the file and reload — confirm empty-state renders and the page still returns 200.
- [x] 4.5 Restore the real file.

## 5. Privacy & hygiene

- [x] 5.1 Run `.claude/skills/privacy-review` over the diff; confirm no new outbound hosts, no new dependencies, dashboard still binds 127.0.0.1.
- [x] 5.2 Run all repo-root `test_*.py` files via `python3 test_<name>.py` (or the `test-focusmonitor` skill) and confirm they still pass.
- [x] 5.3 Update the openspec change status to done via the archive flow when everything above is green.
