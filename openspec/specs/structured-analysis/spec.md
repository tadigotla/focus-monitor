## ADDED Requirements

### Requirement: Multi-strategy JSON parsing
The system SHALL attempt multiple strategies to extract valid JSON from the model's response before falling back to unstructured storage.

The parsing strategies SHALL be applied in order:
1. Direct `json.loads` on the full response text
2. Strip markdown code fences (` ```json ` / ` ``` `) and parse
3. Regex-extract the first `{...}` block (handling nested braces) and parse

#### Scenario: Model returns clean JSON
- **WHEN** the model response is valid JSON
- **THEN** the system parses it directly without modification

#### Scenario: Model wraps JSON in markdown fences
- **WHEN** the model response contains JSON wrapped in ` ```json ` and ` ``` ` markers
- **THEN** the system strips the fences and successfully parses the JSON

#### Scenario: Model returns JSON embedded in prose
- **WHEN** the model response contains text before/after a JSON object
- **THEN** the system extracts the first complete `{...}` block and parses it

### Requirement: JSON retry on parse failure
The system SHALL retry the model query when all parsing strategies fail, up to a configurable maximum number of retries (default: 1).

The retry prompt SHALL be a short correction prompt that includes the original malformed response and asks the model to return only valid JSON.

#### Scenario: First parse fails, retry succeeds
- **WHEN** all parsing strategies fail on the initial response
- **AND** retry count has not been exhausted
- **THEN** the system sends a correction prompt to the model
- **AND** applies the same parsing strategies to the retry response

#### Scenario: All retries exhausted
- **WHEN** all parsing strategies fail on the initial response AND all retry attempts
- **THEN** the system stores the raw response with `focus_score: -1`, empty `projects`, empty `planned_match`, empty `distractions`, and the raw text as `summary`

### Requirement: Response schema validation
The system SHALL validate that parsed JSON contains the expected keys: `projects` (list), `planned_match` (list), `distractions` (list), `summary` (string), `focus_score` (integer 0-100), `task` (string or null), `evidence` (list of `{signal, weight}` objects), `boundary_confidence` (one of `"low" | "medium" | "high"`), `name_confidence` (one of `"low" | "medium" | "high"`), and `needs_user_input` (boolean).

The legacy fields (`projects`, `planned_match`, `distractions`, `summary`, `focus_score`) SHALL remain populated for backwards compatibility with existing rows and the existing nudge path. The new fields are additive.

#### Scenario: Valid response with all fields
- **WHEN** the parsed JSON contains all required keys (legacy and new) with correct types
- **THEN** the system accepts the response and stores it

#### Scenario: Missing or invalid legacy fields
- **WHEN** the parsed JSON is missing any of the legacy keys or has wrong types for them
- **THEN** the system fills missing legacy fields with defaults (empty lists, empty string, -1 for `focus_score`) rather than rejecting the entire response

#### Scenario: Missing or invalid new fields
- **WHEN** the parsed JSON is missing any of the new keys (`task`, `evidence`, `boundary_confidence`, `name_confidence`, `needs_user_input`) or has wrong types for them
- **THEN** the system fills missing new fields with safe defaults: `task=null`, `evidence=[]`, `boundary_confidence="low"`, `name_confidence="low"`, `needs_user_input=true`
- **AND** does not reject the entire response

#### Scenario: focus_score out of range
- **WHEN** the parsed `focus_score` is less than 0 or greater than 100
- **THEN** the system clamps the value to the 0-100 range

#### Scenario: Invalid confidence value
- **WHEN** the parsed `boundary_confidence` or `name_confidence` is not one of `"low" | "medium" | "high"`
- **THEN** the system replaces the value with `"low"`
- **AND** sets `needs_user_input` to `true`

#### Scenario: Evidence list with malformed entries
- **WHEN** the parsed `evidence` list contains entries that are not `{signal, weight}` objects with string values
- **THEN** the system filters out the malformed entries
- **AND** retains the well-formed entries

