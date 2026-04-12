## Context

`update_discovered_activities` in [focusmonitor/tasks.py](focusmonitor/tasks.py) maintains a 50-entry cap on `discovered_activities.json`. The current eviction loop:

```python
while len(activities) > MAX_DISCOVERED:
    non_promoted = [a for a in activities if not a.get("promoted")]
    if non_promoted:
        oldest = min(non_promoted, key=lambda a: a.get("last_seen", ""))
    else:
        oldest = min(activities, key=lambda a: a.get("last_seen", ""))
    activities.remove(oldest)
```

runs **after** the new entry has already been appended, and the spec scenario "All entries promoted" says:

> WHEN all 50 entries are promoted and a new activity is detected
> THEN the oldest entry (by `last_seen`) is evicted regardless of promoted status

The current code's fallthrough (`else`: pick oldest overall) is never exercised in this case, because after the append the list has one non-promoted candidate: the just-inserted new entry. `min(non_promoted, key=last_seen)` returns it, and `activities.remove(oldest)` discards the new entry. The 50 promoted seeds stay, the monitor silently stops learning new activities.

This was verified by [test_discovered_activities.py](test_discovered_activities.py), which currently has two `skip()` asserts pointing at this change.

## Goals / Non-Goals

**Goals:**
- Make the eviction behavior match the spec in all three cases: "cap with non-promoted entries," "cap with a promoted oldest," and "all entries promoted."
- Do the fix without changing the spec, the JSON on disk format, or the public signature of `update_discovered_activities`.
- Leave the cap (`MAX_DISCOVERED = 50`) and the sample-signal logic untouched.

**Non-Goals:**
- Rethinking eviction semantics (e.g., count-based, LRU-with-weight). The spec is fine; the code just has a bug.
- Changing how the prompt/LLM populates `projects` — that is tracked by `filter-planned-tasks-from-discoveries`.
- A migration pass over existing `discovered_activities.json` files — the bug only matters at the cap edge, and real users don't have 50 entries today.

## Decisions

**Decision 1: Evict *before* appending the new entry, not after.**

Switch from "append, then shrink" to "shrink to `MAX_DISCOVERED - 1` (only when we're adding a brand-new entry), then append." This way the new entry is never a candidate for immediate eviction, and the "all promoted" case naturally falls through to the else branch that picks the oldest overall.

Pseudo:
```python
# After the upsert loop handles known-names:
if existing is None:
    _evict_to_make_room(activities)  # shrinks to <= MAX_DISCOVERED - 1
    activities.append(new_entry)
```

Rationale:
- Minimal diff: the eviction logic is unchanged, we just run it at a different moment and target a size of `MAX_DISCOVERED - 1` instead of `MAX_DISCOVERED`.
- The existing `while len(activities) > MAX_DISCOVERED - 1` guard naturally handles the "not yet full" case (no-op) and the "full" case (one eviction) without special-casing.
- Known-name upserts don't grow the list, so they don't need eviction at all. The current code unnecessarily runs the eviction loop after every update; the new shape only runs it when we actually need to make room. Cleaner and faster.

**Alternative considered:** Leave append-first, but subtract the new entry from the `non_promoted` candidate pool. Rejected — requires identifying "the new entry" after append (by name? by object identity? by timestamp?) and introduces edge cases when the LLM detects the same name twice in one call. Less robust than avoiding the collision entirely.

**Alternative considered:** Change the spec so that "all promoted, cap reached" means the new activity is silently dropped. Rejected — the spec intent is clear (preserve learning when the user has promoted everything), and the current behavior was an oversight, not a design choice. Also, if we dropped new activities we'd also want a user-visible warning, which is a bigger change.

**Decision 2: Factor the eviction into a named helper.**

Extract a small `_evict_one_if_over(activities, limit)` (or similar) so the logic has one call site and is obviously testable. Keeps `update_discovered_activities` readable.

**Alternative considered:** Inline. Rejected — the function is already doing two things (upsert + eviction) and splitting them makes the control flow clearer.

**Decision 3: Reuse `test_discovered_activities.py`, don't create a new test file.**

The two skipped asserts there already encode the expected behavior. Unskip them. Do not duplicate into a separate file.

**Decision 4: Do not touch `test_structured_tasks.py`.**

That file has a coarser cap-enforcement test that currently passes; the fix should not regress it. Re-run it as part of the verification pass.

## Risks / Trade-offs

- **[Risk] Reordering the eviction changes the moment at which known-name upserts run eviction** → Mitigation: known-name upserts currently never trigger eviction anyway (the list length is unchanged), so moving the eviction call inside the `existing is None` branch is a net no-op for the upsert path. Confirmed by re-running all existing tests.
- **[Risk] A pathological `projects` list with many new names in one call could push the list past the cap by more than 1** → Mitigation: wrap the eviction in a `while` (not `if`) so it keeps shrinking until the list is at the target size. The cost is negligible at N=50.
- **[Risk] Eviction helper returns the evicted entry for logging, and we forget to use it** → Mitigation: return nothing; the helper mutates in place. Logging eviction is out of scope for this change (could be added in a later observability pass).
- **[Privacy] New external calls or dependencies** → None. Pure in-memory list manipulation on a file the system already owns.
