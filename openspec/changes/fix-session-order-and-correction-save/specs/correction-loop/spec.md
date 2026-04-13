## ADDED Requirements

### Requirement: CSRF token refresh after correction submission
After a successful correction or confirmation POST, the server SHALL return a fresh CSRF token that is usable by subsequent htmx requests without a full page reload. The page-level `hx-headers` CSRF token SHALL be updated to match the fresh token so that all htmx-driven mutation endpoints continue to work.

#### Scenario: Second correction succeeds after first
- **WHEN** the user submits a correction for session A (succeeds)
- **AND** then submits a correction for session B without reloading the page
- **THEN** the second submission also succeeds (200, not 403)
- **AND** the correction row for session B is persisted

#### Scenario: Confirmation after correction succeeds
- **WHEN** the user submits a correction for session A (succeeds)
- **AND** then clicks Confirm on session B without reloading the page
- **THEN** the confirmation succeeds (200, not 403)

#### Scenario: Token propagated via htmx mechanism
- **WHEN** a correction POST returns successfully
- **THEN** the response includes a mechanism (e.g. HX-Trigger header) that causes the page-level htmx CSRF header to update
- **AND** no full page reload is required