### Requirement: Configurable retry count
The system SHALL read a `max_parse_retries` key from the config file (default: 1) to control how many retry attempts are made on parse failure.

#### Scenario: Config specifies custom retry count
- **WHEN** the config file contains `"max_parse_retries": 2`
- **THEN** the system allows up to 2 retry attempts before falling back

#### Scenario: Config omits retry count
- **WHEN** the config file does not contain `max_parse_retries`
- **THEN** the system defaults to 1 retry attempt

### Requirement: Evidence-grounded classification
The classification prompt SHALL instruct the model to populate an `evidence` array tying each classification claim to one or more observable signals from the structured screenshot artifacts, the ActivityWatch top apps, or the window titles.

Each evidence entry SHALL be a `{signal, weight}` object where `signal` is a short human-readable string identifying the observation (e.g. `"vscode workspace: focus-monitor"`, `"terminal pwd matches"`, `"github PR url"`) and `weight` is one of `"strong" | "medium" | "weak"`.

The prompt SHALL state that an empty `evidence` array is permitted only when `task` is `null` and `name_confidence` is `"low"`.

#### Scenario: Evidence populated for confident classification
- **WHEN** the classification pass identifies a clear task with multiple supporting signals
- **THEN** the `evidence` field contains one entry per supporting signal with appropriate `weight` values
- **AND** the strongest signals appear first

#### Scenario: Empty evidence permitted for unclear classification
- **WHEN** the model cannot identify a task and sets `task=null`, `name_confidence="low"`
- **THEN** an empty `evidence` array is accepted
- **AND** the system does not flag this as a validation failure

### Requirement: Dual confidence levels
The classification output SHALL include two separable confidence fields:

- `boundary_confidence`: how confident the model is that the cycle represents one coherent activity (as opposed to a mix of multiple distinct activities)
- `name_confidence`: how confident the model is that the named `task` is the *correct* name for that activity (as opposed to generic or wrongly-attributed)

Each SHALL take one of three values: `"low"`, `"medium"`, `"high"`. The classification prompt SHALL include explicit anchor examples for each level on each axis, and SHALL explicitly state that returning `"low"` when signals are genuinely mixed is a successful outcome, not a failure mode.

#### Scenario: High boundary, high name
- **WHEN** the model sees consistent signals pointing at a single named task
- **THEN** it returns `boundary_confidence="high"` and `name_confidence="high"`

#### Scenario: High boundary, low name
- **WHEN** the model sees consistent signals (one workspace, one cwd) but cannot match a specific planned task name
- **THEN** it returns `boundary_confidence="high"` and `name_confidence="low"`
- **AND** `task` may be either a generic descriptor or `null`

#### Scenario: Low boundary
- **WHEN** the model sees signals from multiple unrelated workspaces or applications within the cycle
- **THEN** it returns `boundary_confidence="low"`
- **AND** the aggregator downstream is expected to treat this cycle as a likely task-switch boundary

### Requirement: Model may decline to commit a task name
The classification prompt SHALL explicitly permit the model to return `task=null`, `name_confidence="low"`, and `needs_user_input=true` when the signals are insufficient to identify a specific task. The prompt SHALL state that this is a correct, expected outcome rather than a failure.

The system SHALL accept `task=null` as a valid classification result and SHALL NOT trigger a parse-retry for this case.

#### Scenario: Insufficient signal
- **WHEN** the cycle contains active AW events but the structured artifacts have all-null workspace/cwd/url fields
- **THEN** the classification result has `task=null`, `name_confidence="low"`, `needs_user_input=true`
- **AND** the system stores this result without retrying

#### Scenario: Mixed signal
- **WHEN** the cycle's structured artifacts show two unrelated workspaces with comparable signal strength
- **THEN** the classification result has `boundary_confidence="low"`
- **AND** the result is accepted without retry

### Requirement: Few-shot corrections in classification prompt
The classification prompt SHALL include up to N most recent user corrections and confirmations from the corrections store as labeled few-shot examples. N is read from `corrections_few_shot_n` in the config (default: 5).

