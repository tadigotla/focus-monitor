## Context

Focus Monitor's AI analysis pipeline (`monitor.py:run_analysis`) currently works as a single-shot prompt to Ollama's `llava` model. It sends up to 6 screenshots plus ActivityWatch summaries and asks for a JSON classification. The pipeline has several weaknesses: fragile JSON parsing that silently falls back to unstructured text, no deduplication of identical screenshots, no memory of previous analyses, and reliance on an older vision model with weaker instruction-following.

All changes stay within `monitor.py` — there are no external services, APIs, or deployment concerns. The database schema remains unchanged.

## Goals / Non-Goals

**Goals:**
- Reliable structured JSON output from every analysis run (no more silent fallbacks to raw text)
- Reduce wasted tokens by skipping duplicate screenshots
- More accurate activity classification through chain-of-thought prompting and historical context
- Keep everything local and dependency-free (stdlib only)

**Non-Goals:**
- Adding new external dependencies (no pydantic, no langchain, etc.)
- Changing the database schema or migration tooling
- Building a model fine-tuning or training pipeline
- Real-time streaming analysis or sub-minute analysis intervals
- Supporting non-Ollama backends (OpenAI, Anthropic, etc.)

## Decisions

### 1. Default model: `llama3.2-vision` instead of `llava`

**Rationale**: `llama3.2-vision` has significantly better instruction following and JSON output compliance. It's widely available via Ollama and runs well on Apple Silicon.

**Alternative considered**: Keeping `llava` with better prompts. Rejected because `llava` fundamentally struggles with structured output regardless of prompt quality.

**Migration**: Config key `ollama_model` already exists. Default changes from `"llava"` to `"llama3.2-vision"`. Users who already have a config file keep their existing setting.

### 2. Multi-strategy JSON parsing with retry

**Rationale**: Even good models occasionally produce malformed JSON. Rather than silently degrading, we try multiple extraction strategies and optionally retry the query.

**Approach**:
1. Try direct `json.loads` on the response
2. Strip markdown fences and retry
3. Regex extract first `{...}` block and parse
4. If all fail and retries remain, re-query with a "fix your JSON" follow-up prompt
5. After max retries, store raw response with `focus_score: -1` (existing fallback behavior)

**Alternative considered**: Using Ollama's `format: "json"` parameter. This works but constrains the model and isn't universally supported across all Ollama models. We use it when available but don't depend on it.

### 3. Perceptual hash-based screenshot deduplication

**Rationale**: When users leave the same window open, consecutive screenshots are nearly identical. Sending 6 identical images wastes tokens and confuses the model.

**Approach**: Compute a simple block-mean hash of each screenshot (resize to 8x8, compare luminance). If a screenshot's hash matches the previous one within a configurable Hamming distance threshold, skip it. This uses only PIL/stdlib — but since PIL may not be available, fall back to file-size-based heuristic (if two consecutive files have sizes within 2% of each other, consider them duplicates).

**Alternative considered**: Pixel-diff with a threshold. More accurate but significantly more expensive for marginal benefit. Hash comparison is O(1) per image.

### 4. Two-pass analysis pipeline

**Rationale**: Asking the model to simultaneously describe screenshots AND classify activity in one prompt leads to shallow descriptions and classification errors. Separating these steps improves both.

**Approach**:
- **Pass 1 (Describe)**: For each unique screenshot, ask the model to describe what's visible — app, content, activity. Short structured output per image.
- **Pass 2 (Classify)**: Feed the descriptions + ActivityWatch data + planned tasks + recent history into a classification prompt that produces the final JSON.

**Trade-off**: Two API calls instead of one, roughly doubling latency per analysis cycle (from ~30s to ~60s). Acceptable since analysis runs every 30 minutes.

**Alternative considered**: Single improved prompt with chain-of-thought. Simpler but testing shows the two-pass approach is noticeably more accurate for distraction detection.

### 5. Historical context window

**Rationale**: Without history, each analysis is independent. The model can't detect drift ("you were focused on X but switched to Y") or trends.

**Approach**: Before the classification pass, query the last 3 entries from `activity_log` and include their summaries + focus scores in the prompt. This adds ~200 tokens of context.

**Config**: New key `history_window` (default: 3) controls how many past analyses to include.

## Risks / Trade-offs

- **[Doubled latency per analysis]** → Two-pass adds ~30s per cycle. Mitigated by the 30-minute interval — users won't notice. Config key `two_pass_analysis` (default: true) allows disabling.
- **[Model availability]** → `llama3.2-vision` must be pulled via Ollama first. Mitigated by falling back to whatever model is configured; setup.py will suggest pulling the model.
- **[Screenshot dedup false positives]** → Aggressive dedup might skip meaningfully different screenshots. Mitigated by conservative default threshold (Hamming distance <= 5 out of 64 bits) and config key `dedup_threshold`.
- **[Retry adds latency on failure]** → If the model consistently returns bad JSON, retries compound. Mitigated by max 1 retry (configurable) and a fast "fix JSON" prompt that's much shorter than the original.
