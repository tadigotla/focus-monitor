## Context

focus-monitor has never been under version control in its current location (`/Users/adigo/code/2026/focus-monitor` has no `.git`). The owner wants to push it to a public remote. The codebase is small (~12 modules, 3 root-level test files, pure stdlib) and has a strong privacy promise baked into the product. The challenge is less "what tooling do we need" and more "don't mess this up on the first commit" — once something is in git history, redacting it is expensive and the internet may have already scraped it.

Current state of the working tree, as observed:

- No `.git` directory, no `.gitignore`.
- `__pycache__/` at repo root — Python bytecode from prior runs.
- `.DS_Store` at repo root — macOS finder metadata (leaks folder ordering, preview state).
- `.claude/` contains shared tooling (CLAUDE.md is elsewhere at root, settings.json, hooks, skills) that should be committed, but Claude Code can also drop `.claude/settings.local.json` which is per-user and should not.
- `.opencode/` — another agent tool's local state, likely per-user; needs investigation.
- `openspec/` — deliberately committed content (changes, specs, config).
- `.mcp.json` — committed, empty placeholder, fine.
- `~/.focus-monitor/` — outside the repo root, no leak risk unless someone symlinks it in.
- No `requirements.txt`, `pyproject.toml`, or `setup.cfg`. Dependencies are zero.
- No `LICENSE` file.
- README has a quick-start but no security, privacy, or contribution guidance.

## Goals / Non-Goals

**Goals:**
- The first `git add -A && git commit` on this repo produces a commit that contains only files meant for distribution, with zero secrets, absolute user paths, or local state.
- `.gitignore` is comprehensive enough that future sloppy `git add .` also stays safe.
- A first-time user can clone the repo and run one documented command to get a working install, with clear errors for missing prerequisites.
- The public README makes the privacy story (data stays local, no telemetry) verifiable — a reader should know within 60 seconds of landing on the README that nothing leaves their machine.
- A `LICENSE` exists so the repo is legally reusable.

**Non-Goals:**
- CI/CD pipelines, release automation, or version tagging.
- Publishing to PyPI or Homebrew.
- A CONTRIBUTING.md separate from the README section.
- A code of conduct or issue templates.
- Commit signing, pre-commit hooks as a separate framework, conventional commit enforcement.
- Repository splitting, subtree extractions, or history rewriting.
- Choosing the license without the owner's input — MIT is the default recommendation but the decision surfaces as an open question.

## Decisions

### 1. `.gitignore` is additive and conservative

A conservative `.gitignore` is one that ignores *classes* of local state, not specific filenames that happen to exist today. The committed `.gitignore` will cover:

- **Python build artifacts**: `__pycache__/`, `*.py[cod]`, `*.so`, `.Python`, `build/`, `dist/`, `*.egg-info/`, `.venv/`, `venv/`, `env/`.
- **macOS**: `.DS_Store`, `._*`, `.Spotlight-V100`, `.Trashes`.
- **Editors**: `.vscode/`, `.idea/`, `*.swp`, `*.swo`, `*~`.
- **Agent tool local state**: `.claude/settings.local.json`, `.claude/memory/`, `.claude/**/*.local.*`. The shared `.claude/settings.json`, `.claude/hooks/`, and `.claude/skills/` stay committed — they are part of the project's developer experience and documented in `CLAUDE.md`.
- **opencode tool local state**: TBD — investigate `.opencode/` contents and either commit the shared parts or ignore entirely. Surfacing as a task.
- **Runtime leakage guard**: `.focus-monitor/` at repo root (in case anyone symlinks or copies it in) — belt-and-braces, the real runtime data lives at `~/.focus-monitor/` outside the repo.
- **Logs and temp**: `*.log`, `*.tmp`, `tmp/`.

Alternative: a generic GitHub Python `.gitignore` template. Rejected — it pulls in 100+ lines of things that don't apply (Flask, Django, Jupyter, Poetry, pytest) and obscures what's actually being protected.

### 2. Delete pre-existing cruft before the first commit, don't ignore-and-pray

`__pycache__/` and `.DS_Store` currently exist in the working tree. Adding them to `.gitignore` does not remove them from a subsequent `git add`. They must be deleted from the filesystem before the first commit. This is a one-time cleanup step in tasks.md.

### 3. Pre-first-commit audit is one sweep with three passes

Before anyone runs `git init && git add && git commit`, do:

1. **`privacy-review` skill** against the full working tree — catches the categories it's designed for (non-localhost URLs, outbound HTTP imports, retention regressions, non-loopback binds).
2. **Grep pass** for absolute user paths (`/Users/`, `/home/`), tokens (`api_key`, `token`, `secret`, `password`, `bearer`, `authorization`), and long hex strings that look like keys.
3. **File-tree pass** for binary blobs, unexpected large files (>1MB), and anything outside the expected shape (Python source, markdown, JSON/YAML config, SKILL.md files, the hook script).

