## Why

The current AI analysis pipeline uses Ollama's `llava` model with a single monolithic prompt, fragile JSON parsing, and no awareness of previous analyses. This leads to inconsistent focus scores, unreliable JSON output (often falling back to raw text), and redundant processing of identical screenshots. Improving the analysis pipeline will make classifications more accurate, output more reliable, and scoring more consistent over time.

## What Changes

- **Switch to a better vision model**: Replace `llava` with `llama3.2-vision` (or make model easily configurable with a recommended default) for significantly improved visual understanding and instruction following.
- **Structured output with retry logic**: Add robust JSON extraction with multiple parsing strategies and a retry mechanism when the model returns malformed output.
- **Screenshot deduplication**: Hash-based comparison to skip near-identical screenshots, reducing token usage and noise in analysis.
- **Two-pass analysis**: First pass describes what's visible on each screen; second pass classifies activity against planned tasks. This chain-of-thought approach improves accuracy.
- **Historical context**: Include summaries from the last 2-3 analyses in the prompt so the model can detect trends (e.g., "user was focused on X but is now drifting").
- **Improved prompt engineering**: More specific classification criteria, explicit examples of what counts as productive vs. distracted, and clearer JSON schema instructions.

## Capabilities

### New Capabilities
- `structured-analysis`: Robust JSON output handling with retry logic, multi-strategy parsing, and validation against an expected schema
- `screenshot-dedup`: Hash-based screenshot deduplication to skip identical/near-identical captures before sending to the model
- `contextual-analysis`: Two-pass analysis pipeline with historical context from recent analyses for trend-aware classification

### Modified Capabilities

(none - no existing specs to modify)

## Impact

- **monitor.py**: Major changes to `query_ollama()`, `run_analysis()`, and `recent_screenshots()`. New helper functions for JSON validation, screenshot hashing, and historical context retrieval.
- **Config**: New config keys for model selection, retry attempts, dedup sensitivity threshold, and historical context window size.
- **Dependencies**: No new external dependencies - uses only stdlib (hashlib for dedup, existing sqlite for history).
- **Database**: No schema changes needed - `raw_response` column already stores full model output; `activity_log` already has the history we need.
