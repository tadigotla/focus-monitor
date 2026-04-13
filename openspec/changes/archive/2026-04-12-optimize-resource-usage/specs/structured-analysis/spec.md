## MODIFIED Requirements

### Requirement: Default configuration values
The system SHALL use the following updated default values for analysis timing:

- `screenshot_interval_sec`: `300` (was `120`)
- `analysis_interval_sec`: `3600` (was `1800`)
- `screenshots_per_analysis`: `12` (was `6`)

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
