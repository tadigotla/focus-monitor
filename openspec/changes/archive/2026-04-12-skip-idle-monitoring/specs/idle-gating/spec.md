## ADDED Requirements

### Requirement: Main loop gates capture on ActivityWatch AFK state

The monitor's main loop SHALL consult ActivityWatch's AFK state before each screenshot-capture tick and before each analysis tick. When the user has been AFK continuously for longer than `idle_skip_grace_sec`, the loop SHALL skip that tick (no screenshot taken, no Ollama call issued, no row written to `activity_log`). Cleanup / retention work SHALL run on its normal cadence regardless of AFK state.

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

### Requirement: Fail-open when AFK state is unknown

The system SHALL treat "AFK state cannot be determined" as equivalent to "user is active" and SHALL NOT skip ticks on the basis of missing data.

#### Scenario: ActivityWatch unreachable
- **WHEN** the query to `http://localhost:5600` fails with a network error
- **THEN** the AFK helper returns a sentinel meaning "unknown"
- **AND** the main loop runs the tick normally (fail-open)
- **AND** the helper logs a single warning line to the console

#### Scenario: No aw-watcher-afk bucket present
- **WHEN** ActivityWatch responds but no bucket name starts with `aw-watcher-afk`
- **THEN** the AFK helper returns "unknown"
- **AND** the main loop runs the tick normally
- **AND** the helper logs a one-time warning so the user knows AFK gating is inactive

#### Scenario: Malformed AFK event data
- **WHEN** the most recent AFK event is present but missing `data.status` or has an unrecognized status value
- **THEN** the helper returns "unknown" and the loop runs the tick normally

### Requirement: Idle-state transitions are visible on the console

The system SHALL print a status line on the first skipped tick of an idle stretch and on the first non-idle tick after an idle stretch. The system SHALL NOT print a line on every skipped tick during a stable idle stretch.

#### Scenario: Entering idle
- **WHEN** the previous tick ran normally (or there was no previous tick)
- **AND** the current tick is being skipped due to AFK
- **THEN** the system prints a single line indicating capture has been paused (e.g., `💤 idle — skipping capture`)

#### Scenario: Stable idle
- **WHEN** both the previous tick and the current tick are being skipped due to AFK
- **THEN** the system prints nothing for the current tick

#### Scenario: Resuming from idle
- **WHEN** the previous tick was skipped due to AFK
- **AND** the current tick is running normally
- **THEN** the system prints a single line indicating capture has resumed (e.g., `▶️  resumed`)

### Requirement: Configurable grace window

The system SHALL read an `idle_skip_grace_sec` key from the config file with a default of `60`. The value SHALL be an integer number of seconds. Setting it to a very large value effectively disables the gate; setting it to `0` means any `afk` state triggers an immediate skip.

#### Scenario: Default grace window
- **WHEN** the config file does not specify `idle_skip_grace_sec`
- **THEN** the system uses 60 seconds as the grace window

#### Scenario: Custom grace window
- **WHEN** the config file contains `"idle_skip_grace_sec": 300`
- **THEN** the loop requires at least 300 seconds of continuous AFK before it starts skipping ticks

#### Scenario: Grace window effectively disabling the gate
- **WHEN** the config file contains `"idle_skip_grace_sec": 86400`
- **THEN** short-to-medium AFK stretches never trigger a skip, preserving pre-change behavior for users who want it

### Requirement: Privacy posture is preserved

The idle-gating feature SHALL NOT introduce any new network surface. All AFK queries SHALL go to the same `localhost:5600` ActivityWatch endpoint already used for window events. The feature SHALL NOT introduce new dependencies outside the Python standard library. The feature SHALL NOT cause the system to capture *more* screenshots or write *more* rows than the pre-change baseline under any condition.

#### Scenario: No new outbound hosts
- **WHEN** idle gating is active
- **THEN** network calls go only to `http://localhost:5600` (ActivityWatch) — no other hosts

#### Scenario: Never captures more than baseline
- **WHEN** any tick fires
- **THEN** the worst-case behavior of the gate is equivalent to pre-change behavior (tick runs); the gate can only *reduce* capture, never increase it
