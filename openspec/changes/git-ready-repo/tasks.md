## 1. Pre-commit audit (must pass before anything else)

- [x] 1.0 **In-scope fix surfaced by 1.1**: deleted the Google Fonts `@import` from `focusmonitor/dashboard.py`. Existing `sans-serif` / `monospace` fallbacks now handle rendering — no external CSS fetch from the user's browser on dashboard view.
- [x] 1.1 Run the `privacy-review` skill over the full working tree and capture findings by category
- [x] 1.2 Grep the tree for absolute user paths: `/Users/`, `/home/<user>/` (anywhere outside `openspec/changes/archive/`). Report every match as `file:line`
      Result: zero matches in `focusmonitor/`, `.claude/`, or root-level scripts. All matches were meta-references inside `openspec/changes/git-ready-repo/` documenting the audit itself.
- [x] 1.3 Grep the tree for secret-shaped strings: `api_key`, `token`, `secret`, `password`, `bearer`, `authorization`, and long hex runs (case-insensitive). Report every match
      Result: zero matches in code. "token(s)" matches in archived proposals are about LLM input tokens. No long hex runs anywhere.
- [x] 1.4 List every file over 1 MB and every non-text file in the tree. Flag anything unexpected
      Result: no file over 50kB. The only binary is `.DS_Store` at repo root (scheduled for deletion in task 4.2).
- [x] 1.5 Produce a combined audit report and STOP if there are any unresolved findings — do not proceed to any file creation, cleanup, or git work until findings are resolved or explicitly waived by the owner
      Result: one finding (Google Fonts leak in `focusmonitor/dashboard.py`) surfaced and resolved as task 1.0 by deleting the `@import` line. Audit cleared; proceeding.

## 2. Investigate unknowns before writing .gitignore

- [x] 2.1 Inspect `.opencode/` contents and decide whether it is shared tooling (commit) or per-user state (ignore). Record the decision in design.md as a resolved open question
      Result: `.opencode/` mirrors `.claude/` — contains the same openspec-workflow commands (`opsx-*.md`) and skills (`openspec-*`) for the opencode CLI. Shared tooling. **Decision: commit.** Also found `.github/prompts/` and `.github/skills/` — the same openspec scaffolding for GitHub Copilot. Also commit.
- [x] 2.2 Confirm there are no other agent-tool directories we haven't accounted for (`.cursor/`, `.aider/`, `.continue/`, etc.). If any exist, decide commit vs. ignore per directory
      Result: no other agent-tool directories present. Only `.claude/`, `.opencode/`, `.github/`.

## 3. Create .gitignore

- [x] 3.1 Write `.gitignore` at repo root covering: Python artifacts (`__pycache__/`, `*.py[cod]`, `*.so`, `.Python`, `build/`, `dist/`, `*.egg-info/`, `.venv/`, `venv/`, `env/`), macOS (`.DS_Store`, `._*`, `.Spotlight-V100`, `.Trashes`), editors (`.vscode/`, `.idea/`, `*.swp`, `*.swo`, `*~`), Claude local state (`.claude/settings.local.json`, `.claude/memory/`, `.claude/**/*.local.*`), opencode decision from task 2.1, runtime leakage guard (`.focus-monitor/`), and logs/temp (`*.log`, `*.tmp`, `tmp/`)
      Note: per task 2.1, `.opencode/` and `.github/` are committed (shared tooling), so they are NOT in the ignore list.
- [x] 3.2 Explicitly leave the following uncommitted-but-shared paths OUT of the ignore list (they must stay trackable): `.claude/settings.json`, `.claude/hooks/`, `.claude/skills/`, `.mcp.json`, `openspec/`, `CLAUDE.md`
- [ ] 3.3 Dry-run verification: run `git check-ignore -v` against each of the paths in 3.2 (they MUST NOT be ignored) and against each of `__pycache__/foo.pyc`, `.DS_Store`, `.vscode/settings.json`, `.claude/settings.local.json` (they MUST be ignored). Deferred to task 8.3 once `git init` has been run.

## 4. Delete committed-by-accident artifacts

- [x] 4.1 Delete every `__pycache__/` directory in the tree (`find . -name __pycache__ -type d -prune -exec rm -rf {} +`, but confirm the find pattern first)
      Result: removed `./__pycache__/` and `./focusmonitor/__pycache__/`.
- [x] 4.2 Delete every `.DS_Store` in the tree
      Result: removed `./.DS_Store` (the only one).
- [x] 4.3 Confirm no other files match the new `.gitignore` patterns after cleanup
      Result: zero matches for `*.pyc`, `*.pyo`, `._*`, `*.swp`, `*.log`, `.env`, `*.pem`, `*.key`, or any of the editor/venv directory patterns.

