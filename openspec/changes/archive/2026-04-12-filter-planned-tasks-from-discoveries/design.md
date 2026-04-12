## Context

`discovered_activities.json` is meant to be a list of projects the monitor has observed that are *not yet* on the user's planned-tasks list — a "what else am I spending time on?" channel, meant to drive decisions about whether to promote something into `planned_tasks.json`.

Today the pipeline in [focusmonitor/analysis.py:277](focusmonitor/analysis.py#L277) passes `result["projects"]` straight into `update_discovered_activities(projects, top_titles)`. The classification prompt at [focusmonitor/analysis.py:167](focusmonitor/analysis.py#L167) asks for `"projects": ["list of projects/tasks the user was working on"]`, with no instruction to exclude planned tasks. Small local vision models (llava, llama3.2-vision) tend to play it safe: when unsure what label to invent, they echo the planned-task name back. Observed in the wild: planned task "Building and maintaining Sanskrit Study Tool" appeared as a discovered activity even though the actual work captured in window titles was clearly focus-monitor development.

Net effect today: `planned_match` and `projects` become near-duplicates, and the "Discovered Activities" card on the dashboard is cluttered with names the user already has in `planned_tasks.json`. The distinction between "LLM recognized a planned task" and "LLM discovered something new" is lost at the storage layer.

`update_discovered_activities` already has precedent for enforcing invariants at the write site — see the recently-extracted `_evict_over` helper in [focusmonitor/tasks.py:90](focusmonitor/tasks.py#L90), which makes the eviction cap impossible to bypass. That's the same shape we want for planned-task filtering.

## Goals / Non-Goals

**Goals:**
- Keep `discovered_activities.json` a pure "not on my planned list" channel. No entry whose name case-insensitively matches a currently-loaded planned task `name`.
- Enforce the invariant at the *write site* (`update_discovered_activities`), not at the caller, so no future caller can bypass it.
- Preserve `activity_log.project_detected` as an un-tampered record of what the LLM actually returned. That column is for forensic/debug purposes and anyone reading it should see the raw model output.
- Add test coverage for the new filter so regressions are caught by the existing `python3 test_*.py` suite.

**Non-Goals:**
- Retroactively cleaning up existing polluted entries in `discovered_activities.json`. The cap + eviction logic will evict them over time; a one-off migration is overkill for a file the user can edit by hand.
- Tightening the classification prompt to tell the model "don't echo planned tasks." Cheap to do, but out of scope for *this* change — adding a runtime filter is a belt-and-suspenders enforcement that must stand on its own even if the prompt is later relaxed. Tracked as a follow-up idea in the proposal but not wired into tasks here.
- Fuzzy matching (Levenshtein, substring, stemming). Case-insensitive exact match on `name` is sufficient for the observed failure mode and avoids a new "why did my activity get silently dropped?" class of bug.
- Touching `planned_match`. That field already comes from the LLM and is meant to include planned tasks — it's working as intended.

## Decisions

### Decision 1: Filter inside `update_discovered_activities`, not at the call site

**Chosen:** move the filter into `update_discovered_activities` itself. The function gains a new argument `planned_tasks` (list of dicts, same shape returned by `load_planned_tasks`), and drops any entry from `projects` whose name case-insensitively matches any planned task's `name` before the upsert loop.

**Why:**
- Matches the existing pattern of enforcing `discovered_activities.json` invariants at the write site (`_evict_over` for the cap, now planned-task filter for pollution).
- Impossible to bypass from a future call site. If someone writes a second caller tomorrow, the invariant still holds without them knowing about it.
- Testable in isolation. A unit test can drive `update_discovered_activities(["Foo", "Bar"], [], [{"name": "Foo", ...}])` without mocking the whole analysis pipeline.

**Alternatives considered:**
- **Filter at the `run_analysis` call site.** Smaller surface change — just a one-liner list comprehension before calling `update_discovered_activities`. Rejected because it leaks the invariant out of the module that owns the file. A future second caller (e.g., a batch re-classifier, a CLI tool that replays log rows) would silently break the invariant.
- **Filter inside `load_planned_tasks` or via a side channel.** Too decoupled. The contract should be "you pass me projects and the current plan; I keep the file clean."

### Decision 2: Case-insensitive exact match on `name`

**Chosen:** `project.lower() == task["name"].lower()` for each `(project, task)` pair. No substring match, no Levenshtein, no signal matching.

**Why:**
- The observed failure is the LLM echoing the exact planned-task string back verbatim, sometimes with a case drift ("Focus Monitor" vs "focus monitor"). Exact-ignore-case kills it.
- Substring matching would over-filter: a planned task "Sanskrit" would eat a newly discovered "Sanskrit Tooling Dashboard" even though those are meaningfully different.
- Signal matching (comparing projects against task `signals`) is tempting but crosses a line — signals are matching hints for the LLM's classification, not canonical names. Using them to filter discoveries would couple two unrelated concerns.

**Alternatives considered:**
- **Substring match.** Higher recall, but over-filters as above.
- **Normalize more aggressively** (strip punctuation, collapse whitespace). Probably correct eventually but YAGNI for the specific bug being fixed.

### Decision 3: `activity_log.project_detected` stays un-filtered

**Chosen:** the filter runs only on the path into `update_discovered_activities`. The `activity_log` insert at [focusmonitor/analysis.py:264](focusmonitor/analysis.py#L264) keeps writing `result["projects"]` verbatim.

**Why:** `activity_log.project_detected` is the raw model output, stored for forensic reasons (debugging prompts, auditing scores, understanding why the LLM made a decision). Filtering it would make the debug trail lie. The "clean" view the user wants is `discovered_activities.json`; the "ground truth" view is `activity_log`.

### Decision 4: Default to an empty planned-task list when the caller passes nothing

**Chosen:** `update_discovered_activities(projects, top_titles, planned_tasks=None)`. When `planned_tasks` is `None` or empty, no filtering happens — the function behaves exactly like it does today.

**Why:**
- Preserves backwards compatibility with any hypothetical caller that still uses the two-arg signature.
- Makes the unit tests for the legacy behavior continue to pass unchanged.
- Keeps the "do the right thing by default" pressure on `run_analysis`, which is the one caller that *should* always pass the current plan.

## Risks / Trade-offs

- **Risk: The LLM returns a variant spelling that exact-match misses** — e.g., "Focus Monitor (app)" vs planned "Focus Monitor". → **Mitigation:** accepted for now. If this becomes a repeating pattern, revisit with prefix match or a stemming pass. The dashboard will make it obvious (a new discovered entry that looks suspiciously like a known plan).
- **Risk: Filter silently drops a legitimate new discovery that happens to share a name with a planned task** — e.g., user plans "Research" and LLM detects a separate project called "Research". → **Mitigation:** this is the trade-off. Users who want both to coexist should rename one. Dropped names still show up in `planned_match`, so no information is lost; they just don't create a "discovered" entry.
- **Risk: `update_discovered_activities` signature change breaks a future caller that's still on two args.** → **Mitigation:** `planned_tasks` is an optional kwarg, so existing call shapes keep working at the type level. The filter only kicks in when a non-empty list is provided.
- **Risk: Reading planned tasks a second time (once in `run_analysis`, once inside `update_discovered_activities`) would double-work if we went that way.** → **Mitigation:** we're *not* going that way. The caller passes the already-loaded `planned_tasks` through; no second file read.
- **Privacy:** no new network surface, no new dependencies, no storage changes. Pure local filter over an already-local file. No privacy impact beyond "the discoveries list becomes slightly less polluted" — which is strictly better signal-to-noise without changing what leaves the machine (nothing).
