## ADDED Requirements

### Requirement: Unified CLI with subcommands
The system SHALL provide a single CLI entry point (`cli.py`) with subcommands that replace direct script invocation.

#### Scenario: Run monitor with dashboard
- **WHEN** the user executes `python3 cli.py run`
- **THEN** the monitor starts with the dashboard server (equivalent to current `python3 monitor.py`)

#### Scenario: Dashboard only
- **WHEN** the user executes `python3 cli.py dashboard`
- **THEN** only the dashboard server starts (no monitoring, no screenshots)
- **AND** the user can view past data at the dashboard URL

#### Scenario: Setup
- **WHEN** the user executes `python3 cli.py setup`
- **THEN** the setup script runs (equivalent to current `python3 setup.py`)

### Requirement: Default subcommand
The system SHALL default to the `run` subcommand when no subcommand is specified.

#### Scenario: No subcommand given
- **WHEN** the user executes `python3 cli.py` without arguments
- **THEN** the system behaves as if `python3 cli.py run` was executed

### Requirement: Dashboard-only mode
The `dashboard` subcommand SHALL start only the HTTP server, allowing users to view historical data without running the monitor.

#### Scenario: View past data without monitoring
- **WHEN** the user runs `python3 cli.py dashboard`
- **THEN** the dashboard server starts and serves data from the existing database
- **AND** no screenshots are taken and no analyses are run

#### Scenario: No database exists
- **WHEN** the user runs `python3 cli.py dashboard` and no database file exists
- **THEN** the system prints an error: "No activity database found. Run 'python3 cli.py run' first."
