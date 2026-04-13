## Context

`query_ollama` in `focusmonitor/ollama.py` is the single chokepoint for all model queries. Today it builds a payload with `model`, `prompt`, `stream`, `keep_alive`, and optionally `images` — but no generation parameters. The Ollama `/api/generate` endpoint accepts:

- `options.temperature` — sampling temperature (0.0 = greedy/deterministic)
- `format` — either the string `"json"` (constrain output to valid JSON tokens) or a JSON schema object (constrain to a specific shape)

Neither is set today, so the model runs at its compiled-in defaults (typically temperature 0.7–0.8 for llama3.2-vision). For structured extraction and classification tasks, this introduces unnecessary variance that manifests as JSON parse failures requiring expensive retry roundtrips.

## Goals / Non-Goals

**Goals:**
- Drive JSON parse failure rate toward zero for Pass 1 and Pass 2 by adding `temperature: 0` and `format: "json"` to the Ollama request payload.
- Keep the change minimal: modify the API call layer, wire the new params from the two call sites, add tests. No prompt rewrites, no parser changes, no config additions.
- Retain all existing parse-recovery code as defense-in-depth.

**Non-Goals:**
- Full JSON schema validation via Ollama's `format: {schema}` feature. Defer until `format: "json"` proves insufficient.
- Removing the multi-strategy parser, `\_` unescape, or retry loop. Observe failure rates first.
- Changing the legacy single-pass code path. It's an escape hatch; minimize disruption.
- Adding user-facing config for temperature or format. These are implementation details.
- Parallelizing Pass 1 calls. Separate change.

## Decisions

### D1. `query_ollama` gains keyword-only `temperature` and `format_`

**Decision:** Add two optional keyword-only arguments to `query_ollama`:

```python
def query_ollama(cfg, prompt, image_paths=None, *, temperature=None, format_=None):
```

- `temperature` (float or None): when not None, added to the payload as `options.temperature`.
- `format_` (str or None): when not None, added to the payload as `format`. Named `format_` to avoid shadowing Python's built-in `format`.

When either is None, the corresponding key is omitted from the payload entirely, preserving current default behavior for any caller that doesn't opt in.

**Why keyword-only:** prevents positional-argument mistakes at call sites. The existing `image_paths` positional arg is already established; new params should not extend the positional signature.

**Why not a `generation_options` dict:** two params don't justify an abstraction. If we later need `top_p`, `top_k`, `repeat_penalty`, etc., we can refactor then.

### D2. Pass 1 and Pass 2 both use temperature=0.0 and format="json"

**Decision:** Both `extract_screenshot_artifacts` (Pass 1, per-screenshot) and the Pass 2 classification call in `run_analysis` pass `temperature=0.0, format_="json"` to `query_ollama`.

**Why temperature=0 for both passes:**
- Pass 1 is structured field extraction. Determinism is strictly better — we want the same screenshot to produce the same artifact every time.
- Pass 2 is classification. We want consistent task naming, consistent evidence extraction, consistent confidence calibration. Creative temperature adds noise to a task where reliability matters more than diversity.

**Why format="json" for both passes:**
- Both prompts already instruct "respond with ONLY the JSON object, no markdown, no prose." The `format` parameter makes this enforceable at the token level rather than aspirational in the prompt.
- Ollama's JSON mode constrains the grammar to produce syntactically valid JSON. It does NOT constrain the schema — the model can still return wrong keys or unexpected types. `validate_analysis_result` and `_coerce_artifact` still do the schema work.

### D3. Legacy single-pass path is unchanged

**Decision:** The code path at `run_analysis` lines 576–584 (when `two_pass_analysis` is false, or no screenshots) does NOT pass temperature or format. It uses the existing default behavior.

**Why:** This path is an escape hatch. Users who set `two_pass_analysis: false` may be doing so because the structured pipeline doesn't work for their model. Adding constraints to the escape hatch defeats its purpose.

Exception: when `two_pass_analysis` is true but there are no screenshots, the classification-only call (line 575) DOES get the new params — it's still part of the structured pipeline, just without a Pass 1 phase.

### D4. Retry loop and parse-recovery code are retained as-is

**Decision:** The multi-strategy parser (`_parse_json_strategies`), the `\_` unescape path, and the retry loop at lines 591–604 are untouched. They become fallback paths that fire rarely rather than regularly.

**Why not remove them now:** we haven't measured the failure rate under the new parameters. The conservative path is to keep them, observe for a week, and remove in a follow-up if failures drop to zero. The code cost of keeping them is minimal (they're already written and tested).

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| **`format: "json"` may cause the model to produce degenerate JSON** (e.g., `{}` or `{"error": "..."}`) when it would otherwise have produced useful prose. | `_coerce_artifact` and `validate_analysis_result` already handle missing/malformed fields with safe defaults. A degenerate JSON object is no worse than a parse failure — and is better because it doesn't trigger the retry loop. |
| **Temperature 0 may reduce model quality** for edge cases where the "right" classification is ambiguous and the greedy path picks the wrong one. | Classification is a recall task, not a creative task. The correction loop exists precisely to catch persistent misclassifications. Consistency is more valuable than occasional lucky guesses. |
| **Ollama version compatibility.** Older Ollama versions may not support `format` or `options.temperature`. | Both features have been stable since Ollama 0.1.x (2024). The project already depends on Ollama for vision model support, which arrived later. If an old Ollama rejects the params, the error surfaces clearly in the existing try/except. |
| **Privacy.** | No new outbound target, no new dependency, no new data path. The change adds two fields to a payload sent to `127.0.0.1:11434`. Privacy posture is strictly unchanged. |

## Migration Plan

1. Land the `query_ollama` signature change and unit test.
2. Wire Pass 1 and Pass 2 call sites. Run the existing test suite (cassette-backed, offline).
3. Dogfood for a day. Watch for degenerate JSON responses or unexpected parse failures in the console output.
4. If failure rate drops as expected, consider a follow-up change to simplify or remove the retry loop.
