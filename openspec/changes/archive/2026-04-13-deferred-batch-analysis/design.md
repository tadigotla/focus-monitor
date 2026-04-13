## Context

The main loop in `focusmonitor/main.py` runs two interleaved timers: screenshot capture (default every 5 min) and analysis (default every 1 hour). Analysis calls `run_analysis()` which queries ActivityWatch live, gathers recent screenshots, and fires 13+ Ollama calls (12 Pass-1 extractions + 1 Pass-2 classification). This blocks the GPU for minutes per cycle.

The current flow:

```
  main loop tick
    ├── screenshot_due? → take_screenshot()
    └── analysis_due?   → run_analysis(cfg, db)
                              ├── get_aw_events(cfg, ...)     ← live query
                              ├── recent_screenshots(cfg)     ← glob from disk
                              ├── extract_screenshot_artifacts() ← N × Ollama
                              ├── build_classification_prompt()
                              ├── query_ollama()              ← 1 × Ollama
                              ├── INSERT activity_log
                              ├── aggregate_day()
                              └── check_nudges()
```

All data paths are localhost-only (ActivityWatch on :5600, Ollama on :11434). No new external dependencies are introduced.

## Goals / Non-Goals

**Goals:**
- Eliminate Ollama GPU/CPU usage during work hours when `batch_analysis` is enabled.
- Preserve the existing live-analysis flow as the default (`batch_analysis: false`).
- Keep the correction feedback loop viable by batching every 2–3 hours, not once a day.
- Snapshot AW events at collection time so batch processing doesn't depend on AW state hours later.
- Reuse the existing analysis pipeline (Pass 1 + Pass 2 + validation + session aggregation) without forking it.

**Non-Goals:**
- Real-time dashboard during batch mode. Dashboard shows stale data between batches.
- Lightweight AW-only heuristic dashboard (possible future enhancement).
- Nudges in batch mode. They require near-real-time classification.
- Launchd/cron integration. Scheduling stays inside the main loop.
- Changing the analysis pipeline itself (prompts, parsing, validation).

## Decisions

### 1. Staging table (`pending_data`) over filesystem markers

**Decision:** New SQLite table to stage collected data.

```sql
CREATE TABLE IF NOT EXISTS pending_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collected_at TEXT NOT NULL,
    screenshot_path TEXT,
    aw_events_json TEXT NOT NULL,
    processed INTEGER DEFAULT 0
)
```

**Alternatives considered:**
- *Filesystem markers* (e.g., `.processed` sidecar files) — fragile across cleanup, no transactional grouping.
- *Separate queue DB* — unnecessary complexity for a single-process app.

**Rationale:** SQLite is already the data store. A table lets us atomically mark rows as processed, query by time range, and group into analysis windows with plain SQL. WAL mode already handles reader/writer concurrency with the dashboard.

### 2. AW event snapshotting at collection time

**Decision:** Each collection tick calls `get_aw_events()` for the last `screenshot_interval_sec` seconds and stores the raw event list as JSON in `pending_data.aw_events_json`.

**Alternatives considered:**
- *Re-query AW at batch time with wide windows* — AW retains data, but the API summarization may behave differently for 3-hour spans vs. 5-minute spans, and AW must be running at batch time.
- *Store only AW summaries* — loses raw event detail if the analysis prompt evolves.

**Rationale:** Snapshotting raw events makes the batch independent of AW availability and preserves full fidelity. JSON blob per row keeps the schema simple. The AW events for a 5-minute window are small (~1–5 KB).

### 3. Clock-check scheduling in the main loop

**Decision:** The main loop compares `datetime.now().strftime("%H:%M")` against `batch_schedule` entries on each tick. When a match is found and the schedule hasn't already fired for that slot today, trigger `batch_analyze()`.

