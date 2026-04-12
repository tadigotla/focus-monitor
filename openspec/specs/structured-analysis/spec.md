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
The system SHALL validate that parsed JSON contains the expected keys: `projects` (list), `planned_match` (list), `distractions` (list), `summary` (string), `focus_score` (integer 0-100).

#### Scenario: Valid response with all fields
- **WHEN** the parsed JSON contains all required keys with correct types
- **THEN** the system accepts the response and stores it

#### Scenario: Missing or invalid fields
- **WHEN** the parsed JSON is missing required keys or has wrong types
- **THEN** the system fills missing fields with defaults (empty lists, empty string, -1 for focus_score) rather than rejecting the entire response

#### Scenario: focus_score out of range
- **WHEN** the parsed `focus_score` is less than 0 or greater than 100
- **THEN** the system clamps the value to the 0-100 range

### Requirement: Configurable retry count
The system SHALL read a `max_parse_retries` key from the config file (default: 1) to control how many retry attempts are made on parse failure.

#### Scenario: Config specifies custom retry count
- **WHEN** the config file contains `"max_parse_retries": 2`
- **THEN** the system allows up to 2 retry attempts before falling back

#### Scenario: Config omits retry count
- **WHEN** the config file does not contain `max_parse_retries`
- **THEN** the system defaults to 1 retry attempt
