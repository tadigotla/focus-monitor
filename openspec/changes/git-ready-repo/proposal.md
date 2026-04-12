## Why

The repository has no `.git`, no `.gitignore`, an uncommitted `.DS_Store`, a root-level `__pycache__/` directory, and no pre-push audit of what's about to become public history. The owner wants to push it to a remote. We need to (a) make sure nothing that shouldn't be committed ends up in the first commit, (b) give first-time users a frictionless clone-to-running experience, and (c) preserve the privacy-first invariant when the repo is public — the README and docs already promise "no data leaves your machine", and the public repo should make that claim easy to verify from the code itself.

## What Changes

- Add a `.gitignore` at the repo root covering: Python build artifacts (`__pycache__/`, `*.py[cod]`, `*.egg-info`, `.venv/`, `venv/`, `build/`, `dist/`), macOS cruft (`.DS_Store`, `._*`), common editor metadata (`.vscode/`, `.idea/`, `*.swp`, `*.swo`), Claude Code per-user state that should not be shared (`.claude/settings.local.json`, `.claude/memory/`), and the user's runtime data directory in case someone symlinks it into the repo (`.focus-monitor/`).
- Delete the committed-by-accident artifacts that already exist in the working tree (`.DS_Store`, `__pycache__/`) before the first commit, and document that cleanup in tasks.
- Audit the repository for secrets, absolute user paths, and privacy leaks before any commit is made. This is a one-shot sweep invoking the existing `privacy-review` skill plus a grep pass for tokens, API keys, and hard-coded `/Users/<name>/` paths.
- Extend `setup.py` (or add a sibling `bootstrap.sh`) so a first-time user can clone, run one command, and get a working install with all preflight checks (Ollama present, required model pulled, ActivityWatch installed, Screen Recording permission hint, `~/.focus-monitor/` scaffolded). `setup.py` already does most of this — the change is to make the "one command" story explicit in the README and fix any remaining gaps uncovered by walking the path on a fresh machine mentally.
- Update `README.md` with a **Contributing / Development** section pointing at `CLAUDE.md`, the openspec workflow, and the `.claude/skills/` tooling, and with a **Security & privacy** section that tells users where their data lives and what the repo does *not* collect.
- Add a `LICENSE` file. Without a license the code is legally not open source; pushing it public without one is a trap for anyone who wants to fork. Default to MIT unless the owner says otherwise — the decision is surfaced in design.md as an open question, not hardcoded.

Non-goals: setting up GitHub Actions, publishing to PyPI, adding a CONTRIBUTING.md beyond a README section, writing a code-of-conduct, configuring branch protection. All of those can follow once the repo is actually pushed.

## Capabilities

### New Capabilities
- `git-repository-hygiene`: The set of files and procedures that must exist before the repository is pushed to a public remote — `.gitignore`, `LICENSE`, a pre-commit privacy audit, and README sections covering setup and security — plus the rule that no absolute user paths or secrets appear in tracked files.

### Modified Capabilities
- `cli-entrypoint`: If `setup.py` grows new preflight checks (a fresh-machine path-walk may uncover gaps), the CLI entrypoint spec needs a delta. Only include this section in specs if the fresh-machine audit actually surfaces a gap; otherwise leave empty.

## Impact

- **New files**: `.gitignore`, `LICENSE`.
- **Modified files**: `README.md` (Contributing + Security & privacy sections), possibly `setup.py` (only if the audit surfaces a gap).
- **Deleted files** (from the working tree, pre-first-commit): `.DS_Store`, `__pycache__/`.
- **No runtime code changes** in the `focusmonitor/` package — this is repo hygiene, not product work.
- **No new runtime dependencies.** The project remains pure standard library.
- **Privacy impact**: None. The change strengthens the privacy posture by making the public repo easier to audit. No new external calls, no new data collection. `.gitignore` ensures that local state (Claude memory, editor caches, user data) cannot be accidentally committed.
- **Developer impact**: A first-time clone becomes `git clone && python3 setup.py && edit ~/.focus-monitor/planned_tasks.json`. Contributors get a clear pointer to `CLAUDE.md` and the openspec workflow.
