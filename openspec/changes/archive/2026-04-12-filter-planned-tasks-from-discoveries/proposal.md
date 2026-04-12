## Why

The "discovered activities" channel is meant to surface projects the monitor observed that are **not already** on the user's planned-tasks list — so the user can see what else they're spending time on and decide whether to promote it. Today the pipeline at [focusmonitor/analysis.py:277](focusmonitor/analysis.py#L277) passes `result["projects"]` straight into `update_discovered_activities`, and `result["projects"]` routinely contains planned-task names because:

1. The classification prompt at [focusmonitor/analysis.py:167](focusmonitor/analysis.py#L167) asks for `"projects": ["list of projects/tasks the user was working on"]` without instructing the model to exclude planned tasks.
2. Small local vision models (llava, llama3.2-vision) tend to echo the planned-task list back into `projects` when they are not confident inventing a new label.

Observed concretely: a user working on `focus-monitor` with one planned task ("Building and maintaining Sanskrit Study Tool") saw that planned task appear as a discovered activity on the dashboard, even though the captured window-title signals (`Focus Monitor`, `ActivityWatch`, `monitor`, `spec.md`, `design.md`) correctly reflected the real work. The signals were right; the label was the planned task verbatim.

Net effect: the discoveries list is polluted by planned tasks, `planned_match` and `projects` become near-duplicates, and the user cannot distinguish "new thing the monitor learned" from "planned thing the LLM echoed."

## What Changes

- In `run_analysis`, before calling `update_discovered_activities`, filter `result["projects"]` to drop any entry whose name case-insensitively matches a loaded planned-task `name`.
- Keep `result["projects"]` as-is when written to `activity_log.project_detected` — that column is the raw LLM output and other code paths may still want to see everything the model observed.
- Add a test scenario in `test_structured_tasks.py` (or a new `test_discovery_filter.py`) that exercises the filter: given planned task "Focus Monitor" and LLM `projects: ["Focus Monitor", "Sanskrit Tool"]`, only "Sanskrit Tool" should be passed to `update_discovered_activities`.
- Optional (if cheap): tighten the prompt wording at [focusmonitor/analysis.py:167](focusmonitor/analysis.py#L167) to explicitly say "projects the user worked on, including planned tasks and any other projects you observed" so `projects` and `planned_match` have clearer semantics. Then the runtime filter is a belt-and-suspenders enforcement of the spec, not a cleanup of a sloppy prompt.

## Capabilities

### New Capabilities
<!-- None -->

### Modified Capabilities
- `activity-discovery`: clarifies that `discovered_activities.json` SHALL only contain project names that do not match a currently-loaded planned task (case-insensitive). Needs a new scenario or a MODIFIED requirement — design phase decides.

## Impact

- **Code:** [focusmonitor/analysis.py](focusmonitor/analysis.py) (one call-site filter in `run_analysis`, optional prompt tweak). Possibly [focusmonitor/tasks.py](focusmonitor/tasks.py) if we prefer to push the filter into `update_discovered_activities` instead — decision for design phase.
- **Data:** Existing `discovered_activities.json` entries that duplicate planned tasks are not migrated — they remain until evicted by the cap, or the user hand-deletes them. A one-off cleanup is out of scope.
- **Privacy:** No new network surface, no new dependencies. Pure local filter.

## Related

- Observed during implementation of `add-discovered-activities-dashboard`, which first made the issue visible to the user.
- Interacts with `fix-all-promoted-eviction` only in that both touch `update_discovered_activities` call path; they can land independently.
