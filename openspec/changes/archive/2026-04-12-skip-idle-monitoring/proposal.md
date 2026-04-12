## Why

The main loop in [focusmonitor/main.py](focusmonitor/main.py) takes screenshots and runs LLM analysis on a fixed wall-clock cadence — it does **not** consult ActivityWatch's AFK watcher. So when the user steps away (lunch, meeting on another device, overnight), the monitor keeps capturing the same locked / screensaver / empty-desktop frames and paying Ollama to classify them. The resulting `activity_log` rows are noise: low focus scores attributed to "distracted or idle" drag trend history down, screenshots burn disk quota for 48h, and the dashboard shows activity that isn't really activity. This also contradicts the spirit of the tool — it's supposed to help the user understand their *active* work, not log their absence.

## What Changes

- In the main loop, before each screenshot or analysis tick, check whether the user has been AFK per ActivityWatch's `aw-watcher-afk` bucket. If the most recent AFK event covers *now* and is tagged `afk`, skip both the screenshot capture and the analysis run for that tick.
- Add a minimal AFK query helper in `focusmonitor/activitywatch.py` that finds the `aw-watcher-afk_*` bucket and returns the current AFK state (plus when it started). Network stays on `localhost:5600` — no new outbound surface.
- Add an `idle_skip_grace_sec` config key (default: 60) so a brief pause doesn't immediately stop monitoring; only skip when AFK has been continuous for longer than the grace window. This avoids ping-ponging around short context switches.
- Print a one-line `💤 idle — skipping` status when a tick is skipped, and `▶️  resumed` on the first non-idle tick after an idle stretch, so the user can see the monitor is alive but choosing not to work.
- Cleanup and retention jobs (`run_cleanup`) SHALL continue to run on their normal cadence regardless of idle state — they're about disk hygiene, not activity capture.
- If ActivityWatch is unreachable or has no AFK bucket, fall back to current behavior (capture + analyze). AFK-gating is an optimization on top of the existing pipeline, not a new hard dependency.

## Capabilities

### New Capabilities
- `idle-gating`: defines when the monitor's main loop captures screenshots and runs analysis vs. skips a tick because the user is AFK per ActivityWatch. This is a new capability because the existing specs (`contextual-analysis`, `activity-discovery`, `module-structure`, etc.) describe the *pipeline* and *storage* but not the *cadence gate* in front of the pipeline.

### Modified Capabilities
<!-- None -->


## Impact

- **Code:**
  - [focusmonitor/activitywatch.py](focusmonitor/activitywatch.py) — new `get_afk_state(cfg)` helper that queries the `aw-watcher-afk_*` bucket via the existing `localhost:5600` API.
  - [focusmonitor/main.py](focusmonitor/main.py) — main loop consults AFK state before each screenshot/analysis tick; tracks idle transitions for status logging.
  - [focusmonitor/config.py](focusmonitor/config.py) — add `idle_skip_grace_sec` to `DEFAULT_CONFIG`.
- **Data:** Fewer rows written to `activity_log` during idle stretches, and fewer screenshots kept before the retention job runs. No schema changes. No migrations.
- **Privacy:** No new network surface. The AFK bucket is already served by the local ActivityWatch install; no new hosts, no new dependencies. Screenshot capture is *reduced*, which strictly improves the privacy posture (fewer images of a potentially-unlocked-but-unattended screen sitting on disk). No "Privacy impact" section required — this change moves the needle in the safer direction.
- **Tests:** Add `test_afk_gating.py` at the repo root exercising `get_afk_state` parsing and the main-loop skip decision (the latter with a thin fake for the AW helper). Follows the existing `python3 test_*.py` convention — no new framework.