Each example SHALL render: the timestamp, what the model previously said (task + name confidence), what the user said (verdict + corrected task or kind), and the structured signals visible at the time. Confirmations SHALL be rendered alongside corrections so the model has both positive and negative examples.

When the corrections store is empty, the prompt SHALL omit the few-shot section entirely (no empty header).

#### Scenario: Corrections present
- **WHEN** the classification pass runs and the corrections store has at least one record
- **THEN** the classification prompt contains a "Recent corrections from the user" section with up to N entries ordered most-recent-first
- **AND** each entry includes the model's prior verdict, the user's verdict, and the structured signals from that time

#### Scenario: Confirmations included
- **WHEN** the corrections store contains both confirmed (✓) and corrected (✏️) entries
- **THEN** both kinds appear in the few-shot section
- **AND** each entry's verdict (`confirmed` vs `corrected`) is clearly labeled

#### Scenario: Corrections store empty
- **WHEN** the corrections store has no records
- **THEN** the classification prompt does not include a "Recent corrections" section at all

#### Scenario: Configurable N
- **WHEN** `corrections_few_shot_n` is set to 3 in config
- **THEN** the classification prompt includes at most 3 most-recent correction entries

#### Scenario: N set to zero
- **WHEN** `corrections_few_shot_n` is `0`
- **THEN** no few-shot section is rendered, regardless of corpus size

### Requirement: Default configuration values
The system SHALL use the following default values for analysis timing:

- `screenshot_interval_sec`: `300`
- `analysis_interval_sec`: `3600`
- `screenshots_per_analysis`: `12`

All other default values remain unchanged. Existing users with a saved `config.json` retain their current values since `load_config()` merges saved config over defaults.

#### Scenario: New install gets updated defaults
- **WHEN** a user runs focus-monitor for the first time with no existing `config.json`
- **THEN** the generated config SHALL contain `"screenshot_interval_sec": 300`, `"analysis_interval_sec": 3600`, and `"screenshots_per_analysis": 12`

#### Scenario: Existing install preserves user values
- **WHEN** a user has an existing `config.json` with `"analysis_interval_sec": 1800`
- **THEN** the system SHALL use `1800`, not the new default of `3600`

#### Scenario: Full-hour screenshot coverage
- **WHEN** the system runs with defaults (`screenshot_interval_sec: 300`, `analysis_interval_sec: 3600`, `screenshots_per_analysis: 12`)
- **THEN** the 12 most recent screenshots SHALL span the full 60-minute analysis window with no blind spots

### Requirement: run_analysis accepts pre-fetched data
`run_analysis()` SHALL accept optional keyword arguments `prefetched_events` and `prefetched_screenshots`. When `prefetched_events` is not `None`, the function SHALL skip calling `get_aw_events()` and use the provided event list. When `prefetched_screenshots` is not `None`, the function SHALL skip calling `recent_screenshots()` and use the provided paths list. All other behavior (prompt building, Ollama calls, DB writes, session aggregation) SHALL remain identical.

#### Scenario: Live mode — no prefetched data
- **WHEN** `run_analysis()` is called without `prefetched_events` or `prefetched_screenshots`
- **THEN** the function queries AW events live via `get_aw_events()` and screenshots via `recent_screenshots()`
- **AND** behavior is identical to the pre-change implementation

#### Scenario: Batch mode — prefetched events and screenshots
- **WHEN** `run_analysis()` is called with `prefetched_events` set to a list of AW events and `prefetched_screenshots` set to a list of Path objects
- **THEN** the function uses those values directly
- **AND** does NOT call `get_aw_events()` or `recent_screenshots()`
- **AND** passes the events through `summarize_aw_events()` as usual

#### Scenario: Mixed — only events prefetched
- **WHEN** `run_analysis()` is called with `prefetched_events` set but `prefetched_screenshots` as `None`
- **THEN** the function uses the prefetched events and queries screenshots from disk via `recent_screenshots()`
