## Why

The focus-monitor repo has `.claude/commands/opsx` and `openspec-*` skills, but lacks the foundational Claude Code scaffolding that the "Complete Claude Code Breakdown" reference recommends: a root `CLAUDE.md`, a `settings.json` with hooks, populated `openspec/config.yaml` project context, and project-specific skills. Adding these gives every future Claude session consistent context about the privacy-first, macOS-only, local-only nature of this project — so it stops making wrong assumptions (e.g., suggesting cloud LLM calls) and can run guardrails automatically instead of relying on prompts.

## What Changes

- Add a root `CLAUDE.md` documenting project conventions: privacy invariants (no network except localhost), macOS/Apple-Silicon target, Python 3.10+ style, module layout under `focusmonitor/`, and testing patterns used in `test_*.py`.
- Add `.claude/settings.json` with a `PreToolUse` hook that blocks `Bash` commands making external network calls (enforcing the privacy invariant mechanically, not just via prompt).
- Populate `openspec/config.yaml` `context` and `rules` blocks so every openspec artifact inherits the privacy/local-first constraints.
- Add two project-local skills under `.claude/skills/`:
  - `privacy-review` — audits a diff for privacy regressions (non-localhost URLs, data egress, screenshot retention).
  - `test-focusmonitor` — runs the existing `test_*.py` files with the project's test patterns.
- Add `.mcp.json` placeholder documenting which MCP servers (if any) are expected; leave empty by default to preserve the "nothing leaves the machine" posture.

Non-goals: defining sub-agents, adding CI, adding new product features.

## Capabilities

### New Capabilities
- `claude-code-scaffolding`: Files and configuration that Claude Code reads on session start (CLAUDE.md, settings.json, .mcp.json, openspec config context) plus project-local skills that enforce this project's privacy/local-first invariants.

### Modified Capabilities
<!-- None — this change adds new scaffolding without altering existing spec requirements. -->

## Impact

- **New files**: `CLAUDE.md`, `.claude/settings.json`, `.mcp.json`, `.claude/skills/privacy-review/SKILL.md`, `.claude/skills/test-focusmonitor/SKILL.md`.
- **Modified files**: `openspec/config.yaml` (populate `context` and `rules`).
- **No code changes** in `focusmonitor/` — this is tooling/config only.
- **No runtime dependencies** added. The hook uses stock shell tooling.
- **Developer impact**: future Claude sessions in this repo inherit privacy constraints automatically; the PreToolUse hook will block (and require explicit override) commands that look like network egress, which may occasionally be a friction point and is documented in CLAUDE.md.
