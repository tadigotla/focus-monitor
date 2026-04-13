## Why

The Cycle Inspector (Phase 3) answers "why did the model decide this for *this* cycle." But the deeper question — "is the system actually getting better over time?" — requires a longitudinal view across days and weeks of corrections.

The Learning Curves view answers three specific questions:
1. **Is the correction rate decreasing?** If the few-shot loop works, the model should need fewer corrections over time.
2. **Is the model's confidence calibrated?** When it says "high confidence," is it actually right more often than when it says "low"?
3. **Which tasks does it struggle with?** Some tasks (e.g., "email/comms") may be inherently ambiguous; others (e.g., "focus-monitor dev" with clear workspace signals) should be nearly perfect.

These metrics turn the corrections store from a feedback mechanism into a **measurement system** for prompt engineering effectiveness.

## What Changes

- **New stats API endpoints** added to the existing Scope API in `scope/api/queries.py` and `scope/api/server.py`. Some were stubbed in Phase 2's design; this change implements the computation logic fully.
- **New React view** in `scope/ui/` with chart components for correction rate, confidence calibration, per-task accuracy, and few-shot impact.
- **View routing** added to the React app — tab or nav switch between Cycle Inspector and Learning Curves.
- **SVG-based charts** — hand-rolled or lightweight library (recharts if hand-rolled SVG proves too painful). No d3.

## Capabilities

### Modified Capabilities
- `scope-api`: Stats endpoints fully implemented with SQL aggregation queries.
- `scope-cycle-inspector`: App gains routing between Cycle Inspector and Learning Curves views.

### New Capabilities
- `scope-learning-curves`: Interactive charts showing correction rate over time, confidence calibration, per-task accuracy, and few-shot correction impact.

## Impact

**Modified code:**
- `scope/api/queries.py` — implement/refine stats query functions
- `scope/api/server.py` — wire stats endpoints if not already wired
- `scope/ui/src/App.tsx` — add view routing (tabs or nav)
- `scope/ui/src/api/client.ts` — add typed fetch functions for stats endpoints
- `scope/ui/src/api/types.ts` — add TypeScript interfaces for stats responses

**New code:**
- `scope/ui/src/components/LearningDashboard.tsx` — container for all chart components
- `scope/ui/src/components/CorrectionRateChart.tsx` — bar chart: corrections/day over time
- `scope/ui/src/components/CalibrationChart.tsx` — grouped bars: confidence level vs actual accuracy
- `scope/ui/src/components/TaskAccuracyChart.tsx` — horizontal bars per task
- `scope/ui/src/components/FewShotImpactCard.tsx` — before/after comparison for individual corrections

**Dependencies:** Possibly `recharts` (npm, dev-only) if hand-rolled SVG is too cumbersome. Decision deferred to implementation.

**Network:** No new network access. All data from existing Scope API on localhost.

**Privacy:** No new data exposure. Stats are aggregations of data already in the local DB.
