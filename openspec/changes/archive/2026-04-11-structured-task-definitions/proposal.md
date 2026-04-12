## Why

The current `planned_tasks.txt` is a flat list of task names with no structure. The AI has to guess what "Build Sanskrit Study Tool" means in terms of observable signals — which apps, window titles, or activities indicate you're working on it. This leads to vague matching and missed detections. Meanwhile, the monitor discovers many real activities but forgets them after each analysis cycle, giving you no way to see what the AI thinks you're actually doing over time.

## What Changes

- **Replace `planned_tasks.txt` with `planned_tasks.json`**: Each planned task becomes a structured object with a project name and a list of typical actions/signals (apps, keywords, file patterns) that indicate you're working on it. This gives the AI concrete matching criteria instead of fuzzy name matching.
- **Add `discovered_activities.json`** (auto-populated by the monitor): After each analysis, the monitor writes detected projects/activities to this file with metadata (first seen, last seen, frequency). This accumulates over time so you can see what the AI thinks you're actually doing.
- **Review-and-promote workflow**: You review `discovered_activities.json` and can promote entries into `planned_tasks.json` — either manually or by marking them in the discovered file. This closes the feedback loop: observe → discover → promote → track.
- **Backward compatibility**: If `planned_tasks.txt` exists and `planned_tasks.json` doesn't, auto-migrate the text entries into the JSON format with empty signals (preserving existing behavior).

## Capabilities

### New Capabilities
- `structured-tasks`: JSON-based planned task definitions with project names and matching signals
- `activity-discovery`: Auto-populated discovered activities file with observation metadata and promote workflow

### Modified Capabilities
- `contextual-analysis`: The classification prompt changes to use structured task definitions (signals) instead of plain task names for matching

## Impact

- **Config files**: `planned_tasks.txt` replaced by `planned_tasks.json` in `~/.focus-monitor/`. Old file auto-migrated on first run.
- **`discovered_activities.json`**: New file in `~/.focus-monitor/`, written after each analysis cycle.
- **monitor.py**: `load_planned_tasks()` rewritten to parse JSON. `run_analysis()` prompt updated to include signals. New `update_discovered_activities()` function. Analysis output now feeds back into discovery.
- **dashboard.py**: No changes required (reads from `activity_log` DB, not task files directly).
- **Dependencies**: None (stdlib JSON).
