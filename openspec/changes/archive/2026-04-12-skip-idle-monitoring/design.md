## Context

focus-monitor's main loop in [focusmonitor/main.py](focusmonitor/main.py) runs unconditionally on wall-clock ticks: every `screenshot_interval_sec` (default 120s) it captures a screenshot, and every `analysis_interval_sec` (default 1800s) it calls `run_analysis` which invokes Ollama. The loop has no notion of whether the user is actually *at* the Mac. When the user steps away, the pipeline happily burns Ollama cycles classifying the lock screen / screensaver / static desktop as "idle" — dragging trend history, filling the screenshot directory, and writing rows that the dashboard then renders as if they were real activity.

ActivityWatch already solves the "is the user here?" question: `aw-watcher-afk` (installed alongside the window watcher) writes events to a bucket named `aw-watcher-afk_<hostname>`. Each event has a timestamp, duration, and `data.status ∈ {"afk", "not-afk"}`. We already hit `localhost:5600` for window events (see [focusmonitor/activitywatch.py](focusmonitor/activitywatch.py)); querying the AFK bucket is the same API, same host, zero new network surface.

The change is small and contained: one helper in `activitywatch.py`, one guard in `main.py`, one new config key. The loop structure, cleanup cadence, and all downstream analysis stay identical.

## Goals / Non-Goals

**Goals:**
- Skip screenshot capture and analysis when ActivityWatch reports the user has been AFK for longer than a grace window.
- Keep the privacy posture at least as strong as today (fewer screenshots is strictly better, not worse).
- Degrade gracefully: if ActivityWatch is unreachable or the AFK bucket is missing, behave exactly like today.
- Make idle vs. active state visible to the user in the console output so a silent monitor doesn't look like a broken monitor.
- Preserve cleanup/retention regardless of idle state — disk hygiene is orthogonal to activity capture.

**Non-Goals:**
- Writing our own idle detector (`CGEventSourceSecondsSinceLastEventType`, `ioreg`, etc.). ActivityWatch is already running and already correct.
- Skipping *dashboard* refreshes when idle. The dashboard is read-only over historical data and costs ~nothing to keep serving.
- Inferring "user is in a meeting on a different device" or any other semantic beyond "the keyboard/mouse has been still per aw-watcher-afk."
- Retroactively scrubbing historical `activity_log` rows that were written during past idle stretches.
- Configurable AFK detection thresholds at the ActivityWatch layer — that's a property of the user's AW install, not ours to override.

## Decisions

### Decision 1: Use ActivityWatch's AFK bucket instead of rolling our own idle detector

**Chosen:** query `aw-watcher-afk_<host>` via the same `localhost:5600` API we already use for window events.

**Why:** ActivityWatch is already a hard runtime dependency for this tool and already runs an AFK watcher by default on macOS. Reimplementing idle detection means shelling out to `ioreg` or linking `Quartz`/`AppKit`, which is more code, more platform risk, and produces a *second* source of truth that can disagree with the one the user can already inspect in the ActivityWatch UI. Reusing AW's signal means "if AW thinks you're here, so do we" — one concept, one debug path.

**Alternatives considered:**
- `ioreg -c IOHIDSystem | awk '/HIDIdleTime/ ...'` subprocess call. Works but needs parsing, runs every tick, and introduces a new shell dependency. Rejected.
- PyObjC / Quartz `CGEventSourceSecondsSinceLastEventType`. Correct but adds a PyObjC dependency, which is a bigger ask than "query an endpoint we already hit."

### Decision 2: Grace window before skipping

**Chosen:** add `idle_skip_grace_sec` (default 60s). Only skip a tick when the user has been AFK continuously for at least the grace window.

**Why:** aw-watcher-afk flips to `afk` after ~180s of input silence by default, but users sometimes read long documents or watch a video for a minute without touching input — we don't want to blip to "idle" and miss the tick where they come back. The grace window gives us a dead zone where we *trust* AW's transition before acting on it. 60s is comfortably shorter than the default 120s screenshot interval, so one missed screenshot at most during a legitimate return.

