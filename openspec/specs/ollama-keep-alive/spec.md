## ADDED Requirements

### Requirement: Ollama keep-alive parameter in API requests
The system SHALL include a `keep_alive` field in every Ollama `/api/generate` request payload, set to the value of the `ollama_keep_alive` config key.

#### Scenario: Default keep-alive value
- **WHEN** the user has not set `ollama_keep_alive` in their config
- **THEN** the system SHALL send `"keep_alive": "30s"` in each Ollama API request

#### Scenario: Custom keep-alive value
- **WHEN** the user sets `ollama_keep_alive` to a custom value (e.g. `"0"`, `"5m"`, `"1h"`)
- **THEN** the system SHALL send that exact value as the `keep_alive` field in each Ollama API request

#### Scenario: Model unloads between analysis cycles
- **WHEN** an analysis cycle completes and no further Ollama requests arrive within the keep-alive duration
- **THEN** Ollama SHALL unload the model from memory (this is Ollama server behavior, not enforced by focus-monitor)

### Requirement: Configurable ollama_keep_alive key
The system SHALL read an `ollama_keep_alive` key from the config file with a default value of `"30s"`.

The value SHALL be passed through to the Ollama API as-is. Valid formats are defined by the Ollama API (e.g. `"0"` for immediate unload, `"30s"`, `"5m"`, `"1h"`, or `-1` for never unload).

#### Scenario: Config key present
- **WHEN** the config file contains `"ollama_keep_alive": "1m"`
- **THEN** the system SHALL use `"1m"` as the keep-alive value for all Ollama requests

#### Scenario: Config key absent
- **WHEN** the config file does not contain `ollama_keep_alive`
- **THEN** the system SHALL use the default value `"30s"`
