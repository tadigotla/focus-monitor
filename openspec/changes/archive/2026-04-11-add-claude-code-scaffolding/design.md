## Context

focus-monitor is a local, privacy-first productivity tracker: all data stays in `~/.focus-monitor/`, Ollama runs locally, ActivityWatch runs locally, and the only network calls are to `localhost`. The repo has openspec wired up and a `.claude/` directory with openspec skills only — no `CLAUDE.md`, no `settings.json`, no project context populated in `openspec/config.yaml`.

The reference diagram ("Complete Claude Code Breakdown") highlights several best practices:
1. `CLAUDE.md` for persistent project instructions.
2. `.claude/settings.json` with hooks that run deterministically on tool use.
3. Organized skills (under `.claude/skills/<name>/SKILL.md`) that load only when triggered.
4. `.mcp.json` for MCP server config.
5. A three-tier memory layer (user / project / auto-memory).

Of these, the ones that actually move the needle for *this* project are the ones that enforce the privacy invariant and give future Claude sessions correct context about the local-only architecture. The memory layer already exists at the user level; parallel/self-reflection agent workflows are out of scope because the codebase is small and single-developer.

## Goals / Non-Goals

**Goals:**
- Every Claude Code session in this repo starts with correct context about the privacy invariant, macOS target, and Python/module layout — without relying on the user re-explaining it.
- Mechanically block (not just advise against) network egress from `Bash` tool calls via a PreToolUse hook.
- Project-local skills exist for the two workflows unique to this repo: privacy review and running the `test_*.py` files.
- openspec artifacts generated in the future inherit the privacy/local-first rules from `config.yaml`.

**Non-Goals:**
- Adding sub-agents, parallel workflows, or self-reflection loops from the reference image — overkill for this codebase.
- Adding real MCP servers — we keep `.mcp.json` empty/placeholder to preserve the local-only posture.
- Modifying `focusmonitor/` runtime code, tests, or dependencies.
- Building a memory layer beyond what `~/.claude/projects/.../memory/` already provides.
- Writing a new test framework or CI pipeline.

## Decisions

### 1. `CLAUDE.md` at repo root, not in `.claude/`

The reference image shows `CLAUDE.md` at the project root. Claude Code loads root `CLAUDE.md` automatically. Alternative: `.claude/CLAUDE.md` — rejected because root is the conventional, auto-loaded location.

Content will be tight (<150 lines) and cover: privacy invariant, macOS target, Python 3.10+, where config lives (`~/.focus-monitor/`), module layout, testing pattern (plain `python3 test_*.py`), and the explicit rule "no network calls except to localhost."

### 2. PreToolUse hook blocks network commands at the shell level

A hook in `.claude/settings.json` matches `Bash` tool calls and runs a short script that greps the command for patterns indicating network egress (`curl http`, `wget http`, `pip install` from non-local indexes, `requests.get(` in inline Python, etc.). If matched, the hook exits non-zero with a message pointing to `CLAUDE.md`.

Alternatives considered:
- **Prompt-only rule in CLAUDE.md** — rejected: prompts are advisory, this project's entire value prop is the privacy invariant, so it deserves mechanical enforcement.
- **PostToolUse hook** — rejected: too late, the network call already happened.
- **Pattern-match everything including reads** — rejected: too noisy; we only care about outbound network.

The hook will allow-list `localhost`, `127.0.0.1`, and `ollama` commands explicitly. Users can still override via explicit approval when Claude Code prompts them.

### 3. Populate `openspec/config.yaml` with project context and rules

The existing `config.yaml` has the `context:` and `rules:` blocks commented out. We populate them so every future openspec artifact (proposal/design/specs/tasks) inherits the privacy-first framing automatically. This is the openspec-native equivalent of CLAUDE.md for the openspec workflow.

### 4. Two project-local skills, not more

- `privacy-review` — audits a diff or file set for things that would break the privacy invariant: non-localhost URLs in strings, new outbound HTTP libraries, changes to `screenshots.py` retention, removal of `127.0.0.1` bind addresses.
- `test-focusmonitor` — runs the three `test_*.py` files at repo root and reports pass/fail.

Alternative: add skills for code-review, refactor, docs, etc. Rejected — the reference image cautions skills should be specific and trigger-loaded; generic skills duplicate what base Claude already does well.

### 5. `.mcp.json` is an empty placeholder with a comment

We add the file so future contributors see it as the documented location for MCP servers, but leave the server list empty to preserve the "nothing talks to the network" posture. An inline comment in the file explains the rationale.

## Risks / Trade-offs

- **[Hook false positives]** → The network-egress hook may block legitimate commands (e.g., `git clone` from a local path, or a curl to `localhost:1234`). Mitigation: allow-list `localhost`/`127.0.0.1`, and document in CLAUDE.md how to bypass for one-off cases by explicitly approving the tool call when prompted.
- **[Hook false negatives]** → Regex matching cannot catch every exfiltration vector (e.g., base64-encoded URLs, DNS tunneling). Mitigation: the hook is a safety net, not a security boundary. CLAUDE.md still states the invariant as primary guidance. We do not claim this hook is a sandbox.
- **[Stale CLAUDE.md]** → Root `CLAUDE.md` will drift from reality as the codebase evolves. Mitigation: keep it short and focused on invariants that rarely change (privacy, platform, language), not on per-module details that belong in code comments.
- **[Skill bloat]** → Adding skills encourages adding more skills. Mitigation: this change hard-caps at two skills and documents the bar ("unique to this repo, otherwise base Claude handles it").
- **[openspec config duplication]** → Some rules now live in both `CLAUDE.md` and `openspec/config.yaml`. Mitigation: `config.yaml` context block is a short pointer to `CLAUDE.md`; full rules live in one place.

## Migration Plan

This is additive — no migration needed. All new files; one existing file (`openspec/config.yaml`) is edited to populate previously-commented-out blocks. Rollback = delete the new files and revert `config.yaml`.

## Open Questions

- Should the PreToolUse hook run as a shell script checked into the repo, or inlined in `settings.json`? Leaning: checked-in script at `.claude/hooks/block-network.sh` so it's reviewable and testable.
- Should `privacy-review` also check `screenshots.py` retention values against `config.json` defaults? Out of scope for v1; deferred.
