## Context

focus-monitor today runs an analysis cycle every few minutes. Each cycle independently:
1. Pulls ActivityWatch events for the window.
2. Captures and de-duplicates screenshots.
3. (Optional Pass 1) Asks Ollama to describe each screenshot in 1–2 free-form sentences.
4. (Pass 2) Asks Ollama to classify the cycle into `{projects, planned_match, distractions, summary, focus_score}` and writes a row to `activity_log`.
5. The dashboard renders that row list as a flat per-cycle log with a focus-score paragraph.

Two consequences fall out of this design:

- **No temporal coherence.** Adjacent cycles representing one task — say, debugging an auth bug across VSCode, terminal, browser, and a stack overflow tab — are classified independently and often inconsistently. The user perceives the timeline as flickering nonsense even when the underlying activity is stable.
- **No verifiability.** The summary is prose. The focus score is opaque. There is no way to ask "why did you call this distraction?" or to push a correction back into the system. The user looks at the dashboard, can't tell if it's right, looks again, still can't, and disengages.

The user-facing problem is **trust**, not raw model accuracy. Solving it requires giving the model better inputs, asking it for auditable outputs, gluing per-cycle results into the unit the user actually thinks in (sessions), and closing the loop with corrections. None of this requires training a custom model — it's all prompt engineering, schema design, deterministic aggregation, and a feedback loop on top of the existing local Ollama install.

The hard constraints from `CLAUDE.md` are unchanged: macOS / Apple Silicon, Python 3.10+, stdlib-first, ActivityWatch and Ollama on localhost only, no outbound network, all user data in `~/.focus-monitor/`, no hardcoded paths, dev-only test deps stay dev-only, cassette tests offline-by-default, privacy-review every cassette diff.

## Goals / Non-Goals

**Goals:**
- Reframe the dashboard from "focus score per cycle" to **timeline of sessions with auditable evidence**.
- Make every classification claim trace back to specific observable signals (workspace, cwd, url, file, title) extracted from screenshots.
- Let the model say "I don't know" honestly via separable boundary and name confidence levels.
- Give the user a one-click correct (✏️) and confirm (✓) primitive that compounds into better future classifications via simple few-shot retrieval.
- Treat invisible work ("I was thinking") as a correction-modal option, not a separate concept.
- Preserve every existing privacy invariant; introduce zero new outbound surface and zero new runtime dependencies.

**Non-Goals:**
- Training or fine-tuning a model. We are demonstrating how far context engineering goes first.
- Embeddings, vector retrieval, or similarity-scored corrections. Most-recent-N is the v1; we measure before adding complexity.
- Retroactive bulk correction. Per-entry only in v1.
- Browser/terminal/VSCode platform-specific accessibility integrations. Vision-first across the board.
- Sharing / template packs / multi-user packaging. The self-use loop has to be solid first.
- Extending or improving `nudges.py`. It keeps working as-is.
- Removing `focus_score`. It stays in the schema for back-compat; it's just no longer the headline UI element.

## Decisions

### D1. Pass 1 returns a typed artifact, not free-form prose

**Decision:** Replace `describe_screenshots` with `extract_screenshot_artifacts` that prompts the model for a strict JSON object per screenshot:

```json
{
  "app": "VSCode" | null,
  "workspace": "focus-monitor" | null,
  "active_file": "auth.py" | null,
  "terminal_cwd": "~/code/2026/focus-monitor" | null,
  "browser_url": "github.com/.../pull/47" | null,
  "browser_tab_titles": ["PR #47", "Stack Overflow"] | null,
  "one_line_action": "editing auth.py with PR open in adjacent window"
}
```

All fields nullable except `one_line_action`. Parse with the existing multi-strategy JSON parser. On total failure, fall back to a descriptor object with only `one_line_action` populated from the raw response.

