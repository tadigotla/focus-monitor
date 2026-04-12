## ADDED Requirements

### Requirement: Dashboard served over HTTP
The system SHALL serve the dashboard HTML over HTTP on a configurable local port (default: 9876), bound to 127.0.0.1 only.

#### Scenario: Dashboard accessible at localhost
- **WHEN** the dashboard server is running
- **THEN** a GET request to `http://localhost:9876/` returns the dashboard HTML with status 200

#### Scenario: Dashboard shows current data
- **WHEN** a user visits the dashboard URL after analyses have been logged
- **THEN** the page displays data from the current day's activity log, freshly queried from the database

### Requirement: Auto-refresh
The dashboard HTML SHALL include an auto-refresh mechanism that reloads the page at a configurable interval (default: 60 seconds).

#### Scenario: Page auto-refreshes
- **WHEN** the dashboard page is open in a browser
- **THEN** the page automatically reloads after the configured refresh interval

#### Scenario: Custom refresh interval
- **WHEN** the config contains `"dashboard_refresh_sec": 30`
- **THEN** the page auto-refreshes every 30 seconds

### Requirement: Server starts with monitor
The dashboard server SHALL start automatically as a daemon thread when `monitor.py` runs, so no separate command is needed.

#### Scenario: Monitor starts server
- **WHEN** the user starts the monitor
- **THEN** the dashboard server starts on the configured port
- **AND** the startup banner prints the dashboard URL

#### Scenario: Monitor stops, server stops
- **WHEN** the monitor process exits
- **THEN** the dashboard server thread terminates automatically (daemon thread)

### Requirement: Configurable port
The system SHALL read a `dashboard_port` key from the config file (default: 9876).

#### Scenario: Custom port
- **WHEN** the config contains `"dashboard_port": 8080`
- **THEN** the dashboard server binds to port 8080

#### Scenario: Port conflict
- **WHEN** the configured port is already in use
- **THEN** the system prints an error message suggesting to change the port in config
- **AND** the monitor continues running without the dashboard server

### Requirement: Local-only binding
The dashboard server SHALL bind to 127.0.0.1 only, not to 0.0.0.0 or any external interface.

#### Scenario: External access blocked
- **WHEN** a request comes from a non-local IP
- **THEN** the connection is refused because the server only listens on 127.0.0.1
