## ADDED Requirements

### Requirement: Database row retention
The system SHALL delete rows from `activity_log` and `nudges` tables that are older than a configurable retention period (default: 30 days).

#### Scenario: Old rows pruned
- **WHEN** cleanup runs and `activity_log` contains rows older than 30 days
- **THEN** those rows are deleted from the database

#### Scenario: Custom retention period
- **WHEN** the config contains `"db_retention_days": 14`
- **THEN** rows older than 14 days are pruned

#### Scenario: Retention disabled
- **WHEN** the config contains `"db_retention_days": 0`
- **THEN** no database rows are pruned

### Requirement: Log file size management
The system SHALL truncate launchd log files (`stdout.log`, `stderr.log`) in `~/.focus-monitor/logs/` when they exceed a configurable maximum size (default: 5MB), keeping the most recent 1MB of content.

#### Scenario: Log exceeds limit
- **WHEN** `stdout.log` exceeds 5MB
- **THEN** the system keeps the last 1MB of the file and discards the rest

#### Scenario: Log under limit
- **WHEN** log files are under the configured limit
- **THEN** no truncation occurs

#### Scenario: Log management disabled
- **WHEN** the config contains `"log_max_size_mb": 0`
- **THEN** no log truncation occurs

### Requirement: Unified cleanup function
The system SHALL consolidate all cleanup operations (screenshots, database, logs) into a single `run_cleanup()` function.

#### Scenario: Cleanup runs after analysis
- **WHEN** an analysis cycle completes
- **THEN** `run_cleanup()` runs, performing screenshot cleanup, database pruning, and log truncation

#### Scenario: Cleanup runs at startup
- **WHEN** the monitor starts
- **THEN** `run_cleanup()` runs once to clear any backlog from downtime

### Requirement: Cleanup reporting
The system SHALL print a summary when cleanup removes data, showing counts of deleted screenshots, pruned DB rows, and truncated log files.

#### Scenario: Data cleaned up
- **WHEN** cleanup removes 5 screenshots and 100 old DB rows
- **THEN** the system prints a summary like "Cleanup: 5 screenshots, 100 DB rows, 0 logs"

#### Scenario: Nothing to clean
- **WHEN** no data exceeds retention limits
- **THEN** no cleanup message is printed
