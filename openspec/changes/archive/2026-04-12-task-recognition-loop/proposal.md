## Why

The current pipeline emits an isolated focus-score classification per analysis cycle with a free-form summary. In daily use this produces a timeline the developer cannot trust at a glance: classifications flicker between adjacent slices that are really one task, justifications are vague, and there is no way to say "that was wrong" in a way that improves the next run. The user-facing problem is **low confidence in the dashboard**, not low model accuracy. This change shifts the product from "score the user" to "give the user a trustworthy, correctable timeline of sessions" — the unit they actually think in — while keeping the same off-the-shelf local Ollama model. No custom training, no new external dependencies, no relaxation of the local-only invariant.

## What Changes

- **Pass 1 (screenshot description) becomes a structured extractor.** Replace the vague "describe this screenshot" prompt in `analysis.py::describe_screenshots` with one that returns a typed object: `{app, workspace, active_file, terminal_cwd, browser_url, browser_tab_titles, one_line_action}`. Most fields nullable. Local vision models are markedly better at "extract these specific fields" than free-form description, and these are exactly the high-signal artifacts the user cares about (terminal `pwd`, browser URL, VSCode workspace).
- **Pass 2 (classification) gains evidence and dual confidence.** Extend the classification JSON schema with `evidence[]` (list of `{signal, weight}`), `boundary_confidence` and `name_confidence` (each `low|medium|high`), and `needs_user_input` (bool). The model is explicitly allowed to decline a name when `name_confidence` is low. Boundary and name confidence are deliberately separable: the aggregator consumes boundary confidence, the planned-task matcher consumes name confidence.
- **Sessions become the primary unit.** A new deterministic aggregation layer glues consecutive analysis cycles that share enough signal (same workspace / repo / terminal cwd / browser url) into one session, allowing short dips without breaking it. Task-switch boundaries are surfaced explicitly. AW's afk module is used to split "active but unclear" from "away" — the model is never asked to infer presence.
- **Corrections and confirmations are first-class.** A persistent store records, per timeline entry: timestamp range, what the model said (task + evidence + confidence), what the user said (corrected task + optional reason), and the structured signals visible at the time. Confirmations (✓) are stored in the same shape as corrections (✏️) so the system learns from success as well as failure.
- **Per-entry only for v1 (locked assumption).** Corrections affect only the entry that was corrected. No retroactive bulk-fix of similar past entries. Bulk retroactive correction is deferred to a later change if it proves necessary.
- **Few-shot retrieval from corrections feeds Pass 2.** `build_classification_prompt` includes the N most recent corrections and confirmations as few-shot examples ("in similar past situations, user said X"). Configurable N, default 5. No embeddings, no similarity scoring — measure first, add complexity only if warranted.
- **Dashboard view becomes a session timeline with inline correction UI.** Replace the focus-score paragraph view with a timeline of sessions showing time range, task name (or `Unclear` / `Away`), boundary+name confidence indicators, expandable evidence list, and ✏️/✓ controls. The correction modal also handles invisible work ("Thinking / reading offline on [task]", "Meeting (no screenshare)", "Break / lunch") as correction options rather than a separate concept.
- **`focus_score` is demoted but not removed.** Existing analysis-log writes continue to populate `focus_score` for backwards compatibility with existing rows; it just stops being the headline UI element. No data migration required.

Explicitly out of scope (deferred to later changes):
- Nudges. `nudges.py` keeps working as-is; not extended here.
- Sharing / template packs for other developers. Deferred until the self-use loop is solid.
- Embeddings / vector retrieval / similarity-scored corrections. Ship most-recent-N first, measure, then revisit.
- Fine-tuning / LoRA / training a custom model. The whole point of this change is to demonstrate how far context engineering goes before any training is required.
- Retroactive bulk correction (per the locked assumption above).
- Browser/terminal/VSCode platform-specific accessibility integrations. Vision-first across the board; revisit only if specific fields keep coming back wrong.

## Capabilities

### New Capabilities
- `session-aggregation`: Deterministic glue layer that merges consecutive analysis cycles sharing workspace/repo/url/cwd signal into coherent sessions, preserves short-dip tolerance, and surfaces task-switch boundaries. Uses AW afk to distinguish active-but-unclear from away.
- `correction-loop`: Persistent corrections + confirmations store, the per-entry write/read API used by the dashboard, and the few-shot retrieval that feeds the most recent N corrections back into the Pass 2 classification prompt.

### Modified Capabilities
- `contextual-analysis`: Pass 1 (screenshot description) becomes structured extraction returning a typed artifact instead of free-form prose.
- `structured-analysis`: Pass 2 classification schema gains `evidence[]`, `boundary_confidence`, `name_confidence`, and `needs_user_input`. Validation and parse-retry logic updated to match. The model is explicitly allowed to decline a task name when name confidence is low.
- `dashboard-server`: View shifts from per-cycle classification list to a session timeline with confidence indicators, expandable evidence, and correction/confirmation endpoints. New write endpoints follow the same atomic-write pattern as the existing planned-task and discovered-activity helpers.

## Impact

**Affected code (focusmonitor/):**
- `analysis.py` — `describe_screenshots`, `build_classification_prompt`, `parse_analysis_json`, `validate_analysis_result`, `run_analysis` all change. New aggregation step inserted between `run_analysis` and dashboard read paths.
- `db.py` — new table(s) for the corrections/confirmations store and (likely) for persisted sessions. Existing `activity_log` schema unchanged.
- `dashboard.py` (top-level entrypoint) and `focusmonitor/dashboard.py` — timeline view rewrite, new write endpoints for ✏️/✓.
- `tasks.py` — corrections store mutation helpers follow the existing atomic-write pattern.
- `config.py` — new tunables: `corrections_few_shot_n`, `session_dip_tolerance_sec`, `session_glue_signals`.
- New module(s): `focusmonitor/sessions.py`, `focusmonitor/corrections.py` (or fold corrections into `tasks.py` if cleaner — design.md decides).

**Affected data (~/.focus-monitor/):**
- New SQLite tables in the existing DB. No new top-level files; corrections live in the DB rather than a sidecar JSON for query-ability.
- Existing files (`config.json`, `planned_tasks.txt`, `discovered_activities.json`, screenshot cache) untouched.

**Tests:**
- New cassette-backed tests for the structured Pass 1 prompt and the extended Pass 2 schema. Cassettes captured against the existing PNG fixtures under `tests/data/screenshots/` — never personal data — and privacy-reviewed before commit per the `test-focusmonitor` re-record sub-workflow.
- New unit tests for `sessions.py` (deterministic glue, no Ollama).
- New unit tests for `corrections.py` (write/read/retrieval).
- Dashboard syrupy snapshot regenerated for the new timeline view; the snapshot diff lands in the same PR as the template change.

**Dependencies:** None added. Pure stdlib + existing dev-only test deps.

**Network:** None added. All new components are localhost-only and the `pytest-socket` allow-list is unchanged. No new outbound HTTP target is introduced anywhere in this change. (No "Privacy impact" section is required because nothing in this change reaches a non-loopback host.)

**Privacy invariants preserved:**
- Corrections store lives in `~/.focus-monitor/` via `focusmonitor.config` paths — never hardcoded.
- New cassettes captured exclusively against fixture PNGs and the testing AW server (`:5666`); never against production data.
- Privacy-review the diff (especially any new cassette) before committing per the project skill.

**Backwards compatibility:** Existing `activity_log` rows remain readable. `focus_score` continues to be written. Old DB instances upgrade by creating the new tables on first run; no destructive migrations.
