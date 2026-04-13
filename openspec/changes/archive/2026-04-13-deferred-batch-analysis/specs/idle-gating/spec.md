## MODIFIED Requirements

### Requirement: Main loop gates capture on ActivityWatch AFK state

The monitor's main loop SHALL consult ActivityWatch's AFK state before each screenshot-capture tick and before each analysis tick. When the user has been AFK continuously for longer than `idle_skip_grace_sec`, the loop SHALL skip that tick (no screenshot taken, no Ollama call issued, no row written to `activity_log`).

When `batch_analysis` is `True`, AFK gating SHALL apply to collection ticks (screenshot + AW snapshot). AFK gating does not apply to batch-scheduled analysis runs, since those are triggered by clock time, not activity cadence. Cleanup / retention work SHALL run on its normal cadence regardless of AFK state.

#### Scenario: User actively working
- **WHEN** a screenshot or analysis tick fires
- **AND** the most recent `aw-watcher-afk_*` event covering the current time has `data.status == "not-afk"`
- **THEN** the loop runs the tick normally (captures the screenshot and/or runs analysis)

#### Scenario: User AFK beyond grace window
- **WHEN** a screenshot or analysis tick fires
- **AND** the most recent `aw-watcher-afk_*` event has `data.status == "afk"`
- **AND** the AFK state has been continuous for at least `idle_skip_grace_sec` seconds
- **THEN** the loop skips the screenshot capture and skips the analysis run for this tick

#### Scenario: User AFK but within grace window
- **WHEN** a tick fires and the most recent AFK event is `afk` but started less than `idle_skip_grace_sec` seconds ago
- **THEN** the loop runs the tick normally (do not skip until the grace window has elapsed)

#### Scenario: Cleanup runs regardless of AFK
- **WHEN** a cleanup cadence fires
- **AND** the user is AFK
- **THEN** `run_cleanup` SHALL still execute (DB retention and screenshot pruning are not gated on AFK)

#### Scenario: AFK gating applies to collection ticks in batch mode
- **WHEN** `batch_analysis` is `True`
- **AND** a collection tick fires while the user is AFK beyond the grace window
- **THEN** the collection tick is skipped (no screenshot, no AW snapshot, no `pending_data` row)

#### Scenario: Batch-scheduled analysis ignores AFK state
- **WHEN** `batch_analysis` is `True`
- **AND** a clock-scheduled batch time is reached
- **AND** the user is currently AFK
- **THEN** `batch_analyze()` still runs (it processes historical data, not live activity)