**Alternatives considered:**
- Hard cutoff (skip immediately when AFK). Too jumpy; can interact badly with AW's own debounce.
- Hysteresis (skip after N consecutive AFK ticks). More state, same effect as a time-based grace. Time is simpler.

### Decision 3: Fail-open on ActivityWatch unavailability

**Chosen:** if the AFK bucket can't be queried (AW down, bucket missing, network error), log a one-time warning and fall through to the current behavior — capture and analyze as before.

**Why:** the existing `get_aw_events` already returns `[]` and prints a warning on AW failure; the analysis pipeline already tolerates empty AW data. Mirroring that pattern keeps the failure mode predictable. The alternative ("fail closed" = never capture when AFK state is unknown) would silently turn the tool off for users whose AW install drifts, which is a bad user experience for a best-effort optimization.

**Alternatives considered:**
- Fail closed (no AFK info → assume idle → skip). Rejected: turns the tool into a brick on AW hiccups, which is disproportionate for an optimization.
- Cache the last-known AFK state and reuse it for N minutes if AW becomes unreachable. Extra state for marginal benefit; rejected.

### Decision 4: Gate both screenshots and analysis, but not cleanup

**Chosen:** the AFK gate wraps the screenshot-capture branch and the analysis branch in `main.py`. It does NOT wrap `run_cleanup`.

**Why:** screenshots and analysis are the expensive, user-facing work the user is complaining about. Cleanup is a local SQLite DELETE + a file unlink loop, costs nothing, and protects disk quota regardless of whether the user is at their desk. Conflating them would create a weird failure mode where the screenshot directory grows unbounded during a long idle stretch because the retention job was also gated off.

### Decision 5: Status line on transitions, not every tick

**Chosen:** print `💤 idle — skipping capture` on the first skipped tick of an idle stretch, and `▶️  resumed` on the first non-idle tick after. Don't print anything on every skipped tick.

**Why:** silence is load-bearing here — the user's complaint is that the tool *does* stuff when it shouldn't. But the user also needs to distinguish "deliberately idle" from "crashed." A transition-only status line achieves both: visible signal when state changes, quiet when the state is stable.

## Risks / Trade-offs

- **Risk:** aw-watcher-afk uses a 180s debounce by default, so there's a window of ~3 minutes after the user walks away where the monitor still captures. → **Mitigation:** acceptable. Matching AW's threshold means we inherit its (well-tuned) definition of AFK; trying to undercut it with a tighter heuristic would just disagree with the user's ActivityWatch UI. Document the lag in the config comment.
- **Risk:** User manually kills aw-watcher-afk → every tick looks "not AFK" → behavior is identical to today. → **Mitigation:** none needed; this is the correct fail-open behavior.
- **Risk:** User's AW bucket is named non-standardly (different hostname quirks, multiple buckets). → **Mitigation:** the helper scans all buckets for the `aw-watcher-afk` prefix, same loop style already used in `get_aw_events`.
- **Risk:** Clock skew between `datetime.now()` and AW's event timestamps causes a tick to misclassify. → **Mitigation:** we already use `datetime.now(timezone.utc)` when talking to AW; keep that, and compare the most recent event's `[timestamp, timestamp+duration]` against `now` with a small tolerance.
- **Privacy trade-off:** None. No new external calls, no new dependencies, no new data written to disk. Screenshots and Ollama calls are strictly *reduced* during idle stretches — that is, the change moves the privacy needle in the right direction. Recording this row per the design-phase privacy rule: the only network I/O added is a GET against `http://localhost:5600/api/0/buckets` and a POST to `http://localhost:5600/api/0/query/`, both of which we already make elsewhere in the same file.
- **Trade-off:** Users who want "record everything, even idle" lose that behavior by default. → **Mitigation:** they can set `idle_skip_grace_sec` to a very large number (e.g., `86400`) to effectively disable the gate, or explicitly set it to `0` to treat any AFK as an immediate skip. We should document both extremes in the config comments alongside the default.