**Why over the alternatives:**
- *Free-form prose (status quo).* Vague, low-signal, the downstream classifier has nothing concrete to anchor on.
- *Multiple targeted prompts per screenshot (one per field).* 6× the Ollama round-trips per cycle. Latency cost not worth the marginal accuracy.
- *Accessibility APIs (AppleScript / AXUIElement) for browser URL, terminal cwd, VSCode workspace.* Higher accuracy but platform-specific surface area, brittle across app updates, and adds non-screenshot data paths to maintain. Defer; reach for it later only for fields the vision model keeps fumbling.

Local vision models are markedly better at "extract these exact fields" than at "describe this image." The schema constrains the output enough that the parser succeeds far more often than today.

### D2. Pass 2 schema gains evidence and **two** confidence levels, not one

**Decision:** Extend the classification JSON schema with:

```json
{
  "task": "auth refactor" | null,
  "evidence": [
    {"signal": "vscode workspace: focus-monitor", "weight": "strong"},
    {"signal": "terminal pwd matches", "weight": "strong"},
    {"signal": "github PR url", "weight": "medium"}
  ],
  "boundary_confidence": "high" | "medium" | "low",
  "name_confidence": "high" | "medium" | "low",
  "needs_user_input": false,
  "summary": "...",
  "projects": [...],
  "planned_match": [...],
  "distractions": [...],
  "focus_score": 84
}
```

The model is **explicitly instructed** that it may set `task: null`, `name_confidence: "low"`, and `needs_user_input: true` when signals are mixed. The legacy fields (`projects`, `planned_match`, `distractions`, `focus_score`) remain populated for back-compat with existing rows and the existing nudge path.

**Why dual confidence over a single score:** the user said the priority is "boundaries first, then names." Boundary confidence ("this is one coherent activity from time A to B") and name confidence ("this activity is *the auth refactor*, not just generic dev work") are distinct judgments that fail independently. The aggregator needs the first; the planned-task matcher needs the second. Collapsing them into one number forces the model to over- or under-commit.

**Why the legacy fields stay:** removing `focus_score` would force a DB migration and break the existing nudge path for no real benefit. Demoting it visually is cheap; removing it isn't. We keep the column populated and let the dashboard render it as a secondary metric (or hide it entirely — the spec deliberately leaves the visual presentation flexible).

### D3. Sessions are deterministic, not LLM-driven

**Decision:** A new `focusmonitor/sessions.py` module aggregates `activity_log` rows into sessions using deterministic rules. Inputs: ordered cycles with their structured signals and boundary confidence. Outputs: sessions with `start`, `end`, `task`, `cycle_count`, `dip_count`, and a merged evidence list.

Glue rules (v1):
1. Two consecutive cycles belong to the same session if they share **any** of: `workspace`, `terminal_cwd`, `browser_url` host, or `task` name (when both have `name_confidence >= medium`).
2. A cycle whose signals don't match the current session but lasts ≤ `session_dip_tolerance_sec` (default 300s = 5 min) is treated as a **dip** inside the parent session, not a new session.
3. AW afk events are read directly from ActivityWatch (`aw-watcher-afk`). Cycles overlapping ≥50% with afk become `away` entries, not part of any session.
4. A cycle with `name_confidence: low` and no glue match becomes its own `unclear` entry and does not merge with neighbors.

**Why deterministic over LLM-driven aggregation:**
- *Cheap and explainable.* The user can read the rule and predict the output. That's how trust gets built.
- *Tunable.* Each rule is a knob. If dip tolerance feels too generous, change one number.
- *No context-window cost.* Asking the LLM to glue across 96 cycles per day means re-paying token cost on every read, or building a separate aggregation cache anyway.
- *Robust to model hiccups.* When a single cycle misclassifies, the glue still produces the right session as long as the surrounding cycles are correct.

The trade-off is that genuinely subtle task switches (where signals shift gradually with no hard boundary) may be over-merged. Acceptable for v1; the correction UI lets the user split a session retroactively if it matters. (Splitting is the inverse correction; design.md keeps the surface area minimal by treating "wrong session boundary" as a kind of correction recorded against the offending entry.)

