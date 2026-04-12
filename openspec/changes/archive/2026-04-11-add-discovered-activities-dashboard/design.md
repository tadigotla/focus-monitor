## Context

Today, `update_discovered_activities` is called from [focusmonitor/analysis.py:277](focusmonitor/analysis.py#L277) at the end of each analysis cycle, writing to `~/.focus-monitor/discovered_activities.json`. The dashboard ([focusmonitor/dashboard.py](focusmonitor/dashboard.py)) reads only from SQLite (`activity_log`, `nudges`) and knows nothing about this file. Users who want to see what the AI has discovered have to `cat` the JSON.

There is also no test coverage for `update_discovered_activities` — the upsert, the 10-signal cap, the 50-entry cap, and the promoted-entry protection are all specified in `openspec/specs/activity-discovery/spec.md` but never exercised. A recent bug in that logic would be silent.

This change does both: a small read-only addition to the dashboard, and a verification test that pins the existing behavior to the spec.

## Goals / Non-Goals

**Goals:**
- Show discovered activities on the dashboard so users can see what the monitor is learning and decide which to promote.
- Provide direct test coverage that `discovered_activities.json` is being populated per spec (new entry, upsert, signal merge, cap, eviction, promoted protection).
- Keep the change fully local and stdlib-only.

**Non-Goals:**
- Interactive promotion (a button to move a discovered activity into `planned_tasks.json`) — out of scope; the user still edits the JSON by hand.
- Historical trends for discovered activities (sparklines, count-over-time) — not enough data to be useful yet.
- Migrating `discovered_activities.json` into SQLite — file-based JSON is the current contract with the user who may hand-edit it; no reason to break that.
- Changing any existing `update_discovered_activities` behavior. The test is purely a verification pass; if it finds a divergence from spec, that is a bug report, not part of this change.

## Decisions

**Decision 1: Read the JSON file at render time, not via a new DB table.**
- Rationale: The file is small (≤50 entries), rendering is already synchronous, and the user is expected to hand-edit `promoted`. Introducing a DB mirror would create a sync problem for no benefit.
- Alternative considered: Load once at server start and cache. Rejected — the monitor thread updates this file every analysis cycle, and the dashboard already re-queries SQLite on every request, so consistency beats a negligible perf win.

**Decision 2: Render discovered activities as a new section below the timeline, not inside the stats grid.**
- Rationale: The stats grid is for "at-a-glance today" numbers; discovered activities are a running catalogue, structurally closer to the timeline than to the cards.
- Alternative considered: A fourth stat card with just the count. Rejected — the count alone doesn't give the user anything actionable; they need to see names and signals to decide on promotion.

**Decision 3: Tolerate missing/empty/malformed JSON silently.**
- Rationale: The dashboard must not crash because of a bad user edit. Matches existing behavior in `load_planned_tasks` which returns `[]` on any parse failure.
- Approach: A dedicated `_load_discovered_activities()` helper in `dashboard.py` that returns `[]` on `FileNotFoundError`, `json.JSONDecodeError`, or `OSError`.

**Decision 4: Test verification uses repo-root `test_*.py` pattern, not pytest.**
- Rationale: CLAUDE.md explicitly forbids adding a test framework without an openspec change. The existing pattern is `python3 test_foo.py` with `tempfile`/monkey-patching.
- Approach: `test_discovered_activities.py` follows [test_structured_tasks.py](test_structured_tasks.py) — monkey-patch `focusmonitor.config.DISCOVERED_FILE` to a temp path, drive `update_discovered_activities`, and assert the resulting JSON.

**Decision 5: Test covers each scenario in `activity-discovery/spec.md` explicitly.**
- Rationale: The user asked for "thorough verification." Pinning each scenario gives both regression coverage and spec/code traceability.
- Scenarios to cover:
  1. New activity detected → entry added with `count: 1` and `promoted: false`.
  2. Known activity detected again → `count` increments, `last_seen` updates, signals merge without duplicating.
  3. First run with no file → file is created with an `activities` array.
  4. Sample signals extracted from window titles → keywords parsed from `—`/`-`/`|`/`:` splits, capped at 10.
  5. Cap reached with non-promoted entries → oldest non-promoted (by `last_seen`) evicted.
  6. All entries promoted → oldest overall evicted.
  7. Promoted flag preserved across upserts.

## Risks / Trade-offs

- **[Risk] A user hand-edit between reads corrupts the file** → Mitigation: the loader catches `json.JSONDecodeError` and renders an empty section with an "unreadable" hint. The writer in `update_discovered_activities` already does `write_text(json.dumps(...))` atomically enough for single-writer use; not in scope to change.
- **[Risk] The verification test finds the existing code actually diverges from the spec** → Mitigation: treat that as a finding, not a test failure to suppress. The tasks.md explicitly flags this possibility and asks the implementer to stop and report before patching, so the fix can be scoped as its own change.
- **[Risk] Rendering ~50 entries with ~10 signals each expands the page** → Mitigation: signals render as small pill chips; the entire section is one simple card, cheap to draw. No virtualization needed at this scale.
- **[Privacy] New external calls or dependencies** → None. This change only reads an existing local file and renders it on a page already bound to 127.0.0.1. No new network surface, no new packages.
