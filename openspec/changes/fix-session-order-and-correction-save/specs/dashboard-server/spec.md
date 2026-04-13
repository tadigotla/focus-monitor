## ADDED Requirements

### Requirement: Sessions displayed newest-first
The dashboard's "Today's sessions" panel SHALL render sessions in reverse chronological order (most recent session at the top). The ordering SHALL be performed in the SQL query, not in post-processing.

#### Scenario: Newest session appears first
- **WHEN** the dashboard is rendered for a day with sessions starting at 09:00, 10:30, and 14:00
- **THEN** the session starting at 14:00 appears first in the HTML
- **AND** the session starting at 09:00 appears last

#### Scenario: Single session
- **WHEN** the dashboard is rendered for a day with exactly one session
- **THEN** that session is displayed (ordering is trivially correct)