**Why store sessions in the DB rather than computing on every read:** the dashboard re-renders frequently, and the glue needs the structured signals from the previous N cycles. Storing the session table is a small cost that avoids re-glueing on every page load, and it gives the correction loop a stable handle (`session_id`) to attach corrections to.

### D4. Corrections live in SQLite, not a JSON sidecar

**Decision:** A new `corrections` table in the existing `~/.focus-monitor/<db>` SQLite file. Schema:

```
corrections(
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  entry_kind TEXT NOT NULL,            -- 'session' | 'cycle'
  entry_id INTEGER NOT NULL,           -- session id or activity_log id
  range_start TEXT NOT NULL,
  range_end TEXT NOT NULL,
  model_task TEXT,                     -- nullable: model said "unclear"
  model_evidence TEXT NOT NULL,        -- JSON-encoded evidence list
  model_boundary_confidence TEXT NOT NULL,
  model_name_confidence TEXT NOT NULL,
  user_verdict TEXT NOT NULL,          -- 'corrected' | 'confirmed'
  user_task TEXT,                      -- nullable: user said "thinking" / "break"
  user_kind TEXT NOT NULL,             -- 'on_planned_task' | 'thinking_offline' | 'meeting' | 'break' | 'other'
  user_note TEXT,                      -- optional free text
  signals TEXT NOT NULL                -- JSON-encoded structured signals from Pass 1
)
```

**Why SQLite over a `corrections.jsonl` sidecar:**
- The project already has `db.py` and an upgrade-on-startup pattern. Reusing it is cheaper than introducing a second persistence format.
- The few-shot retrieval needs `ORDER BY created_at DESC LIMIT N`, which is one trivial query in SQLite and a full-file read in a JSONL.
- Atomic per-row writes are free in SQLite. The JSONL would need its own atomic-append handling.
- Reads from the dashboard for "show me past corrections of this entry" are simple indexed queries.

**Why per-entry, not retroactive (locked v1 assumption):** retroactive bulk-fix sounds appealing but it's a UX rabbit hole — which entries qualify, do we re-confirm each one, what about overlapping confirmed entries, what if the user fixes a session and then a cycle inside it disagrees. Per-entry is unambiguous and ships in days, not weeks. We can layer retroactive on top later as a separate change once we have real corpus and real pain.

**Why confirmations are first-class:** without ✓ records, the system only learns from failure. Every cycle the user *doesn't* correct is positive signal that the prompt + few-shot context are working. Without that signal the system slowly drifts overcautious (the model sees only its mistakes in few-shot, never its successes, and starts hedging on similar cases). Storing confirmations costs nothing and gives the few-shot retrieval a balanced corpus.

### D5. Few-shot retrieval is "most recent N", not similarity search

**Decision:** When `build_classification_prompt` runs, it queries `corrections ORDER BY created_at DESC LIMIT N` (default `corrections_few_shot_n = 5`) and renders each as a short example block in the prompt:

```
## Recent corrections from the user
- 2026-04-11 14:15 — model said "browsing" (low name confidence). User said: working on auth refactor.
  Signals at the time: workspace=focus-monitor, cwd=~/code/2026/focus-monitor, browser_url=github.com/.../pull/47
- 2026-04-11 11:02 — model said "auth refactor" (high name confidence). User confirmed.
  Signals at the time: workspace=focus-monitor, active_file=auth.py
- ...
```

**Why most-recent-N over embedding similarity:**
- *Zero new dependencies.* No embedding model to ship, no vector index to maintain, no extra Ollama call per cycle.
- *Predictable.* The user can guess what's in the prompt window.
- *Sufficient at small corpus sizes.* For the first weeks of use, the corpus is small enough that "recent" and "similar" largely overlap.
- *Trivially upgradable later.* When the corpus grows past the point where most-recent stops being sufficient, swap the query for a similarity-ranked one. That's a one-function change; nothing about the schema or the prompt assembly needs to move.

`N` is configurable so we can tune in the first weeks of use without a code change.

