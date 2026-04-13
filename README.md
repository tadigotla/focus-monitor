# Focus Monitor

Local, privacy-first AI productivity tracker for macOS. Watches your activity, classifies projects vs distractions, and nudges you when you drift.

**Everything runs on your Mac. No data leaves your machine.**

## Requirements

- macOS with Apple Silicon (M1/M2/M4)
- Python 3.10+ (no third-party packages needed — pure stdlib)
- [ActivityWatch](https://activitywatch.net/) — tracks window focus
- [Ollama](https://ollama.com/) with the `llama3.2-vision` model — local AI analysis

## Quick Start

### Prerequisites (one-time, on a fresh Mac)

Skip this block if you already have Ollama running with `llama3.2-vision`
pulled and ActivityWatch installed and running.

```bash
# Install Ollama and start the daemon. Pick ONE of:
brew install ollama && brew services start ollama
#   or: download the Ollama desktop app from https://ollama.com/ and launch it

# Pull the vision model used by focus-monitor (~7.8 GB, one-time download).
ollama pull llama3.2-vision

# Install ActivityWatch. Pick ONE of:
brew install --cask activitywatch
#   or: download from https://activitywatch.net/ and drag to /Applications/

# Launch ActivityWatch so it starts tracking window focus.
open /Applications/ActivityWatch.app
```

**macOS Screen Recording permission (required, one-time):**

Before the first run, grant Screen Recording permission to the terminal
you'll use to launch focus-monitor:

1. Open **System Settings → Privacy & Security → Screen Recording**.
2. Add your terminal app (Terminal.app, iTerm2, Ghostty, etc.) to the
   allow-list.
3. Quit and relaunch the terminal so the permission takes effect.

Without this, `screencapture` produces black PNGs and the AI sees
nothing.

### Install focus-monitor

```bash
# 1. Clone and enter the repo.
git clone https://github.com/tadigotla/focus-monitor.git
cd focus-monitor

# 2. Run setup. This probes Ollama + ActivityWatch and scaffolds
#    ~/.focus-monitor/ with default config. If either service is down
#    or missing, setup prints the exact fix-it command — re-run setup
#    after fixing. setup.py does NOT write the launchd plist; that's
#    owned by `cli.py service install` in step 6.
python3 setup.py

# 3. Edit your planned tasks.
nano ~/.focus-monitor/planned_tasks.json

# 4. Test in the foreground (starts Pulse + Scope, embeds the dashboard).
#    Ctrl-C tears both down.
python3 cli.py start

# 5. Open the dashboard in your browser while focus-monitor is running.
open http://localhost:9876

# 6. Once happy, install and start the background services so they run at login.
python3 cli.py service install
python3 cli.py service start

# To stop them later:
python3 cli.py service stop

# To see per-component state:
python3 cli.py service status
```

### Verifying your install

After `setup.py` reports everything green and `cli.py start` is alive
for at least one analysis interval (~30 minutes by default, or edit
`~/.focus-monitor/config.json` to lower `analysis_interval_sec`), run
these quick checks:

```bash
# 1. Ollama is reachable and has the expected model.
curl -s http://localhost:11434/api/tags | grep llama3.2-vision

# 2. ActivityWatch is reachable and in production mode.
curl -s http://localhost:5600/api/0/info

# 3. Pulse's dashboard is reachable.
curl -s http://localhost:9876 | head -1

# 4. Scope's API is reachable.
curl -s http://localhost:9877/api/health

# 5. An activity row has landed in the database.
sqlite3 ~/.focus-monitor/activity.db \
  "SELECT timestamp, substr(summary, 1, 60) FROM activity_log ORDER BY timestamp DESC LIMIT 5;" \
  2>/dev/null || echo "No rows yet — wait for the first analysis tick."

# 6. (Optional, for contributors) Run the pytest suite — fully offline,
#    requires the dev venv set up via the Contributing section below.
.venv/bin/pytest tests/
```

If steps 1 and 2 return data but step 5 is empty, `cli.py start` hasn't
reached its first analysis tick yet — leave it running and try again.

## Upgrading from the old launchd agent

If you installed focus-monitor before the `cli.py service` verbs
existed, your `~/Library/LaunchAgents/` still has
`com.focusmonitor.agent.plist` pointing at the deleted `monitor.py`.
launchd will respawn-loop that plist on every pull until you remove
it. Run these commands **before** the usual upgrade steps:

```bash
# 1. Unload the legacy agent (bootout is preferred on modern macOS).
launchctl bootout gui/$(id -u)/com.focusmonitor.agent 2>/dev/null || \
  launchctl unload ~/Library/LaunchAgents/com.focusmonitor.agent.plist

# 2. Remove the legacy plist file.
rm ~/Library/LaunchAgents/com.focusmonitor.agent.plist

# 3. Install the new per-component plists and start them.
python3 cli.py service install
python3 cli.py service start
```

There is no automatic migration. The manual recipe is a deliberate
choice — the upgrade touches user-shared launchd state, and the
explicit commands are auditable and reversible. `cli.py service
install` will detect the legacy plist if you forget and print the
same recipe.

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
# Primary path: use the CLI (stops and removes both plists).
python3 cli.py service uninstall
rm -rf ~/.focus-monitor/

# Fallback, if you can't run cli.py:
launchctl bootout gui/$(id -u)/com.focusmonitor.pulse 2>/dev/null
launchctl bootout gui/$(id -u)/com.focusmonitor.scope 2>/dev/null
rm -f ~/Library/LaunchAgents/com.focusmonitor.pulse.plist
rm -f ~/Library/LaunchAgents/com.focusmonitor.scope.plist
rm -rf ~/.focus-monitor/
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
