## ADDED Requirements

### Requirement: Root CLAUDE.md SHALL document the privacy-first invariants and project conventions

The repository SHALL contain a `CLAUDE.md` at the project root that is loaded automatically by Claude Code sessions. It SHALL include, at minimum: the privacy invariant (no network calls except to `localhost`/`127.0.0.1`), the target platform (macOS on Apple Silicon), the Python version floor (3.10+), the location of runtime data (`~/.focus-monitor/`), the top-level module layout (`focusmonitor/` package plus `test_*.py` files at repo root), and the testing convention (test files run directly with `python3`).

#### Scenario: Claude Code session starts in the repo

- **WHEN** a developer opens the focus-monitor directory in Claude Code
- **THEN** Claude's loaded context includes `CLAUDE.md` and its contents state the privacy invariant, platform target, Python version, data directory, module layout, and test convention

#### Scenario: CLAUDE.md is kept concise

- **WHEN** the CLAUDE.md file is read
- **THEN** it is no longer than 150 lines and contains no per-function or per-module documentation that would rot as the code evolves

### Requirement: .claude/settings.json SHALL register a PreToolUse hook that blocks outbound network commands

The repository SHALL contain `.claude/settings.json` declaring a `PreToolUse` hook matching the `Bash` tool. The hook SHALL invoke a checked-in script that inspects the candidate command and exits non-zero if the command appears to initiate outbound network traffic to any host other than `localhost` or `127.0.0.1`. Allowed patterns SHALL include commands targeting `localhost`, `127.0.0.1`, and the `ollama` CLI.

#### Scenario: Bash command targets an external URL

- **WHEN** Claude Code is about to run a `Bash` tool call whose command contains `curl https://example.com` or `wget http://external.host/...`
- **THEN** the PreToolUse hook exits non-zero and the command is blocked with a message referencing CLAUDE.md's privacy invariant

#### Scenario: Bash command targets localhost

- **WHEN** Claude Code is about to run a `Bash` tool call whose command targets `http://localhost:5600/...` or `http://127.0.0.1:11434/...`
- **THEN** the PreToolUse hook exits zero and the command proceeds

#### Scenario: Bash command invokes ollama

- **WHEN** Claude Code is about to run a `Bash` tool call starting with `ollama ` (e.g., `ollama run llava`)
- **THEN** the PreToolUse hook exits zero and the command proceeds

### Requirement: openspec/config.yaml SHALL carry project context and rules used by openspec artifacts

The repository's `openspec/config.yaml` SHALL have the `context` block populated with a short summary of the project's privacy-first, macOS-only, local-only nature, and a pointer to `CLAUDE.md`. It SHALL have the `rules` block populated with at least one rule forbidding openspec proposals from introducing external network dependencies without explicit acknowledgment in a "Privacy impact" section.

#### Scenario: New openspec proposal is generated

- **WHEN** a contributor runs the openspec-propose workflow to create a new change
- **THEN** the context block from `openspec/config.yaml` is available to the artifact-generation step and surfaces the privacy constraint in the generated proposal

#### Scenario: Proposal introduces a new external HTTP dependency

- **WHEN** a proposal adds a dependency or call that targets a non-localhost host
- **THEN** the openspec rules require the proposal to include a "Privacy impact" section that explicitly acknowledges the deviation from the local-only invariant

### Requirement: A privacy-review skill SHALL exist at .claude/skills/privacy-review/SKILL.md

The repository SHALL contain a project-local skill at `.claude/skills/privacy-review/SKILL.md` whose frontmatter describes when to trigger it ("review a diff or file set for privacy regressions"). The skill's body SHALL instruct the reviewer to check for: non-`localhost` URLs in strings, newly imported outbound-HTTP libraries (`requests`, `httpx`, `urllib3`, `aiohttp`) that did not previously appear in the file, reductions in screenshot retention enforcement, and removal or rebinding of `127.0.0.1` bind addresses to broader interfaces.

#### Scenario: Contributor invokes the privacy-review skill on a diff

- **WHEN** a contributor asks Claude to run `privacy-review` on a set of changes
- **THEN** the skill's instructions guide Claude to report each of the documented privacy-regression categories, flagging any matches with file and line references

### Requirement: A test-focusmonitor skill SHALL exist at .claude/skills/test-focusmonitor/SKILL.md

The repository SHALL contain a project-local skill at `.claude/skills/test-focusmonitor/SKILL.md` that documents how to run the repo's existing tests: each `test_*.py` file at the repo root is executed directly via `python3 <file>` and its exit code reported. The skill SHALL NOT introduce a new test framework or modify existing test files.

#### Scenario: Contributor invokes the test-focusmonitor skill

- **WHEN** a contributor asks Claude to run `test-focusmonitor`
- **THEN** Claude runs each `test_*.py` file at the repo root via `python3`, reports pass/fail for each, and does not modify any test file

### Requirement: .mcp.json SHALL exist as an empty placeholder documenting the local-only posture

The repository SHALL contain a `.mcp.json` file whose `mcpServers` object is empty. The file SHALL contain or be accompanied by a comment (in a sibling README, in CLAUDE.md, or as a JSON-with-comments block) explaining that MCP servers are intentionally not configured to preserve the project's privacy invariant, and that any future addition requires updating CLAUDE.md and the openspec privacy rule.

#### Scenario: Contributor inspects the repository for MCP configuration

- **WHEN** a contributor opens `.mcp.json`
- **THEN** they see an empty `mcpServers` object and a documented rationale for why it is empty
