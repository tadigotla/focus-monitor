---
name: test-focusmonitor
description: Run focus-monitor's existing `test_*.py` files at the repo root directly via `python3`. Use when you want to verify the project still works after a change. Does not introduce a test framework.
---

# test-focusmonitor

focus-monitor's tests are plain Python scripts at the repo root. There is no
pytest, no unittest discovery, no conftest. Each `test_*.py` is executed
directly and its exit code indicates pass/fail. This skill runs them and
reports results.

## Hard rules

- **DO NOT** introduce a test framework (pytest, unittest, nose, etc.). Adding
  one requires an openspec change first.
- **DO NOT** modify any `test_*.py` file as part of running this skill. Fixing
  a failing test is a separate task; this skill only reports.
- **DO NOT** run tests from any directory other than the repo root.

## How to invoke

Ask me: "Run test-focusmonitor" or "Run the focus-monitor tests".

## What to do

1. Confirm you are at the repo root (the directory containing `monitor.py`,
   `dashboard.py`, `setup.py`, and the `focusmonitor/` package).
2. List the test files: every `test_*.py` in the repo root. As of writing,
   that is:
   - `test_analysis.py`
   - `test_cleanup.py`
   - `test_structured_tasks.py`
   If the set differs when you run this, use whatever `test_*.py` files are
   present — do not hardcode the list.
3. For each file, run `python3 <file>` and capture:
   - The exit code.
   - The last ~20 lines of stdout+stderr if the exit code is non-zero.
4. Report results in the format below.
5. Do not continue to the next file if one crashes with an import error —
   report it and stop. Import errors usually indicate a broken repo state
   that will make every subsequent run fail the same way.

## Report format

```
# test-focusmonitor report

| File                      | Exit | Result |
|---------------------------|------|--------|
| test_analysis.py          |  0   | PASS   |
| test_cleanup.py           |  1   | FAIL   |
| test_structured_tasks.py  |  0   | PASS   |

## Failures

### test_cleanup.py (exit 1)
<last ~20 lines of output>

## Summary
2/3 passed. `test_cleanup.py` failed — see output above.
```

If all pass, drop the Failures section and state "All N tests passed."

## What this skill does NOT do

- It does not fix failing tests.
- It does not add new tests.
- It does not run linters, type checkers, or coverage tools.
- It does not install dependencies. If a test fails with
  `ModuleNotFoundError`, report it and stop — do not try to `pip install`
  anything (the network-block hook will catch it anyway).
