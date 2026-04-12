## Context

The project is currently 4 top-level Python files: `monitor.py` (845 lines, 7 functional areas), `dashboard.py` (392 lines), `cli.py` (80 lines), and `setup.py` (118 lines). All state (config, paths, DB) is managed through module-level globals and a `cfg` dict passed through function calls. There are no classes — everything is pure functions.

## Goals / Non-Goals

**Goals:**
- Each functional area in its own module, independently editable
- Clear import boundaries — no circular dependencies
- Preserve the pure-functions style (no unnecessary classes)
- All 80 existing tests pass without logic changes

**Non-Goals:**
- Adding a plugin system or dynamic loading
- Introducing dependency injection or abstract interfaces
- Changing any behavior, config format, or external API
- Adding new features

## Decisions

### 1. Package layout: `focusmonitor/`

```
focusmonitor/
├── __init__.py          # Package marker, re-exports main() for convenience
├── config.py            # Path constants, DEFAULT_CONFIG, load_config(), migration
├── db.py                # init_db()
├── activitywatch.py     # get_aw_events(), summarize_aw_events()
├── screenshots.py       # take_screenshot(), recent_screenshots(), deduplicate_screenshots()
├── ollama.py            # encode_image(), query_ollama()
├── analysis.py          # parse_analysis_json(), validate_analysis_result(),
│                        # describe_screenshots(), get_recent_history(),
│                        # build_classification_prompt(), run_analysis()
├── tasks.py             # load_planned_tasks(), update_discovered_activities(),
│                        # _task_matches_projects()
├── nudges.py            # check_nudges(), send_nudge()
├── cleanup.py           # cleanup_old_screenshots(), cleanup_old_db_rows(),
│                        # cleanup_log_files(), run_cleanup()
├── dashboard.py         # Dashboard HTML generation + HTTP server (moved from root)
└── main.py              # main() loop only
```

**Rationale**: Mirrors the `# ── Section ──` markers already in `monitor.py`. Each module corresponds to one section, making the split mechanical and predictable.

**Alternative considered**: Grouping by layer (data/services/ui). Over-engineered for a single-user local tool with ~1400 lines total.

### 2. Shared state via `config.py`

All path constants (`CONFIG_DIR`, `DB_PATH`, `SCREENSHOT_DIR`, `TASKS_JSON_FILE`, `DISCOVERED_FILE`, `LOG_DIR`) live in `config.py`. Other modules import them:

```python
from focusmonitor.config import DB_PATH, TASKS_JSON_FILE
```

`DEFAULT_CONFIG` and `load_config()` also live in `config.py`. The `cfg` dict continues to be passed as a function parameter — no global config singleton.

### 3. Import dependency graph (no cycles)

```
config ← db ← cleanup
  ↑       ↑       ↑
  |    analysis ←──┘
  |    ↑   ↑
  |    |   screenshots
  |    |   ↑
  |    |   ollama
  |    |
  |    tasks
  |    ↑
  |    nudges
  |
  activitywatch
  |
  dashboard
  |
  main (imports everything)
```

Each module imports only from modules above it in the graph. `main.py` is the only module that imports from all others.

### 4. Backward-compatible top-level `monitor.py`

Keep a thin `monitor.py` at the root that re-exports `main` for backward compatibility with existing launchd plists:

```python
from focusmonitor.main import main
if __name__ == "__main__":
    main()
```

### 5. Test import updates

Tests change from `from monitor import X` to `from focusmonitor.module import X`. The test files themselves don't move.

## Risks / Trade-offs

- **[Import path changes break launchd]** → Mitigated by keeping the thin `monitor.py` wrapper at the root. Existing plists continue to work.
- **[Circular imports]** → Mitigated by the strict dependency graph above. Each module only imports from modules it depends on, never the reverse.
- **[Test updates]** → All test files need import path changes. Mechanical but must be thorough.
