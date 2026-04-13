## MODIFIED Requirements

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

## ADDED Requirements

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
