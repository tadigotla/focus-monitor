## MODIFIED Requirements

### Requirement: Server starts with monitor
The dashboard server SHALL start automatically as a daemon thread inside the Pulse monitor process, so no separate command is needed. Starting Pulse via `python3 cli.py start` (foreground) or via the `com.focusmonitor.pulse` launchd service (background) both bring the dashboard up on the configured port.

#### Scenario: Monitor starts server
- **WHEN** the user starts Pulse in any mode (`cli.py start`, `cli.py start pulse`, or the launchd `com.focusmonitor.pulse` service)
- **THEN** the dashboard server starts on the configured port
- **AND** the startup banner prints the dashboard URL

#### Scenario: Monitor stops, server stops
- **WHEN** the Pulse process exits
- **THEN** the dashboard server thread terminates automatically (daemon thread)
