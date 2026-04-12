## 1. Implement the filter

- [x] 1.1 In [focusmonitor/tasks.py](focusmonitor/tasks.py), change the signature of `update_discovered_activities` to `update_discovered_activities(projects, top_titles, planned_tasks=None)`.
- [x] 1.2 Early in the function (after the "empty projects" guard, before the JSON read), build a set of lowercased planned-task names: `blocked = {t["name"].lower() for t in (planned_tasks or [])}`.
- [x] 1.3 Filter `projects` with `projects = [p for p in projects if p and p.lower() not in blocked]` before the upsert loop. If the filtered list is empty, return early (no file write needed).
- [x] 1.4 Leave `_evict_over` and the existing upsert / sample-signal logic untouched.

## 2. Wire planned tasks through the call site

- [x] 2.1 In [focusmonitor/analysis.py](focusmonitor/analysis.py) at the `update_discovered_activities(...)` call around line 277, pass the already-loaded `planned_tasks` variable (it's loaded earlier in `run_analysis` — verify the variable name and scope) so the function receives the current plan.
- [x] 2.2 If `planned_tasks` is not already in scope at the call site, load it once at the top of `run_analysis` rather than re-reading `planned_tasks.json` inside `update_discovered_activities`. No double file reads.

## 3. Preserve activity_log behavior

- [x] 3.1 Verify the `activity_log` INSERT at [focusmonitor/analysis.py:256](focusmonitor/analysis.py#L256)–264 still writes `json.dumps(result["projects"])` — the raw LLM output, unfiltered.
- [x] 3.2 Add a brief comment (≤1 line) at the INSERT clarifying the invariant: "raw model output kept unfiltered for forensic trace; filtering happens in `update_discovered_activities`."

## 4. Tests

- [x] 4.1 Add (or extend an existing) test file at the repo root — `test_discovered_activities.py` already exists; prefer adding to it over creating a new file. Follow the existing `python3 test_*.py` convention.
- [x] 4.2 Test: exact-name match is filtered. Setup `projects=["Focus Monitor", "Sanskrit Tool"]`, `planned_tasks=[{"name": "Focus Monitor", ...}]`, assert only `"Sanskrit Tool"` ends up in the written file.
- [x] 4.3 Test: case-insensitive match is filtered. Setup `projects=["focus monitor"]`, `planned_tasks=[{"name": "Focus Monitor", ...}]`, assert nothing is written.
- [x] 4.4 Test: substring is NOT a match. Setup `projects=["Sanskrit Tooling Dashboard"]`, `planned_tasks=[{"name": "Sanskrit", ...}]`, assert `"Sanskrit Tooling Dashboard"` IS written.
- [x] 4.5 Test: empty / missing `planned_tasks` disables filtering. Call the legacy two-arg shape (or pass `planned_tasks=None`) and assert the function behaves exactly as before.
- [x] 4.6 Test: all projects match planned tasks → no-op write (and the existing file is unchanged).
- [x] 4.7 Test: existing discovered entry upsert still works in the presence of the filter (a non-matching project that's already in the file gets its `count` incremented and `last_seen` updated).
- [x] 4.8 Run all repo-root `test_*.py` files via `python3` to confirm no regressions across the rest of the suite.

## 5. Privacy verification

- [x] 5.1 Run the `privacy-review` skill over the diff — expect "no findings" across all four categories. This is a pure local filter over an already-local file; no new surface area.

## 6. Archive

- [x] 6.1 After implementation and tests pass, run the `openspec-archive-change` skill to fold the delta into `openspec/specs/activity-discovery/spec.md` and move this change to `openspec/changes/archive/`.
