## REMOVED Requirements

### Requirement: Backward-compatible entry points

**Reason**: The top-level shims `monitor.py` and `dashboard.py` existed only to preserve a launchd plist whose `ProgramArguments` targeted them by absolute path. With the consolidated-entrypoints change, the plists target `bin/focusmonitor-service` (which dispatches into `cli.py`), and there is no longer any consumer of the old top-level scripts. Keeping them adds maintenance surface for no user-visible benefit.

**Migration**: Users with the legacy `com.focusmonitor.agent` plist installed follow the manual upgrade path documented in the README's "Upgrading from the old launchd agent" section: unload the old label, remove the old plist, run `python3 cli.py service install && python3 cli.py service start`. Users who invoke `python3 monitor.py` or `python3 dashboard.py` directly switch to `python3 cli.py start` and `python3 cli.py start pulse` respectively (the dashboard HTTP server is embedded in Pulse, so "start pulse" brings it up).