```python
# Pseudocode inside the main loop
now_hm = datetime.now().strftime("%H:%M")
if cfg["batch_analysis"] and now_hm in cfg["batch_schedule"]:
    if now_hm not in fired_today:
        batch_analyze(cfg, db)
        fired_today.add(now_hm)
```

`fired_today` resets at midnight (or when the date changes).

**Alternatives considered:**
- *`sched` / `threading.Timer`* — more precise but adds threading complexity to a single-threaded loop.
- *launchd plist* — proper macOS scheduling but splits the app into two processes and requires system-level configuration.

**Rationale:** The main loop already polls every 5 seconds. A string comparison per tick is negligible. No new threads, no system config, and easy to adjust by editing `config.json`. The 5-second poll means batch fires within 5 seconds of the scheduled time, which is fine.

### 4. `run_analysis()` signature extension

**Decision:** Add optional keyword arguments to `run_analysis()`:

```python
def run_analysis(cfg, db, *, prefetched_events=None, prefetched_screenshots=None):
```

When `prefetched_events` is not None, skip `get_aw_events()` and use the provided events. Same for `prefetched_screenshots`. The rest of the function (prompt building, Ollama calls, DB writes, session aggregation) is untouched.

**Alternatives considered:**
- *New `run_batch_analysis()` function* — duplicates the pipeline; any future prompt changes would need to be applied in two places.
- *Extract pipeline into a helper called by both* — cleaner but a larger refactor than necessary.

**Rationale:** Two optional kwargs is the minimal change. Existing callers (live mode) pass nothing and get current behavior. Batch caller passes pre-fetched data. No pipeline duplication.

### 5. Batch grouping strategy: replay hourly windows

**Decision:** `batch_analyze()` queries unprocessed `pending_data` rows, groups them into windows of `analysis_interval_sec` width (default 1 hour), and processes each window sequentially through `run_analysis()`.

Grouping is by `collected_at` timestamp. Each window collects its constituent screenshots and merges its AW events into a single summary before calling `run_analysis()`.

**Alternatives considered:**
- *Context-switch-aware grouping* (split on AW app changes) — smarter boundaries but a significant new algorithm. Can be added later.
- *Process all data as one giant analysis* — loses temporal granularity; the classification prompt is designed for bounded windows.

**Rationale:** Preserves the existing analysis prompt's assumption of a bounded time window. Session aggregation still works because each cycle produces the same `activity_log` rows with `cycle_start` / `cycle_end` as today.

### 6. Nudges gated, not removed

**Decision:** The `check_nudges()` call inside `run_analysis()` is skipped when `cfg["batch_analysis"]` is `True`. The nudge infrastructure stays intact.

**Rationale:** A future enhancement could add AW-only nudges (e.g., "you've been in Chrome for 2 hours") that don't need LLM classification. Keeping the code means the path is open without re-implementation.

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| Dashboard stale between batches | User has no live productivity view during work | Accepted trade-off. Raw AW breadcrumbs on dashboard is a future enhancement. |
| Batch runs at a scheduled time when user is actively working | GPU contention returns briefly | Batches at natural break times (noon, 3 PM, 6 PM) minimize this. Could add AFK guard before batch start as future improvement. |
| `pending_data` table grows until batch runs | Disk usage from AW JSON blobs (~1–5 KB each × 12/hour = negligible) | Screenshot disk usage is the real cost and is already bounded by `screenshot_keep_hours`. |
| Correction feedback latency increases to 2–3 hours | Model improvement is slower; user may not remember activity context as well | Intentional trade-off. Schedule can be tightened if needed. |
| AW events snapshotted for 5-min windows must be re-summarized for 1-hour analysis windows at batch time | Need to merge/re-summarize multiple 5-min event snapshots into one coherent summary | `batch_analyze()` concatenates raw events from constituent rows and calls `summarize_aw_events()` on the merged set. |
| `run_analysis()` signature change | Callers in tests may need updating | Kwargs are optional with `None` defaults; existing call sites are unaffected. |