### D6. The dashboard becomes a session timeline; legacy structure preserved

**Decision:** The dashboard's hero/primary zones are reorganized:
- The old "focus score card" is demoted to a small secondary stat in the header (or removed from the hero entirely — the spec leaves this flexible).
- The hero becomes a **session timeline list**: each session is a row with time range, task name (or `Unclear` / `Away`), boundary+name confidence indicators, an expandable evidence drawer, and ✏️/✓ buttons.
- The existing inline-SVG hourly heat strip stays — it's still the at-a-glance overview.
- The Discovered Activities, Top Apps, and Nudges cards are unchanged.
- All existing dashboard requirements (port, 127.0.0.1 binding, auto-refresh, htmx vendoring, CSRF lifecycle, `_mutate` choke-point, atomic writes, no outbound network) remain in force. New write endpoints flow through the same `_mutate` helper.

**Why extend rather than rewrite:** the existing dashboard infrastructure (CSRF lifecycle, mutation choke-point, htmx vendoring, design tokens, syrupy snapshot regime) is already privacy-correct and well-tested. Throwing it out to "start fresh" would cost weeks for no gain. The new endpoints and views slot into the existing patterns.

### D7. New mutation endpoints follow the existing `_mutate` contract

**Decision:** Two new endpoints under `POST /api/...`, both routed through the existing `_mutate` helper with CSRF, Host/Origin validation, and atomic writes:

| Endpoint | Required fields | Effect |
|---|---|---|
| `POST /api/sessions/<session_id>/correct` | `csrf`, `user_kind`, optional `user_task`, optional `user_note` | Inserts a `corrections` row with `user_verdict='corrected'`. Re-renders the affected session row. |
| `POST /api/sessions/<session_id>/confirm` | `csrf` | Inserts a `corrections` row with `user_verdict='confirmed'`. Re-renders the affected session row. |

For per-cycle corrections (when the user wants to fix something inside a session, not the session itself), the same endpoints accept `entry_kind=cycle&entry_id=<activity_log_id>`. v1 ships session-level only and treats per-cycle as a follow-on if needed.

### D8. Cassette discipline for the new prompt schemas

**Decision:** The structured Pass 1 prompt and the extended Pass 2 prompt each get new cassettes captured against the existing PNG fixtures under `tests/data/screenshots/`. Cassette filenames identify the prompt version (`pass1_structured_v1.yaml`, `pass2_with_evidence_v1.yaml`). Re-recording follows the existing `test-focusmonitor` skill's sub-workflow. The privacy-review checklist explicitly verifies that no real workspace path, no real file name, and no real URL appears in the recorded responses — only fixture-derived strings.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| **Local llama3.2-vision may fumble the structured Pass 1 schema and return malformed JSON more often than the prose version.** | The existing multi-strategy JSON parser already handles this case. We add a fallback that, on total failure, populates `one_line_action` from the raw response and leaves the other fields null — degrading to today's behavior, never worse. |
| **Dual confidence may push the model to hedge everything as `medium`.** | The classification prompt includes explicit anchor examples for `high` / `medium` / `low` for both confidences, and the prompt instructs the model that it is **expected** to say `low` when signals are genuinely mixed — that this is a successful, correct outcome, not a failure. |
| **Deterministic glue may over-merge.** A user who context-switches projects in the same VSCode workspace will see one giant session. | The glue rules are configurable (`session_glue_signals`). The user can correct an over-merged session by using ✏️ on it; the next analysis cycle will treat the workspace as a weaker glue signal in similar situations (via the few-shot retrieval). If this turns out to be a persistent issue, a follow-up change can add manual session split as a UI primitive — not in v1. |
| **Few-shot retrieval grows the prompt and slows Ollama.** | `corrections_few_shot_n` defaults to 5 and is configurable. Each example is short (one sentence + signal list). At N=5 the prompt grows by ~500 tokens — measured cost on llama3.2-vision is sub-second. |
| **The corrections corpus could leak personal information into cassettes.** | Cassettes are *only* captured against fixture PNGs and a clean testing AW server. The test harness fixture for corrections uses synthetic correction rows, never real user data. Privacy-review every cassette diff before committing per the project skill. |
| **Privacy.** This change introduces no new external call, no new dependency, no MCP server, no telemetry, no auto-update, no cloud LLM, and no new outbound URL. All new components bind to the existing localhost-only servers (Ollama 127.0.0.1:11434, AW localhost:5600/:5666, dashboard 127.0.0.1:9876). The corrections store lives in `~/.focus-monitor/` via paths read from `focusmonitor.config`. The privacy posture is strictly preserved; no new "Privacy impact" rationale is needed because nothing in this change reaches a non-loopback host. |
| **Migration hazard.** Adding new tables to an existing DB risks breaking older installs. | New tables are created via `CREATE TABLE IF NOT EXISTS` on startup in `db.py`'s existing schema-init path. No destructive DDL. Existing `activity_log` schema is untouched. Old rows continue to render correctly because the dashboard reads `focus_score` only as a fallback when no session entry exists for a time range. |
| **Tests for non-deterministic LLM output.** Asserting on prompt-driven JSON is brittle. | Cassette-backed tests pin the *response* deterministically; the test asserts on parsing/aggregation/storage behavior, not on what the model "should" say. Session-aggregation tests are pure-function tests on synthetic input rows, no Ollama at all. |

