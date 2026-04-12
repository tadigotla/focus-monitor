## ADDED Requirements

### Requirement: Repository SHALL contain a comprehensive .gitignore at the root

The repository SHALL contain a `.gitignore` file at the project root that ignores Python build artifacts, macOS finder metadata, common editor metadata, per-user agent-tool state, and the runtime data directory. The ignore patterns SHALL be expressed as classes of files (globs), not as specific filenames that happen to exist at a point in time.

#### Scenario: Running `git status` on a fresh clone with stray local files

- **WHEN** a developer clones the repository and then incidentally creates `__pycache__/`, `.DS_Store`, `.venv/`, `.vscode/settings.json`, or `~/.claude/settings.local.json`-equivalents inside the repo
- **THEN** `git status` reports the tree as clean (no untracked files), because the `.gitignore` matches each of these paths

#### Scenario: Shared Claude Code tooling remains committed

- **WHEN** a developer runs `git check-ignore -v .claude/settings.json`, `.claude/hooks/block-network.sh`, or `.claude/skills/privacy-review/SKILL.md`
- **THEN** `git check-ignore` exits non-zero for each (meaning the file is NOT ignored), because the shared tooling is part of the developer experience and is distributed with the repo

### Requirement: Repository SHALL contain no committed Python bytecode, macOS metadata, or per-user agent state at first-commit time

Before the initial `git commit`, the working tree SHALL NOT contain `__pycache__/` directories, `.pyc`/`.pyo` files, `.DS_Store` files, or any file that the `.gitignore` would otherwise match. These artifacts SHALL be deleted from the filesystem, not merely ignored, so they cannot appear in the initial commit.

#### Scenario: Running the pre-commit cleanup

- **WHEN** the owner runs the documented cleanup step before the initial commit
- **THEN** `__pycache__/` and `.DS_Store` are deleted from the repository root and from any subdirectory, and a subsequent `find . -name __pycache__ -o -name .DS_Store` returns no results

### Requirement: Repository SHALL pass a three-pass privacy and secrets audit before the initial commit

Before running `git init` or the initial `git commit`, the repository SHALL pass three audits without unresolved findings: (a) the `privacy-review` skill over the full working tree, (b) a grep pass for absolute user paths (`/Users/`, `/home/<user>/`) and secret-shaped strings (`api_key`, `token`, `secret`, `password`, `bearer`, `authorization`), and (c) a file-tree pass for unexpected binary blobs, files larger than 1 MB, and files outside the expected shape (Python, markdown, JSON/YAML config, shell scripts).

#### Scenario: Audit finds an absolute user path

- **WHEN** the grep pass finds a string like `/Users/adigo/code/2026/focus-monitor/...` embedded in a Python source file or a markdown file
- **THEN** the finding is reported to the owner and the initial commit is blocked until the path is either removed, genericized (e.g., `~/.focus-monitor/`), or explicitly marked as an intentional example

#### Scenario: Audit finds a non-localhost URL in source

- **WHEN** the `privacy-review` skill reports a non-`localhost` URL in a tracked source file that is not a docstring reference to an upstream project
- **THEN** the finding is reported and the initial commit is blocked until the URL is removed or the owner explicitly approves it

#### Scenario: Audit finds zero issues

- **WHEN** all three passes complete with no unresolved findings
- **THEN** the owner is explicitly notified that the repository is cleared for `git init`, and only then does the initial commit proceed

### Requirement: Repository SHALL contain a LICENSE file at the root

The repository SHALL contain a `LICENSE` file at the project root whose text matches a recognized open-source license (MIT, Apache-2.0, BSD-3-Clause, GPL-3.0, or equivalent). The specific license SHALL be chosen by the owner; the default recommendation is MIT. A repository without a LICENSE file SHALL NOT be pushed to a public remote.

#### Scenario: License is committed before the first public push

- **WHEN** the initial commit is prepared
- **THEN** it includes a `LICENSE` file whose first line identifies the license and whose copyright line names the owner and the year

#### Scenario: License choice is surfaced to the owner

- **WHEN** the implementation reaches the license step
- **THEN** the implementation explicitly asks the owner to confirm the license choice before writing the file, and does not silently default

### Requirement: README.md SHALL contain a Security & privacy section and a Contributing section

The repository's `README.md` SHALL contain a **Security & privacy** section that a reader can find within 60 seconds of landing on the file. The section SHALL state (a) that no data leaves the user's machine, (b) where data is stored (`~/.focus-monitor/`), (c) how a user can wipe their data, and (d) how a skeptical reader can verify the claim (grep for non-localhost URLs, run the `privacy-review` skill).

The README SHALL also contain a **Contributing / Development** section pointing at `CLAUDE.md`, the `openspec/` workflow, the `.claude/skills/` tooling, and the test convention (each `test_*.py` run directly via `python3`).

#### Scenario: New user lands on README

- **WHEN** a user opens `README.md` for the first time
- **THEN** a "Security & privacy" section is visible in the table of contents (or in the first screen of the rendered markdown) and states that all data stays local, with a `~/.focus-monitor/` reference and a wipe command

#### Scenario: Contributor wants to hack on the code

- **WHEN** a contributor reads the Contributing section
- **THEN** they are pointed at `CLAUDE.md`, the `openspec/` workflow, the `.claude/skills/` tooling, and the test convention, and can reach all four from relative links in the README

### Requirement: README.md onboarding instructions SHALL match the current code

The README's Quick Start section SHALL reference the actual filenames, model names, and commands that the codebase uses at the time of the commit. In particular, it SHALL reference `planned_tasks.json` (not the deprecated `planned_tasks.txt`) and the model name configured in `focusmonitor/config.py` (`llama3.2-vision` as of this change, not `llava`).

#### Scenario: README instructs on editing planned tasks

- **WHEN** a user follows the README's Quick Start to edit their planned tasks
- **THEN** the README tells them to edit `~/.focus-monitor/planned_tasks.json`, and the command shown matches the actual file the code reads

#### Scenario: README references the AI model

- **WHEN** the README names the Ollama model to pull
- **THEN** the name matches the `ollama_model` default in `focusmonitor/config.py`

### Requirement: A first-time user SHALL be able to clone, setup, and run with one documented command sequence

A user with macOS, Python 3.10+, Ollama, and ActivityWatch already installed SHALL be able to go from `git clone` to a running monitor by running at most three commands: `git clone <url> && cd focus-monitor`, `python3 setup.py`, and `python3 cli.py run`. The README SHALL document this sequence and SHALL tell the user exactly what to do when any preflight check in `setup.py` fails (missing Ollama, missing model, missing ActivityWatch, missing Screen Recording permission).

#### Scenario: User with prereqs installed runs setup.py

- **WHEN** a user with Ollama, the recommended model, and ActivityWatch already installed runs `python3 setup.py`
- **THEN** the script reports all preflight checks as passing, creates the launchd plist, and prints next-step instructions that match the README

#### Scenario: User is missing the recommended model

- **WHEN** a user without `llama3.2-vision` pulled in Ollama runs `python3 setup.py`
- **THEN** the script reports the missing model with the exact `ollama pull` command and does not silently continue as if the check passed
