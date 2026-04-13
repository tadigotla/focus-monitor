## Context

Focus-monitor runs on 16 GB Apple Silicon Macs alongside the user's primary development workload. The `llama3.2-vision` model consumes ~8 GB when loaded into Ollama. With the current defaults (`analysis_interval_sec: 1800`), the model loads every 30 minutes, stays resident for ~5 minutes (Ollama's default `keep_alive`), then unloads — only to reload 25 minutes later. Combined with VS Code, Docker, and other dev tools, this pushes the system into heavy swap (observed: 4.86 GB swap on a 16 GB machine), degrading the user's primary work.

The analysis pipeline runs 7 Ollama calls per cycle (6 Pass-1 vision + 1 Pass-2 classification) and uses `recent_screenshots()` which returns only the last N screenshots. This means stretching the analysis interval without increasing `screenshots_per_analysis` creates a blind spot over the early portion of each cycle.

## Goals / Non-Goals

**Goals:**
- Reduce Ollama model residency from ~33% of wall-clock time to <10% — freeing ~8 GB of RAM for 90%+ of each hour.
- Maintain full visual coverage across analysis cycles, particularly for users who context-switch every 30 minutes.
- Make the model unload behavior configurable so users can tune the reload-latency vs. memory-pressure tradeoff.

**Non-Goals:**
- Switching to a smaller or text-only model (user values vision accuracy).
- Reducing two-pass analysis to single-pass.
- Changing the analysis pipeline logic or prompt structure.
- Optimizing CPU usage — the bottleneck is memory, not compute.

## Decisions

### D1: Use Ollama's `keep_alive` request parameter — not a global env var

**Choice**: Pass `"keep_alive"` in every `query_ollama()` API payload. Read the value from a new config key `ollama_keep_alive`.

**Alternatives considered**:
- *Global `OLLAMA_KEEP_ALIVE` env var*: Affects all models and all clients on the machine, not just focus-monitor. Too broad.
- *Hardcoded value*: No user tunability. Rejected.

**Rationale**: Per-request `keep_alive` is already supported by the Ollama `/api/generate` endpoint. It scopes the behavior to focus-monitor's calls only and is overridable by the user.

### D2: Default `keep_alive` to `"30s"`, not `"0"`

**Choice**: Default `ollama_keep_alive` to `"30s"`.

**Alternatives considered**:
- *`"0"` (immediate unload)*: Would force a full model reload between every sequential Pass-1 call in the same analysis cycle — 8 GB loaded and unloaded 7+ times in succession. Catastrophic for both latency and memory churn.
- *`"5m"` (Ollama's default)*: Keeps the model loaded too long between cycles for the target use case.

**Rationale**: 30 seconds is long enough to survive the rapid-fire burst of Pass-1 and Pass-2 calls within a single cycle (typically 1-3 minutes), but short enough that the model unloads well before the next hourly cycle.

### D3: Retune defaults to hourly analysis with 12 screenshots

**Choice**: Change `analysis_interval_sec` default from `1800` to `3600` and `screenshots_per_analysis` from `6` to `12`.

**Rationale**: `recent_screenshots()` returns the last N screenshots. With a 5-minute screenshot interval and hourly analysis, 12 screenshots covers the full 60-minute window. This yields 13 Ollama calls/hour (12 Pass-1 + 1 Pass-2), slightly fewer than the current 14 calls/hour (7 calls × 2 cycles). The coverage now includes all 30-minute context-switch boundaries instead of missing the first half of each cycle.

### D4: Increase screenshot interval default to 300s

**Choice**: Change `screenshot_interval_sec` from `120` to `300`.

**Rationale**: At 120s with hourly analysis and 12 screenshots, the system would capture 30 screenshots per hour but only analyze the last 12 — wasting 18 screenshots. At 300s, exactly 12 screenshots are captured per hour, all of which are analyzed. This also reduces disk I/O and storage churn.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Model reload adds 5-15s latency at the start of each analysis cycle | Acceptable for hourly sampling. User never waits interactively for results. |
| Existing users with saved `config.json` keep old defaults | By design — `load_config()` merges saved config over defaults. Only new installs get the new defaults. Document in change notes. |
| 30s keep-alive might be too short if Ollama is slow to respond (high system load) | The 30s timer resets on each request. Only the gap *after* the last call matters. Even under load, 30s post-last-call is generous. |
| Fewer data points per day (8-12 vs 16-24 with current defaults) | For time-distribution analysis, 8-12 hourly samples across a 10-12h workday is statistically sufficient. Real-time nudge users can lower the interval back. |
