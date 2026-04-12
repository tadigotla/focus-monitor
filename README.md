# Focus Monitor

Local, privacy-first AI productivity tracker for macOS. Watches your activity, classifies projects vs distractions, and nudges you when you drift.

**Everything runs on your Mac. No data leaves your machine.**

## Requirements

- macOS with Apple Silicon (M1/M2/M4)
- Python 3.10+ (no third-party packages needed — pure stdlib)
- [ActivityWatch](https://activitywatch.net/) — tracks window focus
- [Ollama](https://ollama.com/) with the `llama3.2-vision` model — local AI analysis

## Quick Start

```bash
# 1. Clone and enter the repo
git clone https://github.com/tadigotla/focus-monitor.git
cd focus-monitor

# 2. Run setup: checks dependencies, creates the launchd agent,
#    and scaffolds ~/.focus-monitor/ with default config.
python3 setup.py

# 3. Edit your planned tasks (the file exists after step 2).
nano ~/.focus-monitor/planned_tasks.json

# 4. Test manually first (also serves the live dashboard).
python3 cli.py run

# 5. Open the dashboard in your browser while the monitor is running.
open http://localhost:9876

# 6. Once happy, load the background agent so it runs at login.
launchctl load ~/Library/LaunchAgents/com.focusmonitor.agent.plist

# To stop it later:
launchctl unload ~/Library/LaunchAgents/com.focusmonitor.agent.plist
```

**One-time macOS permission**: you'll need to grant Screen Recording permission to your terminal (or the Python binary) in **System Settings → Privacy & Security → Screen Recording**. `setup.py` reminds you of this.

## How It Works

1. **Every 2 min** — takes a silent screenshot into `~/.focus-monitor/screenshots/`.
2. **Every 30 min** — pulls ActivityWatch data + recent screenshots, sends them to your local Ollama (`llama3.2-vision`) for analysis.
3. Ollama classifies your activity into projects, matches against your planned tasks, flags distractions, and assigns a focus score.
4. If a planned task hasn't been touched in 2+ hours, you get a macOS notification nudge.
5. Screenshots auto-delete after 48 hours; DB rows after 30 days.

## Config

Edit `~/.focus-monitor/config.json`:

| Key | Default | What it does |
|-----|---------|-------------|
| `screenshot_interval_sec` | 120 | How often to capture |
| `analysis_interval_sec` | 1800 | How often to analyze |
| `nudge_after_hours` | 2 | Nudge if task untouched this long |
| `screenshot_keep_hours` | 48 | Auto-delete old screenshots |
| `ollama_model` | `llama3.2-vision` | Model for analysis |
| `ollama_url` | `http://localhost:11434` | Local Ollama endpoint |
| `activitywatch_url` | `http://localhost:5600` | Local ActivityWatch endpoint |
| `screenshots_per_analysis` | 6 | Screenshots sent per analysis |
| `dashboard_port` | 9876 | Local dashboard HTTP port |
| `db_retention_days` | 30 | Auto-delete DB rows older than this |

## Security & Privacy

Focus Monitor's entire purpose is to watch what you do — so privacy is not a feature, it's the product.

**What stays on your machine:**
- All screenshots live in `~/.focus-monitor/screenshots/` and are deleted after 48 hours.
- The SQLite activity database lives in `~/.focus-monitor/activity.db`.
- Your planned tasks and config live in `~/.focus-monitor/`.
- AI classification runs against your local Ollama instance at `127.0.0.1:11434`.
- Window-focus data comes from your local ActivityWatch instance at `127.0.0.1:5600`.

**What never leaves your machine:**
- No telemetry. No analytics. No error reporting. No auto-update checks.
- No cloud LLM calls. The code contains zero references to any non-localhost host.
- The dashboard server binds to `127.0.0.1` only — not reachable from your network.

**How to verify it yourself** (takes under a minute):

```bash
# Every URL in the codebase should be localhost / 127.0.0.1
grep -rn 'https\?://' --include='*.py' focusmonitor/

# The dashboard server is loopback-bound
grep -n 'ThreadingHTTPServer' focusmonitor/dashboard.py
```

Or run the bundled `privacy-review` agent skill over the tree — see [`.claude/skills/privacy-review/SKILL.md`](.claude/skills/privacy-review/SKILL.md).

**How to wipe all your data:**

```bash
launchctl unload ~/Library/LaunchAgents/com.focusmonitor.agent.plist 2>/dev/null
rm -rf ~/.focus-monitor/
rm -f ~/Library/LaunchAgents/com.focusmonitor.agent.plist
```

That removes every byte Focus Monitor has stored about you.

## Contributing / Development

- **Agent guidance**: read [CLAUDE.md](CLAUDE.md) at the repo root. It documents the privacy invariant, the macOS/Python targets, the module layout, and the network policy enforced by the PreToolUse hook at [.claude/hooks/block-network.sh](.claude/hooks/block-network.sh).
- **Change workflow**: this repo uses [openspec](openspec/) for spec-driven changes. New work lives under `openspec/changes/<name>/`. Archived changes are under `openspec/changes/archive/`.
- **Agent skills**: project-local skills under [.claude/skills/](.claude/skills/) — `privacy-review` audits diffs for privacy regressions, `test-focusmonitor` runs the test suite.
- **Running tests**: tests live under [tests/](tests/) and run via pytest inside a local dev venv. One-time setup:
  ```bash
  python3 -m venv .venv
  .venv/bin/pip install -r requirements-dev.txt
  ```
  Day-to-day:
  ```bash
  .venv/bin/pytest tests/
  ```
  Tests are strictly offline at runtime — `pytest-socket` blocks every non-loopback connection, and cassette-backed tests for Ollama and ActivityWatch replay from committed vcrpy fixtures under `tests/cassettes/`. See `.claude/skills/test-focusmonitor/SKILL.md` for the cassette re-record sub-workflow.
- **Runtime dependencies**: pure standard library. Test-only dependencies live in [requirements-dev.txt](requirements-dev.txt) and are never imported by `focusmonitor/` runtime code. Please do not introduce third-party runtime dependencies without an explicit design discussion — see the "Privacy impact" rule in [openspec/config.yaml](openspec/config.yaml).

## License

MIT — see [LICENSE](LICENSE).
