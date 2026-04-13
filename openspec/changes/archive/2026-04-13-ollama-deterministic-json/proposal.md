## Why

The Ollama query layer (`focusmonitor/ollama.py`) sends requests with zero generation parameters — no `temperature`, no `top_p`, no output format constraint. This means:

1. **Non-deterministic structured output.** The Pass 1 extraction prompt asks for strict JSON but the model runs at its default temperature (~0.7–0.8), introducing unnecessary randomness. Some fraction of responses come back with markdown fences, prose preamble, or the `\_` escape corruption that the multi-strategy parser and `\_` unescape path exist solely to recover from.

2. **No grammar-level JSON enforcement.** Ollama's `/api/generate` supports `"format": "json"` which constrains the model's token sampling to syntactically valid JSON. Without it, the system relies on three parsing strategies, a `\_` unescape fallback, and a retry loop that fires additional full model inferences — each retry costs the same wall-clock time as the original call.

The retry loop at `analysis.py:591–604` is the most expensive consequence: a single JSON parse failure triggers up to `max_parse_retries` additional Ollama roundtrips. On a 10.7B model these are 10–30 seconds each. Eliminating the parse failures at the source is cheaper and more reliable than recovering from them downstream.

These two changes are complementary: `temperature: 0` reduces creative drift that produces malformed output; `format: json` makes malformed JSON structurally impossible at the token level. Together they should drive JSON parse failures to near-zero, making most of the recovery machinery dormant (though we keep it as defense-in-depth).

## What Changes

- **`query_ollama` gains optional `temperature` and `format` parameters.** Callers can pass `temperature=0.0` for deterministic output and `format="json"` for grammar-constrained JSON. Both are optional and default to `None` (current behavior preserved for any caller that doesn't opt in).
- **Pass 1 (extraction) calls use `temperature=0.0` and `format="json"`.** The extraction prompt already asks for strict JSON with no prose — adding the API-level constraint makes the instruction enforceable.
- **Pass 2 (classification) calls use `temperature=0.0` and `format="json"`.** The classification prompt similarly asks for JSON-only output. Low temperature is appropriate because we want consistent, repeatable classifications, not creative variation.
- **The retry loop, multi-strategy parser, and `\_` unescape path are retained** as defense-in-depth. They become rarely-exercised fallback paths rather than load-bearing infrastructure. No code is removed in this change — we reduce the frequency of failures, not the recovery surface.
- **Config keys are NOT added** for temperature or format. These are implementation details of the Ollama call, not user-tunable behavior. If a future model benefits from different settings, the code is the right place to change them.

Explicitly out of scope:
- Structured output / JSON schema validation at the Ollama API level (Ollama supports a `format` field with a JSON schema object, not just `"json"`). This is a stronger constraint but ties the prompt to a specific schema version. Defer until we see whether `format: json` alone is sufficient.
- Removing the parse-recovery code. We want to observe failure rates drop before deleting fallback paths.
- Changing sampling parameters for the legacy single-pass path (when `two_pass_analysis: false`). That path is an escape hatch and should behave as close to the original as possible.
- Parallelizing Pass 1. Separate change.

## Capabilities

### Modified Capabilities
- `contextual-analysis`: Pass 1 extraction calls gain `temperature=0.0` and `format="json"` parameters, reducing non-determinism and enforcing syntactically valid JSON at the token level.
- `structured-analysis`: Pass 2 classification calls gain the same parameters for consistent, parseable output.

## Impact

**Affected code (focusmonitor/):**
- `ollama.py` — `query_ollama` signature gains optional `temperature` and `format_` keyword arguments. Payload construction adds these fields when non-None.
- `analysis.py` — `extract_screenshot_artifacts` and `run_analysis` pass the new kwargs to `query_ollama` for Pass 1 and Pass 2 calls respectively. No prompt text changes. No parser changes.

**Affected data:** None. Output schema is unchanged; the model just produces it more reliably.

**Tests:**
- Existing cassette-backed tests continue to work (cassettes replay fixed responses regardless of request parameters).
- New unit test asserting that `query_ollama` includes `temperature` and `format` in the request payload when provided.
- New unit test asserting the legacy path (single-pass, `two_pass_analysis: false`) does NOT set these parameters.

**Dependencies:** None added.

**Network:** No change. Ollama on `127.0.0.1:11434` only. No new outbound target.
