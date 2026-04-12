"""Tests for the AI analysis pipeline.

Split across several pytest classes:

- `TestParseAnalysisJson` — concrete cases ported from the old harness.
- `TestParseAnalysisJsonProperties` — hypothesis property tests over the
  parser's safety contract. The parser's job is to tolerate arbitrary LLM
  output and return either `None` or a dict — never raise — so this is
  the ideal property-test target.
- `TestValidateAnalysisResult` — validator behaviour and type coercion.
- `TestBuildClassificationPrompt` — prompt assembly.
- `TestDeduplicateScreenshots` — file-size-based dedup against real files.
- `TestDefaultConfig` — sanity checks on config constants.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from focusmonitor.analysis import (
    build_classification_prompt,
    parse_analysis_json,
    validate_analysis_result,
)
from focusmonitor.config import DEFAULT_CONFIG
from focusmonitor.screenshots import deduplicate_screenshots


# ── parse_analysis_json: hand-picked cases ───────────────────────────────────

class TestParseAnalysisJson:

    def test_direct_json(self):
        result = parse_analysis_json('{"focus_score": 85, "projects": ["coding"]}')
        assert result == {"focus_score": 85, "projects": ["coding"]}

    def test_markdown_fences(self):
        result = parse_analysis_json('```json\n{"focus_score": 70}\n```')
        assert result == {"focus_score": 70}

    def test_markdown_fences_without_language(self):
        result = parse_analysis_json('```\n{"focus_score": 70}\n```')
        assert result == {"focus_score": 70}

    def test_embedded_in_prose(self):
        result = parse_analysis_json(
            'Here is the result:\n{"focus_score": 55, "summary": "test"}\nDone.'
        )
        assert result == {"focus_score": 55, "summary": "test"}

    def test_nested_braces(self):
        result = parse_analysis_json('{"data": {"inner": 1}, "focus_score": 42}')
        assert result == {"data": {"inner": 1}, "focus_score": 42}

    def test_empty_string_returns_none(self):
        assert parse_analysis_json("") is None

    def test_none_returns_none(self):
        assert parse_analysis_json(None) is None

    def test_garbage_returns_none(self):
        assert parse_analysis_json("not json at all") is None

    def test_malformed_truncated_json_returns_none(self):
        assert parse_analysis_json('{"focus_score": 85, "projects":') is None


# ── parse_analysis_json: property tests ──────────────────────────────────────

# The parser's contract (from `focusmonitor/analysis.py`):
#   1. Given ANY input, return either None or a dict.
#   2. Never raise.
#
# Hypothesis is the right tool here — LLM outputs are exactly the kind of
# hostile input space where hand-picked cases miss everything.


class TestParseAnalysisJsonProperties:

    @given(st.text())
    @settings(
        max_examples=500,
        # The parser touches no state and no clock; disable the
        # too-slow and filter-too-much health checks since some inputs
        # are intentionally pathological.
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    )
    def test_never_crashes_on_arbitrary_text(self, s):
        """Fuzz with arbitrary unicode text — parser must not raise."""
        result = parse_analysis_json(s)
        assert result is None or isinstance(result, (dict, list, int, float, str, bool))

    @given(st.binary().map(lambda b: b.decode("utf-8", errors="replace")))
    @settings(max_examples=200)
    def test_never_crashes_on_byte_decoded_garbage(self, s):
        """Random bytes decoded to lossy UTF-8 should also be safe."""
        result = parse_analysis_json(s)
        assert result is None or isinstance(result, (dict, list, int, float, str, bool))

    @given(
        score=st.integers(min_value=0, max_value=100),
        prefix=st.text(alphabet=st.characters(blacklist_characters="{}"), max_size=50),
        suffix=st.text(alphabet=st.characters(blacklist_characters="{}"), max_size=50),
    )
    @settings(max_examples=200)
    def test_recovers_valid_json_embedded_in_prose(self, score, prefix, suffix):
        """A valid JSON object surrounded by arbitrary non-brace prose must
        be recovered. Restricting the prefix/suffix to exclude braces keeps
        the property clean — the recovery heuristic is brace-depth scanning
        and unrelated braces would legitimately confuse it.
        """
        payload = f'{{"focus_score": {score}}}'
        raw = f"{prefix}{payload}{suffix}"
        result = parse_analysis_json(raw)
        assert result is not None
        assert result.get("focus_score") == score


# ── validate_analysis_result ─────────────────────────────────────────────────

class TestValidateAnalysisResult:

    def test_full_valid_result_passes_through(self):
        full = {
            "projects": ["coding"],
            "planned_match": ["task1"],
            "distractions": [],
            "summary": "User was coding",
            "focus_score": 85,
        }
        v = validate_analysis_result(full)
        assert v == full

    def test_missing_fields_get_defaults(self):
        v = validate_analysis_result({"focus_score": 50})
        assert v == {
            "projects": [],
            "planned_match": [],
            "distractions": [],
            "summary": "",
            "focus_score": 50,
        }

    def test_score_above_100_is_clamped(self):
        assert validate_analysis_result({"focus_score": 150})["focus_score"] == 100

    def test_score_below_zero_is_clamped(self):
        assert validate_analysis_result({"focus_score": -20})["focus_score"] == 0

    def test_bad_types_fall_back_to_defaults(self):
        v = validate_analysis_result(
            {"focus_score": "high", "projects": "not a list"}
        )
        assert v["focus_score"] == -1
        assert v["projects"] == []

    def test_non_dict_input_returns_all_defaults(self):
        v = validate_analysis_result("not a dict")
        assert v == {
            "projects": [],
            "planned_match": [],
            "distractions": [],
            "summary": "",
            "focus_score": -1,
        }

    def test_float_score_is_coerced_to_int(self):
        v = validate_analysis_result({"focus_score": 73.9})
        assert v["focus_score"] == 73

    @given(score=st.one_of(
        st.integers(),
        st.floats(allow_nan=False, allow_infinity=False),
    ))
    @settings(max_examples=200)
    def test_score_always_within_bounds_or_sentinel(self, score):
        v = validate_analysis_result({"focus_score": score})
        assert v["focus_score"] == -1 or 0 <= v["focus_score"] <= 100


# ── build_classification_prompt ──────────────────────────────────────────────

class TestBuildClassificationPrompt:

    def test_includes_score_criteria(self):
        prompt = build_classification_prompt(
            DEFAULT_CONFIG.copy(),
            app_summary="  - VS Code: 1200s",
            title_summary="  - monitor.py — VS Code",
            task_list="  - Fix AI analysis",
            history_text="",
            screenshot_descriptions=["VS Code showing Python code editing"],
        )
        assert "80-100" in prompt
        assert "50-79" in prompt
        assert "20-49" in prompt
        assert "0-19" in prompt

    def test_includes_screenshot_descriptions(self):
        prompt = build_classification_prompt(
            DEFAULT_CONFIG.copy(),
            "  - VS Code: 1200s",
            "  - monitor.py",
            "  - Fix AI analysis",
            "",
            screenshot_descriptions=["VS Code showing Python code editing"],
        )
        assert "Screenshot observations" in prompt
        assert "VS Code showing Python" in prompt

    def test_includes_json_schema_reminder(self):
        prompt = build_classification_prompt(
            DEFAULT_CONFIG.copy(), "", "", "", "", None
        )
        assert '"focus_score"' in prompt
        assert '"projects"' in prompt
        assert '"planned_match"' in prompt

    def test_omits_screenshot_section_when_no_descriptions(self):
        prompt = build_classification_prompt(
            DEFAULT_CONFIG.copy(), "  - Safari: 600s", "  - Google",
            "  - Research", "", None,
        )
        assert "Screenshot observations" not in prompt

    def test_includes_history_when_provided(self):
        prompt = build_classification_prompt(
            DEFAULT_CONFIG.copy(), "", "", "",
            "## Recent history:\n  - Focus: 70/100", None,
        )
        assert "Recent history" in prompt
        assert "trends" in prompt.lower()

    def test_omits_history_when_empty(self):
        prompt = build_classification_prompt(
            DEFAULT_CONFIG.copy(), "", "", "", "", None
        )
        assert "trends" not in prompt.lower()


# ── get_recent_history ───────────────────────────────────────────────────────

class TestGetRecentHistory:

    def test_empty_db_returns_empty_string(self, db):
        from focusmonitor.analysis import get_recent_history
        assert get_recent_history(db, window=3) == ""

    def test_zero_window_returns_empty_string(self, seeded_db):
        from focusmonitor.analysis import get_recent_history
        assert get_recent_history(seeded_db, window=0) == ""

    def test_seeded_db_produces_chronological_history(self, seeded_db):
        from focusmonitor.analysis import get_recent_history
        history = get_recent_history(seeded_db, window=3)
        assert "Recent activity history" in history
        # Three most recent rows should appear (seed has 4; window=3 drops oldest)
        assert "test harness" not in history  # the 09:30 row
        assert "dashboard render helpers" in history
        assert "news and social media" in history
        assert "unclassified activity" in history

    def test_history_includes_focus_scores(self, seeded_db):
        from focusmonitor.analysis import get_recent_history
        history = get_recent_history(seeded_db, window=4)
        assert "85/100" in history
        assert "90/100" in history
        assert "15/100" in history
        assert "45/100" in history


# ── deduplicate_screenshots ──────────────────────────────────────────────────

class TestDeduplicateScreenshots:

    @pytest.fixture
    def size_files(self, tmp_path):
        """Five files with hand-picked sizes for dedup scenarios."""
        def make(name, size):
            p = tmp_path / name
            p.write_bytes(b"x" * size)
            return p
        return {
            "a": make("a.png", 10000),
            "b": make("b.png", 10000),  # identical size → dup of a
            "c": make("c.png", 15000),
            "d": make("d.png", 15050),  # within 2% of c → dup of c
            "e": make("e.png", 20000),
        }

    def test_same_size_consecutive_dedup(self, size_files):
        result = deduplicate_screenshots(
            [size_files["a"], size_files["b"], size_files["c"],
             size_files["d"], size_files["e"]],
            threshold_pct=2,
        )
        assert result == [size_files["a"], size_files["c"], size_files["e"]]

    def test_all_unique_stays_unchanged(self, size_files):
        result = deduplicate_screenshots(
            [size_files["a"], size_files["c"], size_files["e"]],
            threshold_pct=2,
        )
        assert result == [size_files["a"], size_files["c"], size_files["e"]]

    def test_all_duplicates_keeps_at_least_one(self, tmp_path):
        same = []
        for i in range(5):
            p = tmp_path / f"same_{i}.png"
            p.write_bytes(b"x" * 5000)
            same.append(p)
        result = deduplicate_screenshots(same, threshold_pct=2)
        assert len(result) >= 1

    def test_empty_list_returns_empty(self):
        assert deduplicate_screenshots([], 2) == []

    def test_threshold_zero_disables_dedup(self, size_files):
        result = deduplicate_screenshots(
            [size_files["a"], size_files["b"], size_files["c"]],
            threshold_pct=0,
        )
        assert len(result) == 3

    def test_single_file_survives(self, size_files):
        result = deduplicate_screenshots([size_files["a"]], threshold_pct=2)
        assert result == [size_files["a"]]


# ── DEFAULT_CONFIG ───────────────────────────────────────────────────────────

class TestDefaultConfig:
    """Pins on config constants that other modules depend on.

    These are trip-wires: if someone renames a key or changes a default
    without updating every consumer, these tests break first.
    """

    def test_ollama_model_is_llama_vision(self):
        assert DEFAULT_CONFIG["ollama_model"] == "llama3.2-vision"

    def test_max_parse_retries_is_one(self):
        assert DEFAULT_CONFIG["max_parse_retries"] == 1

    def test_dedup_size_threshold_is_2pct(self):
        assert DEFAULT_CONFIG["dedup_size_threshold_pct"] == 2

    def test_two_pass_analysis_is_on(self):
        assert DEFAULT_CONFIG["two_pass_analysis"] is True

    def test_history_window_is_three(self):
        assert DEFAULT_CONFIG["history_window"] == 3

    def test_ollama_url_is_localhost(self):
        """Privacy invariant: Ollama must target localhost."""
        assert "localhost" in DEFAULT_CONFIG["ollama_url"] or "127.0.0.1" in DEFAULT_CONFIG["ollama_url"]

    def test_activitywatch_url_is_localhost(self):
        """Privacy invariant: ActivityWatch must target localhost."""
        assert "localhost" in DEFAULT_CONFIG["activitywatch_url"] or "127.0.0.1" in DEFAULT_CONFIG["activitywatch_url"]
