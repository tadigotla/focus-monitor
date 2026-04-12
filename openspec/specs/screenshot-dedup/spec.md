## ADDED Requirements

### Requirement: Screenshot deduplication before analysis
The system SHALL deduplicate screenshots before sending them for AI analysis, removing consecutive screenshots that are visually identical or near-identical.

#### Scenario: All screenshots are unique
- **WHEN** 6 recent screenshots all have distinct content
- **THEN** all 6 screenshots are sent to the model for analysis

#### Scenario: Consecutive duplicate screenshots
- **WHEN** 6 recent screenshots include 3 consecutive pairs of identical content
- **THEN** only 3 unique screenshots are sent to the model
- **AND** the analysis log indicates how many were deduplicated

#### Scenario: Only one unique screenshot
- **WHEN** all recent screenshots are near-identical (user didn't change windows)
- **THEN** exactly 1 screenshot is sent to the model

### Requirement: File-size-based deduplication heuristic
The system SHALL compare consecutive screenshot file sizes as the deduplication method. Two consecutive screenshots are considered duplicates when their file sizes are within a configurable percentage threshold of each other.

#### Scenario: Screenshots within threshold
- **WHEN** two consecutive screenshots have file sizes within the configured threshold (default: 2%)
- **THEN** the later screenshot is marked as a duplicate and excluded from analysis

#### Scenario: Screenshots exceed threshold
- **WHEN** two consecutive screenshots have file sizes differing by more than the configured threshold
- **THEN** both screenshots are kept for analysis

### Requirement: Configurable dedup threshold
The system SHALL read a `dedup_size_threshold_pct` key from the config file (default: 2) representing the percentage threshold for file-size-based deduplication.

#### Scenario: Config specifies custom threshold
- **WHEN** the config file contains `"dedup_size_threshold_pct": 5`
- **THEN** the system considers screenshots as duplicates when file sizes are within 5% of each other

#### Scenario: Dedup disabled
- **WHEN** the config file contains `"dedup_size_threshold_pct": 0`
- **THEN** no deduplication is performed and all screenshots are sent to the model

### Requirement: Minimum screenshot count
The system SHALL always send at least 1 screenshot to the model, even if deduplication would eliminate all of them.

#### Scenario: Aggressive dedup leaves no screenshots
- **WHEN** deduplication marks all screenshots as duplicates
- **THEN** the most recent screenshot is still included in the analysis