## 5. License

- [x] 5.1 Ask the owner which license to use (default recommendation: MIT). Do not skip this step
      Result: owner chose MIT. Copyright holder: Harikishore Tadigotla. GitHub handle: tadigotla.
- [x] 5.2 Write `LICENSE` at repo root with the owner's chosen license text, correct copyright year, and owner name
      Result: MIT license written with "Copyright (c) 2026 Harikishore Tadigotla".
- [x] 5.3 Verify the first line of the file identifies the license unambiguously
      Result: first line is "MIT License".

## 6. First-time-user onboarding path walk

- [x] 6.1 Re-read `README.md` end to end and flag every instruction that no longer matches the code: the `llava` vs `llama3.2-vision` model name, the `planned_tasks.txt` vs `planned_tasks.json` file name, and the dashboard command
      Result: 6 mismatches flagged — model name (lines 11, 52), planned tasks file (line 23), run command (line 26), dashboard command (line 32), config table (line 52). Fixed in task 7.
- [x] 6.2 Re-read `setup.py` and confirm the preflight checks match the README. Fix mismatches in the README, not the code, unless the code is actually wrong
      Result: `setup.py` checks for `llama3.2-vision` — matches the code, not the README. README was wrong; fixed in task 7.
- [x] 6.3 Walk through a fresh-machine mental simulation: clone → `python3 setup.py` → edit planned tasks → `python3 cli.py run`. Note every place a first-time user would get stuck. Fix each by editing the README
      Result: main stuck-point is that `~/.focus-monitor/` does not exist after `setup.py` (created lazily by `load_config()` on first run), so the user cannot edit `planned_tasks.json` in the correct order. Fixed in task 6.4 via a `setup.py` one-liner.
- [x] 6.4 If `setup.py` has a genuine gap (not a doc gap), add a narrow fix and note it as an out-of-scope follow-up if it's larger than a one-liner
      Result: added a single import + `load_config()` call at the end of `setup.py` main to bootstrap `~/.focus-monitor/` with defaults. This makes the README order valid (setup → edit planned tasks → run).

## 7. Update README.md

- [x] 7.1 Fix the `planned_tasks.txt` → `planned_tasks.json` reference in Quick Start
- [x] 7.2 Fix the model name reference to match `focusmonitor/config.py`
- [x] 7.3 Add a **Security & privacy** section stating: no data leaves the machine, data lives in `~/.focus-monitor/`, how to wipe (`rm -rf ~/.focus-monitor/`), and how to verify (grep for `https://`, run `privacy-review`)
- [x] 7.4 Add a **Contributing / Development** section pointing at `CLAUDE.md`, `openspec/`, `.claude/skills/`, and the `python3 test_*.py` test convention
- [x] 7.5 Confirm the Quick Start, How It Works, and Config sections still match the code after edits
      Result: Quick Start now uses `cli.py run`, `llama3.2-vision`, `planned_tasks.json`, and dashboard URL `http://localhost:9876`. Config table adds `ollama_url`, `activitywatch_url`, `dashboard_port`, `db_retention_days` rows and corrects `ollama_model` default. All values verified against `focusmonitor/config.py`.

## 8. Initialize git and verify

- [x] 8.1 Run `git init` in the repo root
- [x] 8.2 Run `git status` and confirm the untracked file list contains only files the owner intends to commit — no `__pycache__/`, no `.DS_Store`, no `.claude/settings.local.json`, no `.opencode/` unless explicitly chosen
      Result: 17 top-level entries, all expected. No ignored paths leaked in.
- [x] 8.3 Run `git check-ignore -v` against the four ignored-path samples and the six must-be-tracked paths from 3.2 and 3.3. All must behave correctly
      Result: 9 must-be-tracked paths confirmed untracked by .gitignore; 7 must-be-ignored paths confirmed ignored with the correct matching rule. 16/16 pass.
- [x] 8.4 Stage everything with `git add -A` and run `git diff --cached --stat` to get a final file list for owner review
      Result: 103 files staged, 8688 insertions. Owner review pending in task 8.5.
- [ ] 8.5 Show the file list to the owner, ask for explicit approval, and only then make the initial commit

## 9. Post-commit verification

- [ ] 9.1 Run `git log --stat` on the initial commit and confirm no surprises
- [ ] 9.2 Run the `privacy-review` skill one more time against the committed tree (belt and braces)
- [ ] 9.3 If the owner provided a remote URL, stop and confirm before pushing. Do not push without explicit approval