## Migration Plan

This is an additive change inside a single-developer tool. There is no rollout coordination, no feature flagging, and no per-user data migration to perform on third-party machines.

1. Land the spec deltas and design doc; lock the assumptions.
2. Implement Pass 1 structured extraction behind a config key (`pass1_structured: true`, default true). Old JSON parser handles both shapes. Ship and dogfood.
3. Implement Pass 2 schema extension. Old `validate_analysis_result` still produces the legacy fields; the new fields default to `null` / `low` when missing from the model response.
4. Implement `sessions.py` aggregation with no UI surface. Dump computed sessions to a debug log for one day; eyeball them.
5. Implement the corrections store. No UI yet; dashboard is unchanged.
6. Implement the timeline view + ✏️/✓ endpoints. Dashboard switches from cycle list to session list. Old activity_log rows still queryable for back-compat.
7. Wire few-shot retrieval into `build_classification_prompt`. Measure prompt size and round-trip latency for one day. Tune `corrections_few_shot_n` if needed.

**Rollback:** every step is reversible by reverting the relevant commit. The DB tables created along the way (`sessions`, `corrections`) are additive — leaving them in place after a revert is harmless. Config keys with sensible defaults mean no `config.json` migration is required.

## Open Questions

1. **Per-cycle vs. session-level corrections in v1.** The locked assumption is "per-entry"; the design ships session-level only. Is that enough, or do we need per-cycle correction inside a session from day one? Recommendation: ship session-only, see what the user asks for first. (Open to flip if the user disagrees.)
2. **`focus_score` in the new view.** Hide it entirely from the hero, demote to a small secondary stat, or keep the headline card but add session detail below it? Recommendation: demote to a secondary stat; the spec deliberately leaves the exact UI flexible so we can iterate without re-touching the spec.
3. **Manual session split.** Not in v1. If over-merging turns out to be the dominant correction type after a week, a follow-up change can add a "split here" UI primitive. v1 records a `corrected` row against the over-merged session and lets the few-shot loop carry the lesson forward.
4. **Discovery integration.** Today, projects identified by Pass 2 feed `update_discovered_activities`. With the new `task` field, do we update discoveries from `task` instead of `projects`? Or both? Recommendation: from `projects` for back-compat in v1; revisit once `task` is stable.
5. **Configurable glue rules.** Should `session_glue_signals` be a single ordered list, a per-signal weight map, or a fixed default with no user knob? Recommendation: fixed defaults in v1 with an internal `_GLUE_SIGNALS` constant; expose to config only if the user actually wants to tune it.
