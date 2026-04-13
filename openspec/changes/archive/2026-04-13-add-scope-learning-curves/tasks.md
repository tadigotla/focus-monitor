## 1. Stats API implementation

- [x] 1.1 Implement/refine `get_correction_rate(db, days)` in `scope/api/queries.py`: SQL query that counts total cycles and corrected cycles per day for the last N days. Return list of `{date, total_cycles, corrections, rate}`.
- [x] 1.2 Implement/refine `get_confidence_calibration(db)` in `scope/api/queries.py`: group cycles by `name_confidence` (from `raw_response` JSON), LEFT JOIN to corrections, compute fraction corrected per level. Return `{high: {total, corrected, accuracy}, medium: {...}, low: {...}}`.
- [x] 1.3 Implement/refine `get_per_task_accuracy(db)` in `scope/api/queries.py`: group cycles by `task` (from `raw_response`), compute correction rate per task. Return list of `{task, total, corrected, accuracy}` sorted by total descending.
- [x] 1.4 Implement `get_few_shot_impact(db, correction_id)` in `scope/api/queries.py`: given a correction ID, find cycles with similar signals before and after the correction, compute accuracy in each window. Return `{correction_id, signal_overlap, before: {total, corrected, accuracy}, after: {total, corrected, accuracy}}`.
- [x] 1.5 Wire `GET /api/stats/few-shot-impact?correction_id=N` endpoint in `scope/api/server.py`.
- [x] 1.6 Add unit tests for each stats query function with synthetic data covering: empty DB, single correction, multiple corrections across days, mixed confidence levels.

## 2. View routing

- [x] 2.1 Add a nav bar to `App.tsx` with two tabs: "Cycle Inspector" and "Learning Curves".
- [x] 2.2 Add `view` state to App (`"inspector" | "learning"`). Toggle on tab click. Render the appropriate view component.
- [x] 2.3 Style the nav bar: minimal, fixed at top, active tab highlighted.

## 3. API client extensions

- [x] 3.1 Add TypeScript interfaces to `src/api/types.ts`: `CorrectionRatePoint`, `CalibrationData`, `TaskAccuracy`, `FewShotImpact`.
- [x] 3.2 Add fetch functions to `src/api/client.ts`: `fetchCorrectionRate(days?)`, `fetchConfidenceCalibration()`, `fetchPerTaskAccuracy()`, `fetchFewShotImpact(correctionId)`.

## 4. Learning Dashboard container

- [x] 4.1 Create `src/components/LearningDashboard.tsx` — fetches all stats on mount, passes data to child chart components. Shows loading state while fetching.
- [x] 4.2 Show "insufficient data" message when total cycle count < 10 or correction count < 3.
- [x] 4.3 Add a time range selector (7 days / 30 days / all time) that re-fetches correction rate data.

## 5. Correction Rate chart

- [x] 5.1 Create `src/components/CorrectionRateChart.tsx` — SVG bar chart showing corrections per day.
- [x] 5.2 X-axis: dates. Y-axis: correction rate (0-100%). Bars colored by rate (green low, red high).
- [x] 5.3 Show a trend line or moving average if >14 days of data.
- [x] 5.4 Hover on a bar shows tooltip with exact count: "3 corrections / 12 cycles = 25%".

## 6. Confidence Calibration chart

- [x] 6.1 Create `src/components/CalibrationChart.tsx` — grouped bar chart.
- [x] 6.2 Three groups (high / medium / low confidence). Each group shows: total cycles at that level, fraction corrected, fraction uncorrected. Stacked or side-by-side bars.
- [x] 6.3 Include sample size labels (e.g., "n=26") to indicate statistical strength.
- [x] 6.4 Ideal calibration: high confidence should have lowest correction rate, low confidence highest. Highlight if the pattern is inverted (model is miscalibrated).

## 7. Per-Task Accuracy chart

- [x] 7.1 Create `src/components/TaskAccuracyChart.tsx` — horizontal bar chart, one bar per task.
- [x] 7.2 Bars show accuracy (1 - correction rate). Sorted by total cycles descending.
- [x] 7.3 Show task name on the left, bar on the right, accuracy percentage at the end.
- [x] 7.4 Color-code: green >=90%, yellow >=70%, red <70%.
- [x] 7.5 Include an "(unrecognized)" row for cycles where `task` was null.

## 8. Few-Shot Impact card

- [x] 8.1 Create `src/components/FewShotImpactCard.tsx` — shows a before/after comparison for a selected correction.
- [x] 8.2 Display: what the correction was (model said X, user said Y), signals at the time, accuracy on similar cycles before vs. after.
- [x] 8.3 Show sample sizes and a "low confidence" indicator when sample is < 5.
- [x] 8.4 Add a selector/dropdown to choose which correction to analyze (default: most recent).
- [x] 8.5 If no corrections exist, show an explanatory message about how the few-shot loop works.

## 9. Verification

- [ ] 9.1 Start Scope API and Vite dev server. Open Learning Curves tab.
- [ ] 9.2 Verify: correction rate chart renders with data (or shows "insufficient data" message).
- [ ] 9.3 Verify: confidence calibration chart groups correctly by confidence level.
- [ ] 9.4 Verify: per-task accuracy shows all recognized tasks.
- [ ] 9.5 Verify: few-shot impact card shows before/after for a selected correction.
- [ ] 9.6 Verify: switching between Cycle Inspector and Learning Curves tabs works smoothly.
- [x] 9.7 Run the `privacy-review` skill against the diff.