This is a one-time sweep; we're not building a permanent audit system. If the owner later wants a pre-push hook, that's a separate change. Alternative considered: automating the sweep as a new skill. Rejected — the sweep is a one-shot for first-commit, not a recurring workflow. The existing `privacy-review` skill already covers the recurring case.

### 4. "One command to setup" is `python3 setup.py`, not a new bootstrap script

`setup.py` already exists and already:
- Checks for Ollama.
- Checks for the recommended model.
- Checks for ActivityWatch.
- Reminds about Screen Recording permissions.
- Creates the launchd plist.
- Prints next-step instructions.

The friction points for a first-time user are:
- `setup.py` says the recommended model is `llama3.2-vision` but `CLAUDE.md` and older `README.md` mention `llava`. One of them is wrong — likely `README.md` is out of date. Surfacing this as an audit task.
- `setup.py` doesn't create `~/.focus-monitor/` or seed default config. `focusmonitor/config.py` does that lazily on first import via `load_config()`, which means the user won't see the config directory until they run `cli.py run`. That's fine but should be documented.
- The README quick-start tells the user to `nano ~/.focus-monitor/planned_tasks.txt` but the code has already migrated to `planned_tasks.json` (see `config.py` lines 51–64). README is stale.

Fix: walk the onboarding path in the README, fix the `llava` vs `llama3.2-vision` mismatch, fix `planned_tasks.txt` vs `.json`, and make sure the order of operations (clone → setup.py → edit tasks → run) actually works. No new bootstrap script needed; the fix is documentation + a one-line nudge in `setup.py` if a gap exists.

Alternative: a `bootstrap.sh` that wraps git clone, setup.py, and first-run. Rejected — adds a file without adding capability, and `setup.py` is the idiomatic Python entrypoint.

### 5. License default is MIT, but the owner confirms

MIT is the most permissive mainstream choice and matches the posture of a small single-developer local tool. Alternatives: Apache-2.0 (adds patent grant, more corporate-friendly), GPL-3.0 (copyleft, keeps derivatives open), BSD-3-Clause, or proprietary/no license (effectively all-rights-reserved, blocks forks).

The design recommendation is MIT; the owner's explicit confirmation is an open question. Do not commit a license without their confirmation.

### 6. README gets two new sections, not a rewrite

- **"Security & privacy"**: where data lives, what never leaves the machine, how to verify (grep the repo for `https://`, run `privacy-review`), how to wipe data (`rm -rf ~/.focus-monitor/`), and the Screen Recording permission note moved here from the setup output.
- **"Contributing / Development"**: points at `CLAUDE.md` for agent guidance, at `openspec/` for the change workflow, at `.claude/skills/` for the available tooling, and at the test-running convention (`python3 test_*.py`).

The existing Quick Start, How It Works, and Config sections stay as-is.

## Risks / Trade-offs

- **[First-commit leak]** → The whole point of the change is to prevent this; mitigation is the three-pass audit *before* `git init` is run, and an explicit stop-the-world task that says "do not proceed to git init until the audit report has zero unresolved findings."
- **[Over-ignoring]** → A too-aggressive `.gitignore` could hide files that *should* be committed (e.g., `.claude/settings.json`). Mitigation: enumerate what stays committed under `.claude/` in the design and the README's Development section, and write test cases for the .gitignore by running `git check-ignore` on each in the validation task.
- **[Stale README diverges again]** → Fixing `llava` → `llama3.2-vision` and `planned_tasks.txt` → `planned_tasks.json` today doesn't prevent tomorrow's drift. Mitigation: keep the README narrow (quick start + privacy + dev pointers), let the code be the source of truth for config keys and file formats.
- **[License choice locked in]** → Committing MIT then changing later is technically fine for the owner's own code but socially awkward if contributors have shown up. Mitigation: surface the choice as an open question; do not commit without explicit confirmation.
- **[`.opencode/` unknown contents]** → We don't know yet whether it holds shared or per-user state. Mitigation: a task to inspect before deciding to commit or ignore; if uncertain, ignore by default and document in the README how to re-enable.
- **[Audit false negative]** → Grep patterns cannot catch all secret formats (e.g., JWTs split across lines, obfuscated strings). Mitigation: the audit is best-effort; `privacy-review` catches the structural categories; the final backstop is that the codebase has zero third-party API calls to begin with, so there is no *reason* for a secret to exist in the tree.

## Migration Plan

Additive, file-level, and all work happens *before* `git init`. No migration of existing artifacts because there is no existing git history.

Rollback: delete the new files (`.gitignore`, `LICENSE`), revert `README.md`. No code rollback needed.

## Open Questions

- **License**: MIT (recommended) or something else? Apache-2.0, GPL-3.0, BSD-3-Clause, or no license?
- **`.opencode/`**: is the content shared tooling or per-user local state? Commit or ignore?
- **Remote name**: does the owner already know the remote URL, or does `git init` stand alone with the push configured later?
- **First commit message**: one commit or a series of commits that reflect the incremental history? Default is a single "Initial commit" since this is a pre-existing codebase moving to git for the first time.
- **Repository visibility**: public or private? Changes how urgent the audit is, but does not change the work.
