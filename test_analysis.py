#!/usr/bin/env python3
"""Tests for the improved AI analysis pipeline functions."""

import json
import tempfile
from pathlib import Path

# Import functions under test
from focusmonitor.analysis import (
    parse_analysis_json,
    validate_analysis_result,
    build_classification_prompt,
    get_recent_history,
)
from focusmonitor.screenshots import deduplicate_screenshots
from focusmonitor.config import DEFAULT_CONFIG

passed = 0
failed = 0


def test(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}")


# ── parse_analysis_json ──────────────────────────────────────────────────────

print("\n== parse_analysis_json ==")

# Direct JSON
result = parse_analysis_json('{"focus_score": 85, "projects": ["coding"]}')
test("direct JSON", result is not None and result["focus_score"] == 85)

# Markdown fences
result = parse_analysis_json('```json\n{"focus_score": 70}\n```')
test("markdown fences", result is not None and result["focus_score"] == 70)

# JSON embedded in prose
result = parse_analysis_json('Here is the result:\n{"focus_score": 55, "summary": "test"}\nDone.')
test("embedded in prose", result is not None and result["focus_score"] == 55)

# Nested braces
result = parse_analysis_json('{"data": {"inner": 1}, "focus_score": 42}')
test("nested braces", result is not None and result["focus_score"] == 42)

# Empty / None
test("empty string returns None", parse_analysis_json("") is None)
test("None returns None", parse_analysis_json(None) is None)
test("garbage returns None", parse_analysis_json("not json at all") is None)


# ── validate_analysis_result ──────────────────────────��──────────────────────

print("\n== validate_analysis_result ==")

# Full valid result
full = {
    "projects": ["coding"],
    "planned_match": ["task1"],
    "distractions": [],
    "summary": "User was coding",
    "focus_score": 85,
}
v = validate_analysis_result(full)
test("valid result passes through", v["focus_score"] == 85 and v["projects"] == ["coding"])

# Missing fields filled with defaults
v = validate_analysis_result({"focus_score": 50})
test("missing fields get defaults",
     v["projects"] == [] and v["planned_match"] == [] and v["summary"] == "")

# Score clamping
v = validate_analysis_result({"focus_score": 150})
test("score > 100 clamped to 100", v["focus_score"] == 100)

v = validate_analysis_result({"focus_score": -20})
test("score < 0 clamped to 0", v["focus_score"] == 0)

# Bad types
v = validate_analysis_result({"focus_score": "high", "projects": "not a list"})
test("bad types get defaults", v["focus_score"] == -1 and v["projects"] == [])

# Non-dict input
v = validate_analysis_result("not a dict")
test("non-dict returns all defaults", v["focus_score"] == -1 and v["projects"] == [])


# ── deduplicate_screenshots ──────────────────────────────────────────────────

print("\n== deduplicate_screenshots ==")

# Create temp files with controlled sizes
tmpdir = Path(tempfile.mkdtemp())

def make_file(name, size):
    p = tmpdir / name
    p.write_bytes(b"x" * size)
    return p

f1 = make_file("a.png", 10000)
f2 = make_file("b.png", 10000)   # same size as f1 (duplicate)
f3 = make_file("c.png", 15000)   # different
f4 = make_file("d.png", 15050)   # within 2% of f3 (duplicate)
f5 = make_file("e.png", 20000)   # different

# Default threshold (2%)
result = deduplicate_screenshots([f1, f2, f3, f4, f5], threshold_pct=2)
test("dedup removes same-size consecutive",
     len(result) == 3 and f1 in result and f3 in result and f5 in result)

# All unique
result = deduplicate_screenshots([f1, f3, f5], threshold_pct=2)
test("all unique stays unchanged", len(result) == 3)

# All duplicates → keep at least 1
same = [make_file(f"same_{i}.png", 5000) for i in range(5)]
result = deduplicate_screenshots(same, threshold_pct=2)
test("all dupes keeps at least 1", len(result) >= 1)

# Empty list
test("empty list returns empty", deduplicate_screenshots([], 2) == [])

# Disabled (threshold 0)
result = deduplicate_screenshots([f1, f2, f3], threshold_pct=0)
test("threshold 0 disables dedup", len(result) == 3)

# Single file
result = deduplicate_screenshots([f1], threshold_pct=2)
test("single file stays", len(result) == 1)


# ── build_classification_prompt ──────────────────────────────────────────────

print("\n== build_classification_prompt ==")

cfg = DEFAULT_CONFIG.copy()
prompt = build_classification_prompt(
    cfg,
    app_summary="  - VS Code: 1200s",
    title_summary="  - monitor.py — VS Code",
    task_list="  - Fix AI analysis",
    history_text="",
    screenshot_descriptions=["VS Code showing Python code editing"]
)
test("prompt includes score criteria", "80-100" in prompt and "50-79" in prompt)
test("prompt includes screenshot descriptions", "VS Code showing Python" in prompt)
test("prompt includes JSON format", '"focus_score"' in prompt)

# Without descriptions (single-pass mode)
prompt2 = build_classification_prompt(
    cfg, "  - Safari: 600s", "  - Google", "  - Research", "", None
)
test("no descriptions omits section", "Screenshot observations" not in prompt2)

# With history
prompt3 = build_classification_prompt(
    cfg, "", "", "", "## Recent history:\n  - Focus: 70/100", None
)
test("history included in prompt", "Recent history" in prompt3)
test("trend instruction present", "trends" in prompt3.lower())


# ── DEFAULT_CONFIG new keys ──────────────────────────────────────────────────

print("\n== DEFAULT_CONFIG ==")

test("model is llama3.2-vision", DEFAULT_CONFIG["ollama_model"] == "llama3.2-vision")
test("max_parse_retries exists", DEFAULT_CONFIG["max_parse_retries"] == 1)
test("dedup_size_threshold_pct exists", DEFAULT_CONFIG["dedup_size_threshold_pct"] == 2)
test("two_pass_analysis exists", DEFAULT_CONFIG["two_pass_analysis"] is True)
test("history_window exists", DEFAULT_CONFIG["history_window"] == 3)


# ── Cleanup ──────────────────────────────────────────────────────────────────

import shutil
shutil.rmtree(tmpdir, ignore_errors=True)

print(f"\n{'='*50}")
print(f"  Results: {passed} passed, {failed} failed")
print(f"{'='*50}")

exit(0 if failed == 0 else 1)
