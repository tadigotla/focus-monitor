## Context

Currently, `planned_tasks.txt` holds one task name per line. `load_planned_tasks()` returns a list of strings. The analysis prompt includes these as plain text, and `check_nudges()` does fuzzy substring matching against detected project names. There is no persistent record of what the AI observes — detected projects exist only in `activity_log` DB rows and are never surfaced to the user as actionable data.

## Goals / Non-Goals

**Goals:**
- Structured task definitions with matching signals for better AI classification
- Auto-populated discovered activities file as a feedback mechanism
- Smooth migration from `planned_tasks.txt` to `planned_tasks.json`
- Improved classification accuracy by giving the AI concrete signals to match against

**Non-Goals:**
- A UI for managing tasks (editing JSON files directly is fine for now)
- Automatic promotion from discovered → planned (user reviews and decides)
- Changing the database schema
- Task categories, priorities, or time estimates

## Decisions

### 1. `planned_tasks.json` format

```json
[
  {
    "name": "Sanskrit Study Tool",
    "signals": ["skt-mcp", "sanskrit", "panini", "vyakarana", "dhatu", "sutra"],
    "apps": ["VS Code", "Terminal", "Claude"],
    "notes": "Building and maintaining the Sanskrit MCP server"
  }
]
```

**Fields:**
- `name` (required): Display name for the project/task
- `signals` (optional): Keywords that indicate work on this task — matched against window titles, file names, detected projects. Case-insensitive substring matching.
- `apps` (optional): App names that are relevant. Not used for sole matching (too generic) but included as context in the prompt.
- `notes` (optional): Free-text description for the user's reference and included in the AI prompt for richer context.

**Rationale**: Signals-based matching is more reliable than matching a project name against AI-generated project descriptions. The AI can still use the name and notes for semantic understanding, but signals provide concrete anchors.

**Alternative considered**: Regex patterns for signals. Too complex for the user to write; simple substring matching covers 90% of cases.

### 2. `discovered_activities.json` format

```json
{
  "activities": [
    {
      "name": "focus-monitor development",
      "first_seen": "2026-04-11T17:23:00",
      "last_seen": "2026-04-11T18:34:00",
      "count": 4,
      "sample_signals": ["monitor.py", "dashboard.py", "focus-monitor"],
      "promoted": false
    }
  ]
}
```

**Fields:**
- `name`: AI-detected project/activity name (from `projects` in analysis output)
- `first_seen` / `last_seen`: Timestamps bounding when this activity was observed
- `count`: Number of analysis cycles that detected this activity
- `sample_signals`: Window titles, file names, or keywords associated with it (captured from ActivityWatch data during detection)
- `promoted`: User sets to `true` when they've added this to `planned_tasks.json`. Prevents re-surfacing as "new."

**Rationale**: This gives the user a running log of what the AI observes. The `sample_signals` field is key — it shows what keywords to put into a planned task's `signals` array when promoting.

### 3. Migration from `planned_tasks.txt`

On startup, if `planned_tasks.json` doesn't exist but `planned_tasks.txt` does:
1. Read each line from the text file
2. Create a JSON entry with `name` = the line text, empty `signals`, empty `apps`, no `notes`
3. Write `planned_tasks.json`
4. Rename `planned_tasks.txt` to `planned_tasks.txt.bak`
5. Print a message suggesting the user add signals to their tasks

### 4. Prompt integration

The classification prompt changes from listing plain task names to providing structured context:

```
## User's planned tasks:
  - "Sanskrit Study Tool" — signals: skt-mcp, sanskrit, panini, dhatu
    (Building and maintaining the Sanskrit MCP server)
  - "Focus Monitor" — signals: monitor.py, dashboard.py, focus-monitor
    (Local AI productivity tracker)
```

This gives the AI both semantic understanding (name + notes) and concrete matching hints (signals).

### 5. Discovery update strategy

After each analysis cycle, `update_discovered_activities()`:
1. Read `discovered_activities.json` (or create empty)
2. For each project in the analysis result's `projects` list:
   - If it matches an existing activity (case-insensitive name match): update `last_seen`, increment `count`, merge new signals
   - If it's new: add an entry with `count: 1`, `promoted: false`
3. Collect sample signals from the current ActivityWatch window titles
4. Write back to `discovered_activities.json`

**Cap**: Keep at most 50 activities. Evict oldest (by `last_seen`) non-promoted entries when full.

## Risks / Trade-offs

- **[Empty signals on migration]** → Migrated tasks have no signals, so matching quality is initially the same as before. Mitigated by the migration message prompting the user to add signals, and by the discovered activities file providing suggestions for what signals to add.
- **[JSON editing friction]** → Users must edit JSON directly instead of a simple text file. Mitigated by keeping the format minimal and including a well-commented example in the generated default file.
- **[Discovery file grows]** → Over weeks, many activities accumulate. Mitigated by the 50-entry cap and eviction of old non-promoted entries.
