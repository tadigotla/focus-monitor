## Why

`update_discovered_activities` in [focusmonitor/tasks.py:82-88](focusmonitor/tasks.py#L82-L88) diverges from `openspec/specs/activity-discovery/spec.md` in the "all entries promoted" scenario. The spec says that when the 50-entry cap is reached **and every existing entry is promoted**, the oldest-by-`last_seen` should be evicted regardless of its `promoted` flag. The code instead always picks from the `non_promoted` list first, so when all seeds are promoted the only non-promoted candidate is the just-appended new entry — and the new entry evicts itself. Net effect: once the cap fills with promoted entries, the monitor silently stops learning new activities.

This was caught by [test_discovered_activities.py](test_discovered_activities.py), introduced in the `add-discovered-activities-dashboard` change, where the two failing asserts are currently skipped with a pointer to this change.

## What Changes

- Fix the eviction loop in `update_discovered_activities` so that when `non_promoted` is empty **after** the upsert-append, it falls through to evicting the oldest overall — but the insertion order needs to guarantee the new entry is considered non_promoted in the "not all promoted" case and protected in the "all promoted" case.
- Concretely: evict *before* appending the new entry when the list is already at the cap, or separate "make room" from "append" so the new entry is never treated as a candidate for immediate eviction.
- Unskip the two `skip(...)` asserts in `test_discovered_activities.py` and verify they pass.

## Capabilities

### New Capabilities
<!-- None -->

### Modified Capabilities
- `activity-discovery`: no requirement changes — this is a pure code fix to match the existing spec. Listed so the change ties to the capability for traceability.

## Impact

- **Code:** [focusmonitor/tasks.py](focusmonitor/tasks.py) (`update_discovered_activities` eviction logic only).
- **Tests:** [test_discovered_activities.py](test_discovered_activities.py) — unskip two asserts in the "All promoted, cap reached" block.
- **Data:** No migration. Existing `discovered_activities.json` files are unaffected; the bug only bites once a user has 50 promoted entries, which is unlikely in practice but silently wrong when it happens.
- **Privacy:** No network surface, no new dependencies.
