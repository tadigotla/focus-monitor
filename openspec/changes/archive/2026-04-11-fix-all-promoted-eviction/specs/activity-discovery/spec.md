## MODIFIED Requirements

### Requirement: Activity cap and eviction
The system SHALL keep at most 50 entries in `discovered_activities.json`. When the cap is reached, the oldest non-promoted entry (by `last_seen`) SHALL be evicted. When all existing entries are promoted, the oldest entry (by `last_seen`) SHALL be evicted regardless of promoted status so that a newly-detected activity is still retained. A newly-detected activity SHALL never be evicted as part of the same update that added it.

#### Scenario: Cap reached with non-promoted entries
- **WHEN** there are 50 activities and a new one is detected
- **AND** there are non-promoted entries
- **THEN** the oldest non-promoted entry (by `last_seen`) is removed and the new entry is added
- **AND** the new entry remains in the list after the update

#### Scenario: All entries promoted
- **WHEN** all 50 entries are promoted and a new activity is detected
- **THEN** the oldest entry (by `last_seen`) is evicted regardless of promoted status
- **AND** the new activity is retained in the list
