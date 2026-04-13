## MODIFIED Requirements

### Requirement: Few-shot retrieval injects most-recent-N records
The classification pipeline SHALL include the N most recent records (any verdict) from the `corrections` table in the Pass 2 classification prompt as few-shot examples. N is read from `corrections_few_shot_n` in the config (default: 5). When N is 0, no few-shot section is included.

The retrieval SHALL be a single SQL query of the form `SELECT ... FROM corrections ORDER BY created_at DESC LIMIT ?` with no scoring, no similarity calculation, and no embedding lookup. Adding similarity-based retrieval is explicitly out of scope for this change.

When `batch_analysis` is `True`, the few-shot retrieval still operates identically. Corrections filed between batch runs are visible to the next batch run's analysis cycles. The feedback latency increases from ~1 hour to ~2–3 hours but the mechanism is unchanged.

#### Scenario: Most recent N records retrieved
- **WHEN** the classification pipeline runs and the `corrections` table has more than N records
- **THEN** the N records with the most recent `created_at` are pulled
- **AND** they appear in the prompt ordered most-recent-first

#### Scenario: Fewer than N records
- **WHEN** the table has fewer than N records
- **THEN** all available records are returned
- **AND** no padding or placeholder is added

#### Scenario: N is zero
- **WHEN** `corrections_few_shot_n` is `0`
- **THEN** the few-shot section is omitted entirely from the prompt

#### Scenario: Corrections filed between batch runs
- **WHEN** the user corrects a session at 1:00 PM
- **AND** the next batch runs at 3:00 PM
- **THEN** the 1:00 PM correction appears in the few-shot block for all analysis cycles in the 3:00 PM batch
