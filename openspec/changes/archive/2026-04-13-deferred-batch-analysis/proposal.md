## Why

The LLM analysis pipeline (Pass 1 screenshot extraction + Pass 2 classification) runs inside the main loop on the same schedule as data collection. On Apple Silicon, each analysis cycle fires ~13 Ollama calls that keep the GPU busy for minutes, competing with the user's actual work. Moving analysis to scheduled batch windows eliminates resource contention during focused work hours while preserving the correction feedback loop by running batches every 2–3 hours at natural break times.

## What Changes

- **New `pending_data` table** — screenshots and snapshotted AW events are staged here at collection time; batch processing consumes them later.
- **Collection-only ticks** — when batch mode is enabled, the main loop captures screenshots and AW snapshots on their existing interval but never calls Ollama.
- **Scheduled batch analysis** — a configurable list of clock times (e.g., `["07:00", "12:00", "15:00", "18:00", "20:00"]`) triggers batch processing of all pending data. Implemented as a time check inside the existing `while True` loop (no launchd/cron).
- **`run_analysis()` accepts pre-fetched data** — refactored to take AW events and screenshot paths as arguments instead of querying them live, so both live and batch callers can use the same pipeline.
- **Nudges disabled in batch mode** — `check_nudges()` is skipped when `batch_analysis` is enabled since real-time distraction feedback is not meaningful with deferred analysis.
- **New config keys** — `batch_analysis` (bool, default `false`) and `batch_schedule` (list of `"HH:MM"` strings). When `batch_analysis` is `false`, existing live-analysis behavior is unchanged.

## Capabilities

### New Capabilities
- `deferred-analysis`: Covers the pending-data staging table, AW event snapshotting at collection time, scheduled batch processing, and the collect-only main-loop mode.

### Modified Capabilities
- `structured-analysis`: `run_analysis()` signature changes to accept pre-fetched events and screenshot paths. The analysis pipeline itself (Pass 1, Pass 2, parsing, validation) is unchanged.
- `idle-gating`: Idle gating still controls whether collection ticks fire, but no longer gates analysis ticks (those are clock-scheduled in batch mode).
- `correction-loop`: Corrections still work but feedback latency increases from ~1 hour to ~2–3 hours in batch mode. No schema changes.

## Impact

- **`focusmonitor/main.py`** — main loop gains collect-only path and batch-trigger clock check.
- **`focusmonitor/analysis.py`** — `run_analysis()` signature change; new `batch_analyze()` entry point that groups pending data into windows and feeds them through the existing pipeline.
- **`focusmonitor/db.py`** — new `pending_data` table in `init_db()`.
- **`focusmonitor/config.py`** — new defaults for `batch_analysis` and `batch_schedule`.
- **`focusmonitor/activitywatch.py`** — new function to snapshot and return raw AW events (vs. the current summarize-only path).
- **`focusmonitor/nudges.py`** — no code changes, but `check_nudges()` call gated behind `batch_analysis` flag.
- **Tests** — new tests for pending-data storage, batch grouping, and clock-trigger logic. Existing analysis tests remain valid since the pipeline is unchanged.
- **No new dependencies.** Scheduling uses stdlib `datetime` comparisons.
