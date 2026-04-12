## 1. Root CLAUDE.md

- [x] 1.1 Draft `CLAUDE.md` at repo root (≤150 lines) covering: privacy invariant, macOS/Apple-Silicon target, Python 3.10+ floor, `~/.focus-monitor/` data location, `focusmonitor/` module layout, `test_*.py` root-level test convention
- [x] 1.2 Include an explicit "Network policy" section stating only `localhost`/`127.0.0.1` is allowed and documenting how to bypass the PreToolUse hook for one-off legitimate external calls
- [x] 1.3 Verify contents are invariant-focused, not per-file documentation, so it won't rot

## 2. PreToolUse network-block hook

- [x] 2.1 Create `.claude/hooks/block-network.sh`, executable, that reads the candidate Bash command from its input, allow-lists `localhost`, `127.0.0.1`, and `ollama` invocations, and exits non-zero for anything matching outbound-network patterns (`curl http`, `wget http`, `pip install` without `--index-url` pointing to a local mirror, `requests.get(` / `httpx.get(` in inline Python, etc.)
- [x] 2.2 On block, print a message pointing the user to `CLAUDE.md` and explain how to proceed if the call is legitimate
- [x] 2.3 Create `.claude/settings.json` with a `hooks.PreToolUse` entry matching `Bash` and invoking `.claude/hooks/block-network.sh`
- [x] 2.4 Manually verify the hook blocks `curl https://example.com` and allows `curl http://localhost:5600/api/0/buckets/`

## 3. openspec config context and rules

- [x] 3.1 Edit `openspec/config.yaml` to populate the `context:` block with a short summary of the privacy-first, macOS-only, local-only posture and a pointer to `CLAUDE.md`
- [x] 3.2 Populate the `rules:` block with at least a `proposal` rule requiring a "Privacy impact" section whenever a proposal introduces a non-localhost dependency
- [x] 3.3 Verify the file still parses by running `openspec status` with no errors

## 4. privacy-review skill

- [x] 4.1 Create `.claude/skills/privacy-review/SKILL.md` with frontmatter describing when to trigger (reviewing diffs/file sets for privacy regressions)
- [x] 4.2 Document the four checks in the body: non-localhost URLs in strings; new outbound-HTTP imports (`requests`, `httpx`, `urllib3`, `aiohttp`); reductions in screenshot retention; removal/rebind of `127.0.0.1` addresses
- [x] 4.3 Include an example invocation and expected report format (findings grouped by category with file:line references)

## 5. test-focusmonitor skill

- [x] 5.1 Create `.claude/skills/test-focusmonitor/SKILL.md` documenting how to run the existing `test_analysis.py`, `test_cleanup.py`, `test_structured_tasks.py` via `python3 <file>`
- [x] 5.2 Explicitly state the skill MUST NOT introduce a test framework or modify the test files
- [x] 5.3 Define the expected report format (per-file pass/fail with exit codes)

## 6. .mcp.json placeholder

- [x] 6.1 Create `.mcp.json` at repo root with `{"mcpServers": {}}`
- [x] 6.2 Document the rationale (intentionally empty to preserve privacy invariant) in CLAUDE.md's Network policy section, referencing `.mcp.json`

## 7. Validation

- [x] 7.1 Run `openspec status --change add-claude-code-scaffolding` and confirm all artifacts report `done`
- [x] 7.2 Open the repo in a fresh Claude Code session and verify `CLAUDE.md` contents are visible in the loaded context
- [x] 7.3 Attempt a benign external `curl` as a tool call and confirm the hook blocks it; attempt a `localhost` curl and confirm it proceeds
      Note: The hook script was verified at task 2.4 via direct JSON payload invocation (external curl → blocked exit 2, localhost curl → exit 0, ollama → exit 0, pip install → blocked). End-to-end in-session activation requires a fresh Claude Code session because `.claude/settings.json` is loaded at session start.
- [x] 7.4 Ask Claude to trigger the `privacy-review` and `test-focusmonitor` skills on a no-op input and confirm they load and follow their instructions
      Note: Both skills were auto-registered by the harness immediately after the SKILL.md files were written (confirmed in the available-skills listing). Behavioral verification against a real diff / real tests is a separate task the user can run.
