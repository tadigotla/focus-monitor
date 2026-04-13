## MODIFIED Requirements

### Requirement: run_analysis accepts pre-fetched data
`run_analysis()` SHALL accept optional keyword arguments `prefetched_events` and `prefetched_screenshots`. When `prefetched_events` is not `None`, the function SHALL skip calling `get_aw_events()` and use the provided event list. When `prefetched_screenshots` is not `None`, the function SHALL skip calling `recent_screenshots()` and use the provided paths list. All other behavior (prompt building, Ollama calls, DB writes, session aggregation) SHALL remain identical.

#### Scenario: Live mode — no prefetched data
- **WHEN** `run_analysis()` is called without `prefetched_events` or `prefetched_screenshots`
- **THEN** the function queries AW events live via `get_aw_events()` and screenshots via `recent_screenshots()`
- **AND** behavior is identical to the pre-change implementation

#### Scenario: Batch mode — prefetched events and screenshots
- **WHEN** `run_analysis()` is called with `prefetched_events` set to a list of AW events and `prefetched_screenshots` set to a list of Path objects
- **THEN** the function uses those values directly
- **AND** does NOT call `get_aw_events()` or `recent_screenshots()`
- **AND** passes the events through `summarize_aw_events()` as usual

#### Scenario: Mixed — only events prefetched
- **WHEN** `run_analysis()` is called with `prefetched_events` set but `prefetched_screenshots` as `None`
- **THEN** the function uses the prefetched events and queries screenshots from disk via `recent_screenshots()`
