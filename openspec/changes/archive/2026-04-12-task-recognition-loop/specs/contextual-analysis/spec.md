## MODIFIED Requirements

### Requirement: Two-pass analysis pipeline
The system SHALL perform AI analysis in two passes: a **structured extraction pass** that returns a typed artifact for each screenshot, followed by a classification pass that produces the final structured output.

The extraction pass SHALL replace the prior free-form descriptive prompt. Its output is a typed artifact per screenshot (defined in the new "Structured screenshot extraction schema" requirement). The classification pass SHALL receive these structured artifacts (not free-form prose) alongside ActivityWatch data, planned tasks, and history.

#### Scenario: Normal two-pass analysis
- **WHEN** an analysis cycle runs with screenshots available
- **THEN** the system first queries the model to extract a typed artifact for each screenshot (app, workspace, active_file, terminal_cwd, browser_url, browser_tab_titles, one_line_action)
- **AND** then queries the model with the extracted artifacts, ActivityWatch data, planned tasks, and history to produce the final JSON classification

#### Scenario: No screenshots available
- **WHEN** an analysis cycle runs but no screenshots are available
- **THEN** the system skips the extraction pass and runs the classification pass with only ActivityWatch data, planned tasks, and history

#### Scenario: Extraction pass returns unparseable JSON for a screenshot
- **WHEN** the extraction pass response for a given screenshot cannot be parsed as the typed artifact even after the existing parse-retry strategies
- **THEN** the system records a fallback artifact for that screenshot whose `one_line_action` contains the raw response and whose other fields are `null`
- **AND** the classification pass still runs with the remaining (parsed and fallback) artifacts

## ADDED Requirements

### Requirement: Structured screenshot extraction schema
The extraction pass (formerly the description pass) SHALL produce, per screenshot, a JSON object with the following fields:

| Field | Type | Nullable | Meaning |
|---|---|---|---|
| `app` | string | yes | The visible foreground application name |
| `workspace` | string | yes | The folder/project name visible in IDE sidebar/title or terminal cwd basename |
| `active_file` | string | yes | The currently focused filename, when visible |
| `terminal_cwd` | string | yes | A visible terminal working directory, when visible |
| `browser_url` | string | yes | A visible browser URL, when visible |
| `browser_tab_titles` | array of strings | yes | Visible browser tab titles, when present |
| `one_line_action` | string | **no** | A short description (≤ 12 words) of what the user appears to be doing |

The extraction prompt SHALL instruct the model that any field other than `one_line_action` MAY be `null` when not visible, and SHALL discourage the model from inventing values.

#### Scenario: VSCode workspace extracted
- **WHEN** the extraction pass receives a screenshot showing VSCode with a project sidebar and active file
- **THEN** the returned artifact populates `app="VSCode"`, `workspace=<folder name>`, `active_file=<filename>`, and a `one_line_action`
- **AND** unrelated fields (e.g. `browser_url`) are `null`

#### Scenario: Terminal cwd extracted
- **WHEN** the extraction pass receives a screenshot showing a terminal prompt that includes a working directory
- **THEN** the returned artifact populates `terminal_cwd` with the visible path
- **AND** `one_line_action` describes the visible action in ≤ 12 words

#### Scenario: Browser URL extracted
- **WHEN** the extraction pass receives a screenshot showing a browser with a visible URL bar
- **THEN** the returned artifact populates `browser_url` with the visible URL
- **AND** `browser_tab_titles` is populated with any clearly visible tab titles

#### Scenario: Sparse screenshot
- **WHEN** the extraction pass receives a screenshot whose only useful signal is "a code editor with no visible workspace name"
- **THEN** the returned artifact populates `app` (and `one_line_action`) and leaves `workspace`, `active_file`, `terminal_cwd`, `browser_url`, and `browser_tab_titles` as `null`
- **AND** the classification pass still receives this artifact

#### Scenario: Model declines to invent
- **WHEN** the extraction pass receives a screenshot that does not visibly show a workspace name
- **THEN** the returned artifact's `workspace` field is `null` rather than a guess
- **AND** the prompt does not penalize the model for returning `null`

### Requirement: Classification pass consumes structured artifacts
The classification pass prompt SHALL include the structured artifacts produced by the extraction pass as a labeled section, NOT as free-form prose. Each artifact SHALL be rendered with its non-null fields visible to the model.

#### Scenario: Artifacts rendered in classification prompt
- **WHEN** the classification pass runs after a successful extraction pass
- **THEN** the rendered prompt contains a section listing each screenshot's structured artifact (omitting null fields)
- **AND** the prompt does NOT contain free-form descriptive prose for the screenshots

#### Scenario: Fallback artifacts also rendered
- **WHEN** the classification pass runs and one of the extraction artifacts is a fallback (only `one_line_action` populated)
- **THEN** the rendered prompt still includes that artifact with its `one_line_action`
- **AND** the model is told the other fields are unknown for that screenshot
