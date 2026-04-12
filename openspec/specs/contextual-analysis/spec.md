## ADDED Requirements

### Requirement: Two-pass analysis pipeline
The system SHALL perform AI analysis in two passes: a description pass that summarizes what is visible in each screenshot, followed by a classification pass that produces the final structured output.

#### Scenario: Normal two-pass analysis
- **WHEN** an analysis cycle runs with screenshots available
- **THEN** the system first queries the model to describe each screenshot's visible content (app, activity, context)
- **AND** then queries the model with the descriptions, ActivityWatch data, planned tasks, and history to produce the final JSON classification

#### Scenario: No screenshots available
- **WHEN** an analysis cycle runs but no screenshots are available
- **THEN** the system skips the description pass and runs the classification pass with only ActivityWatch data, planned tasks, and history

### Requirement: Configurable two-pass mode
The system SHALL read a `two_pass_analysis` key from the config file (default: true) to enable or disable the two-pass pipeline.

#### Scenario: Two-pass disabled
- **WHEN** the config file contains `"two_pass_analysis": false`
- **THEN** the system uses a single prompt with screenshots + data (similar to current behavior but with improved prompt and parsing)

#### Scenario: Two-pass enabled (default)
- **WHEN** the config file does not contain `two_pass_analysis` or contains `"two_pass_analysis": true`
- **THEN** the system uses the two-pass pipeline

### Requirement: Historical context in classification
The system SHALL include summaries and focus scores from recent analyses in the classification prompt to enable trend detection.

The system SHALL query the last N entries from `activity_log` (configurable via `history_window`, default: 3) and format their summaries and focus scores as context for the classification pass.

#### Scenario: History available
- **WHEN** the database contains 3 or more prior analysis entries
- **THEN** the classification prompt includes summaries and focus scores from the 3 most recent entries
- **AND** the prompt instructs the model to consider trends (e.g., improving or declining focus)

#### Scenario: No prior history
- **WHEN** the database has no prior analysis entries (first run)
- **THEN** the classification prompt omits the history section and proceeds without trend context

#### Scenario: Partial history
- **WHEN** the database has fewer entries than `history_window`
- **THEN** the classification prompt includes all available entries

### Requirement: Configurable history window
The system SHALL read a `history_window` key from the config file (default: 3) controlling how many past analyses to include as context.

#### Scenario: Custom history window
- **WHEN** the config file contains `"history_window": 5`
- **THEN** the system includes up to 5 recent analyses as context

#### Scenario: History disabled
- **WHEN** the config file contains `"history_window": 0`
- **THEN** no historical context is included in the classification prompt

### Requirement: Updated default model
The system SHALL default to `llama3.2-vision` as the Ollama model when no model is specified in config.

#### Scenario: Fresh install
- **WHEN** no config file exists and the system generates default config
- **THEN** the `ollama_model` value is set to `"llama3.2-vision"`

#### Scenario: Existing config with custom model
- **WHEN** the user's config file already specifies `"ollama_model": "llava"`
- **THEN** the system respects the user's choice and uses `llava`

### Requirement: Improved classification prompt
The system SHALL use a classification prompt that includes structured task definitions with signals and notes instead of plain task names, and explicit criteria for focus scoring and distraction detection:
- Focus score 80-100: actively working on planned tasks
- Focus score 50-79: productive work but not on planned tasks
- Focus score 20-49: mixed activity with significant distractions
- Focus score 0-19: primarily distracted or idle

The prompt SHALL format each planned task as:
```
- "<task name>" — signals: <comma-separated signals>
  (<notes if present>)
```

#### Scenario: Clear productive work
- **WHEN** screenshots and activity clearly show work on a planned task
- **THEN** the model is guided by the prompt to assign a focus score of 80-100

#### Scenario: Productive but off-plan
- **WHEN** the user is doing productive work (coding, writing) not matching any planned task
- **THEN** the model is guided to assign 50-79 and list the detected projects without flagging them as distractions

#### Scenario: Tasks with signals in prompt
- **WHEN** planned tasks have signals defined
- **THEN** the classification prompt lists each task with its signals so the AI can match against observable keywords

#### Scenario: Tasks without signals (migrated)
- **WHEN** a planned task has no signals (e.g., freshly migrated from text file)
- **THEN** the classification prompt lists the task name only (no signals line)

#### Scenario: Prompt instructs signal-based matching
- **WHEN** the classification prompt is built
- **THEN** it instructs the AI to use signal keywords to identify which planned tasks are being worked on, using `planned_match` values that match the exact `name` field from planned tasks
