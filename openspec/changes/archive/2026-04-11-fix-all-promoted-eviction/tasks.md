## 1. Fix eviction order in `update_discovered_activities`

- [x] 1.1 Read [focusmonitor/tasks.py](focusmonitor/tasks.py) lines 34-91 to re-confirm the current append-then-shrink flow and the exact eviction branch at lines 82-88.
- [x] 1.2 Extract the eviction loop into a small helper, e.g. `def _evict_over(activities, limit):` that runs `while len(activities) > limit: ...` with the same non-promoted-first, fall-through-to-oldest logic. Keep it file-private.
- [x] 1.3 Restructure `update_discovered_activities` so that for the `existing is None` branch (new name), eviction runs to bring the list down to `MAX_DISCOVERED - 1` **before** appending the new entry. For the `existing is not None` branch (upsert of a known name), skip the eviction entirely — the list length didn't change.
- [x] 1.4 Verify the eviction uses `while`, not `if`, so a single call detecting multiple new projects at once still settles at `MAX_DISCOVERED` (defensive — not the common case, but the prompt can return multiple projects).

## 2. Unskip and verify the test

- [x] 2.1 In [test_discovered_activities.py](test_discovered_activities.py), replace the two `skip(...)` calls in the "All promoted, cap reached" block with `test(...)` calls (the assertions are already written — only the wrapper changes).
- [x] 2.2 Remove the "KNOWN DIVERGENCE" comment block above those asserts; leave a one-line note that references the spec scenario if useful, or delete it entirely.
- [x] 2.3 Run `python3 test_discovered_activities.py` and confirm: all scenarios pass, `0 failed, 0 skipped`.
- [x] 2.4 Run `python3 test_structured_tasks.py` and confirm the existing coarser cap test still passes (no regression on the non-promoted path).
- [x] 2.5 Run `python3 test_analysis.py` and `python3 test_cleanup.py` as a belt-and-suspenders regression pass.

## 3. Privacy & hygiene

- [x] 3.1 Run `.claude/skills/privacy-review` over the diff — expected: no findings (pure in-memory logic fix).
- [x] 3.2 Sanity-check that `MAX_DISCOVERED = 50` constant is unchanged and the public signature of `update_discovered_activities(projects, top_titles)` is unchanged.
- [x] 3.3 Archive the change via `/opsx:archive fix-all-promoted-eviction` once everything above is green.
