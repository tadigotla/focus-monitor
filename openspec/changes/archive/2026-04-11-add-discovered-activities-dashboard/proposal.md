## Why

`discovered_activities.json` captures projects the AI has observed during analyses, but the user has no way to see it without opening the file on disk. Surfacing it in the dashboard closes the loop: users can spot new activities the monitor is learning about and decide whether to promote them into `planned_tasks.json`. This change also takes the opportunity to verify the upsert, eviction, and signal-capture logic actually behaves as the spec requires — there is currently no direct coverage for it.

## What Changes

- Render a "Discovered Activities" section on the dashboard showing each entry's name, first/last seen, count, promoted flag, and sample signals.
- Read `discovered_activities.json` from `~/.focus-monitor/` at dashboard render time (no schema change, no new persistence layer).
- Sort entries by `last_seen` descending; visually distinguish promoted entries from unpromoted ones.
- Handle the "file missing / empty / malformed" cases gracefully so a broken JSON file never takes the dashboard down.
- Add a repo-root `test_discovered_activities.py` that exercises `update_discovered_activities` end-to-end: new-entry creation, upsert/count increment, signal extraction and merge, 50-entry cap eviction, promoted-entry protection, and the "all promoted, oldest still evicted" fallback.

## Capabilities

### New Capabilities
<!-- None - this change extends existing capabilities only. -->

### Modified Capabilities
- `dashboard-server`: Adds a requirement that the dashboard render the contents of `discovered_activities.json` alongside the existing timeline and stats.
- `activity-discovery`: No requirement changes, but the existing requirements get explicit test coverage. Listed here so the tasks phase can track verification against each scenario.

## Impact

- **Code:** [focusmonitor/dashboard.py](focusmonitor/dashboard.py) (new section + loader), [focusmonitor/config.py](focusmonitor/config.py) (re-export `DISCOVERED_FILE` if not already imported in dashboard), new [test_discovered_activities.py](test_discovered_activities.py) at repo root.
- **Data:** Reads existing `~/.focus-monitor/discovered_activities.json`. No new files written, no schema change.
- **Dependencies:** None. Pure stdlib.
- **Privacy:** No new network calls. Dashboard continues to bind 127.0.0.1 only. The new section renders data already on disk to a page already served locally — no change to the privacy posture.
