## Context

The Scope API (Phase 2) defined stats endpoints in its design. The Cycle Inspector (Phase 3) established the React + Vite scaffold. This change builds the Learning Curves view on top of both: SQL aggregation queries in the API, chart components in the UI.

The corrections table is the primary data source. It records every user correction and confirmation with: what the model said (task, confidence, evidence), what the user said (verdict, corrected task, kind), and the signals visible at the time. Combined with `activity_log` (which records every cycle regardless of correction), we can compute accuracy rates, calibration curves, and per-task performance.

## Goals / Non-Goals

**Goals:**
- Show correction rate over time (should decrease if few-shot learning works)
- Show confidence calibration (high-confidence cycles should be corrected less often than low-confidence)
- Show per-task accuracy (identify which tasks the model struggles with)
- Show few-shot impact for individual corrections (did adding correction X to the few-shot window change accuracy on similar signals?)

**Non-Goals:**
- Real-time updates (polling the API every N seconds). Manual refresh is fine.
- Statistical significance testing. Visual trends are sufficient for a learning tool.
- Exporting charts or data. This is an inspection tool, not a reporting tool.
- Adjusting model parameters from the UI. That's a code change.

## Decisions

### D1. Charts are SVG-based, starting with hand-rolled

**Decision:** Start with hand-rolled SVG elements in React components. If the complexity becomes unmanageable (especially for the calibration chart), add `recharts` as a dependency.

**Why recharts as the fallback, not d3:** recharts is a React-native charting library (components, not imperative DOM manipulation). d3 fights React's rendering model. recharts also has a much smaller bundle size than the full d3.

**Why start hand-rolled:** The correction rate chart is just rectangles in an SVG. The calibration chart is grouped bars. The per-task chart is horizontal bars. These are all achievable with basic `<rect>`, `<text>`, and `<line>` elements. Starting simple avoids the npm dependency and teaches more.

### D2. Accuracy is defined as "not corrected"

**Decision:** A cycle is "accurate" if it has no `corrected` verdict in the corrections table. A cycle with a `confirmed` verdict is also "accurate." A cycle with no correction at all is treated as "accurate" (assumption: if the user didn't correct it, it was acceptable).

**Why:** This is the only definition that works without requiring the user to confirm every cycle. The bias is toward optimism (uncorrected cycles are assumed correct), but this matches how the system is actually used: users correct mistakes and let correct results pass.

### D3. Confidence calibration uses the `name_confidence` field

**Decision:** The calibration chart groups cycles by `name_confidence` (high/medium/low) from `raw_response` and shows the fraction that were subsequently corrected.

**Why `name_confidence` over `boundary_confidence`:** Name confidence is the more actionable signal for the user. "The model was confident about the task name and was wrong" is a clearer failure mode than "the model was confident about activity coherence and was wrong."

### D4. Few-shot impact uses signal similarity

**Decision:** For a given correction, "similar" cycles are those sharing at least one `cycle_signals` workspace, terminal_cwd, or browser_host with the correction's `signals` field. The impact is: accuracy on similar cycles before vs. after the correction entered the few-shot window.

**Why this definition of similar:** It's deterministic, uses already-stored structured signals, and doesn't require embeddings or fuzzy matching. It may over-match (many unrelated cycles share "Chrome" as an app) but the workspace/cwd signals are specific enough to be useful.

**Window definition:** "Before" = cycles where this correction was NOT in the few-shot window (created_at before the correction). "After" = cycles where this correction WAS in the few-shot window (created_at after the correction, up to when it falls out of the top-N window).

### D5. View routing via simple state toggle, not a router library

**Decision:** The App component holds a `view` state (`"inspector" | "learning"`) toggled by a nav bar. No `react-router`.

**Why:** Two views don't justify a routing library. A state toggle is simpler, has no dependency, and works fine for this use case. If we add more views later, we can add routing then.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| **Not enough data for meaningful charts in the first week.** | Show an "insufficient data" message when cycle count < 10 or correction count < 3. The charts become useful after a few days of active use with corrections. |
| **Accuracy metric is biased by uncorrected cycles.** | Document the assumption clearly in the UI ("uncorrected cycles are assumed correct"). This is the standard approach for implicit feedback systems. |
| **Few-shot impact is noisy for corrections with broad signals.** | The UI shows the sample size (e.g., "12 similar cycles before, 8 after"). Small samples get a "low confidence" indicator. |
| **Privacy.** | No new data. All metrics are computed from existing tables via SQL aggregation. No new network access. |
