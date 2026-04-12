## MODIFIED Requirements

### Requirement: Improved classification prompt
The system SHALL use a classification prompt that includes structured task definitions with signals and notes instead of plain task names.

The prompt SHALL format each planned task as:
```
- "<task name>" — signals: <comma-separated signals>
  (<notes if present>)
```

This replaces the previous format of plain task name bullet points.

#### Scenario: Tasks with signals in prompt
- **WHEN** planned tasks have signals defined
- **THEN** the classification prompt lists each task with its signals so the AI can match against observable keywords

#### Scenario: Tasks without signals (migrated)
- **WHEN** a planned task has no signals (e.g., freshly migrated from text file)
- **THEN** the classification prompt lists the task name only (no signals line)

#### Scenario: Prompt instructs signal-based matching
- **WHEN** the classification prompt is built
- **THEN** it instructs the AI to use signal keywords to identify which planned tasks are being worked on, using `planned_match` values that match the exact `name` field from planned tasks
