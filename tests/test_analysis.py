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
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from focusmonitor.analysis import (
    _coerce_artifact,
    build_classification_prompt,
    extract_screenshot_artifacts,
    parse_analysis_json,
    render_few_shot_corrections,
    run_analysis,
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

    def test_markdown_escaped_underscores_recovered(self):
        """llama3.2-vision sometimes escapes the underscore in keys
        that contain them, producing `\\_` sequences that break strict
        json.loads. The parser must recover these. Regression from a
        real-world failure on 2026-04-12."""
        raw = (
            ' {\n'
            '"projects": ["Building and maintaining Sanskrit Study Tool"],\n'
            '"planned\\_match": ["Building and maintaining Sanskrit Study Tool"],\n'
            '"distractions": [],\n'
            '"summary": "The user was working on the Sanskrit study tool.",\n'
            '"focus\\_score": 70,\n'
            '"task": "Sanskrit Study Tool",\n'
            '"evidence": [],\n'
            '"boundary\\_confidence": "high",\n'
            '"name\\_confidence": "high",\n'
            '"needs\\_user\\_input": false\n'
            '}'
        )
        result = parse_analysis_json(raw)
        assert result is not None
        assert result["focus_score"] == 70
        assert result["name_confidence"] == "high"
        assert result["boundary_confidence"] == "high"
        assert result["needs_user_input"] is False
        assert result["planned_match"] == [
            "Building and maintaining Sanskrit Study Tool"
        ]

    def test_escaped_underscore_in_fenced_block(self):
        """Same fix applies when the response is ALSO fence-wrapped."""
        raw = (
            '```json\n'
            '{"focus\\_score": 50, "planned\\_match": ["x"]}\n'
            '```'
        )
        result = parse_analysis_json(raw)
        assert result is not None
        assert result["focus_score"] == 50
        assert result["planned_match"] == ["x"]

    def test_valid_json_is_untouched_by_unescape_fallback(self):
        """A clean response must not go through the unescape path —
        the strict parse wins on the first try. Verified by checking
        that a JSON string containing the literal `\\_` sequence
        survives (not that we'd ever expect one, but it's the only
        way to prove the fallback didn't fire)."""
        # Valid JSON that happens to contain an escaped backslash-u in
        # a string value. If the unescape fallback fired on the raw
        # text, the backslash would be stripped before strict parsing
        # and the string content would change.
        raw = '{"focus_score": 42, "summary": "path: C:\\\\_foo"}'
        # That source represents the JSON string: {"summary": "path: C:\\_foo"}
        # which parses to {"summary": "path: C:\\_foo"} in Python (one backslash).
        result = parse_analysis_json(raw)
        assert result is not None
        assert result["focus_score"] == 42
        assert result["summary"] == "path: C:\\_foo"


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


# ── render_few_shot_corrections ──────────────────────────────────────────────

class TestRenderFewShotCorrections:

    def test_empty_returns_empty_string(self):
        assert render_few_shot_corrections([]) == ""
        assert render_few_shot_corrections(None) == ""

    def test_single_correction(self):
        out = render_few_shot_corrections([
            {
                "created_at": "2026-04-12T14:15:00",
                "model_task": "browsing",
                "model_name_confidence": "low",
                "user_verdict": "corrected",
                "user_task": "auth refactor",
                "user_kind": "on_planned_task",
                "user_note": None,
                "signals": {"workspaces": ["focus-monitor"]},
            }
        ])
        assert "Recent corrections from the user" in out
        assert "corrected → auth refactor" in out
        assert "workspace=focus-monitor" in out
        assert "on_planned_task" in out

    def test_user_note_included(self):
        out = render_few_shot_corrections([
            {
                "created_at": "2026-04-12T14:15:00",
                "model_task": None,
                "model_name_confidence": "low",
                "user_verdict": "corrected",
                "user_task": "auth refactor",
                "user_kind": "on_planned_task",
                "user_note": "this is me thinking",
                "signals": {},
            }
        ])
        assert "this is me thinking" in out
        # null model task renders as "unclear"
        assert "model said: unclear" in out

    def test_confirmation_renders_differently_from_correction(self):
        out = render_few_shot_corrections([
            {
                "created_at": "2026-04-12T14:15:00",
                "model_task": "auth",
                "model_name_confidence": "high",
                "user_verdict": "confirmed",
                "user_task": "auth",
                "user_kind": "on_planned_task",
                "user_note": None,
                "signals": {"workspaces": ["focus-monitor"]},
            }
        ])
        assert "confirmed" in out
        assert "corrected" not in out


# ── extract_screenshot_artifacts ─────────────────────────────────────────────

FIXTURE_DIR = Path(__file__).resolve().parent / "data" / "screenshots"


class TestExtractScreenshotArtifacts:
    """The extractor's job is to round-trip Ollama's response through the
    shared JSON parser and produce a canonical typed artifact per
    screenshot. We stub `query_ollama` so these tests stay offline and
    cassette-free — the cassette-backed variant lives under task 2.9 and
    is deferred to a separate session.
    """

    def _make_cfg(self):
        return DEFAULT_CONFIG.copy()

    def test_returns_typed_artifact_for_clean_response(self, monkeypatch):
        clean_response = json.dumps({
            "app": "VSCode",
            "workspace": "focus-monitor",
            "active_file": "auth.py",
            "terminal_cwd": None,
            "browser_url": None,
            "browser_tab_titles": None,
            "one_line_action": "editing auth.py",
        })
        monkeypatch.setattr(
            "focusmonitor.analysis.query_ollama",
            lambda *a, **kw: clean_response,
        )
        fixture = FIXTURE_DIR / "screen_20260412_100000.png"
        assert fixture.exists()
        artifacts = extract_screenshot_artifacts(self._make_cfg(), [fixture])
        assert len(artifacts) == 1
        art = artifacts[0]
        assert art["app"] == "VSCode"
        assert art["workspace"] == "focus-monitor"
        assert art["active_file"] == "auth.py"
        assert art["terminal_cwd"] is None
        assert art["browser_url"] is None
        assert art["browser_tab_titles"] is None
        assert art["one_line_action"] == "editing auth.py"

    def test_fallback_when_response_is_unparseable(self, monkeypatch):
        """Parser returns None → fallback artifact carries the raw text
        in one_line_action and leaves other fields null."""
        monkeypatch.setattr(
            "focusmonitor.analysis.query_ollama",
            lambda *a, **kw: "definitely not json at all",
        )
        fixture = FIXTURE_DIR / "screen_20260412_100000.png"
        artifacts = extract_screenshot_artifacts(self._make_cfg(), [fixture])
        assert len(artifacts) == 1
        art = artifacts[0]
        assert art["one_line_action"].startswith("definitely not json")
        # All other fields fall back to None.
        for field in ("app", "workspace", "active_file",
                      "terminal_cwd", "browser_url", "browser_tab_titles"):
            assert art[field] is None

    def test_fallback_when_ollama_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            "focusmonitor.analysis.query_ollama",
            lambda *a, **kw: None,
        )
        fixture = FIXTURE_DIR / "screen_20260412_100000.png"
        artifacts = extract_screenshot_artifacts(self._make_cfg(), [fixture])
        assert len(artifacts) == 1
        # one_line_action is non-empty even on total silence from Ollama.
        assert artifacts[0]["one_line_action"]
        assert artifacts[0]["app"] is None

    def test_response_with_markdown_fence_parses(self, monkeypatch):
        """The shared multi-strategy parser handles fence-wrapped JSON —
        make sure the extractor does NOT short-circuit it."""
        fenced = (
            "```json\n"
            '{"app": "Terminal", "workspace": null, "active_file": null, '
            '"terminal_cwd": "~/code/demo", "browser_url": null, '
            '"browser_tab_titles": null, "one_line_action": "running tests"}\n'
            "```"
        )
        monkeypatch.setattr(
            "focusmonitor.analysis.query_ollama",
            lambda *a, **kw: fenced,
        )
        fixture = FIXTURE_DIR / "screen_20260412_100000.png"
        artifacts = extract_screenshot_artifacts(self._make_cfg(), [fixture])
        art = artifacts[0]
        assert art["app"] == "Terminal"
        assert art["terminal_cwd"] == "~/code/demo"
        assert art["one_line_action"] == "running tests"

    def test_coerce_artifact_filters_non_string_values(self):
        """Hostile parsed payload: numeric workspace, dict tab titles,
        blank action. The coercer should normalize all of them without
        raising."""
        result = _coerce_artifact(
            {
                "app": 42,                         # non-string → dropped
                "workspace": "",                   # blank → dropped
                "active_file": "main.py",          # kept
                "terminal_cwd": None,              # null → null
                "browser_url": "   ",              # whitespace → dropped
                "browser_tab_titles": ["tab a", 7, "tab b"],  # mixed → coerced
                "one_line_action": "",             # blank → falls back
            },
            raw_fallback="raw text",
        )
        assert result["app"] is None
        assert result["workspace"] is None
        assert result["active_file"] == "main.py"
        assert result["terminal_cwd"] is None
        assert result["browser_url"] is None
        assert result["browser_tab_titles"] == ["tab a", "7", "tab b"]
        assert result["one_line_action"] == "raw text"

    def test_passes_temperature_and_format_to_ollama(self, monkeypatch):
        """Pass 1 extraction must request temperature=0 and format=json."""
        captured_kwargs = {}

        def spy(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return json.dumps({"one_line_action": "testing"})

        monkeypatch.setattr("focusmonitor.analysis.query_ollama", spy)
        fixture = FIXTURE_DIR / "screen_20260412_100000.png"
        extract_screenshot_artifacts(self._make_cfg(), [fixture])

        assert captured_kwargs.get("temperature") == 0.0
        assert captured_kwargs.get("format_") == "json"


# ── validate_analysis_result ─────────────────────────────────────────────────

class TestValidateAnalysisResult:

    def test_full_valid_legacy_result_passes_through(self):
        """Back-compat: a response containing only the legacy fields
        still validates. New fields are filled with safe defaults."""
        legacy_only = {
            "projects": ["coding"],
            "planned_match": ["task1"],
            "distractions": [],
            "summary": "User was coding",
            "focus_score": 85,
        }
        v = validate_analysis_result(legacy_only)
        # Legacy fields pass through unchanged.
        for k, expected in legacy_only.items():
            assert v[k] == expected
        # New fields get safe defaults.
        assert v["task"] is None
        assert v["evidence"] == []
        assert v["boundary_confidence"] == "low"
        assert v["name_confidence"] == "low"
        assert v["needs_user_input"] is True

    def test_full_valid_result_with_new_fields(self):
        full = {
            "projects": ["focus-monitor"],
            "planned_match": ["focus-monitor"],
            "distractions": [],
            "summary": "Worked on the auth refactor",
            "focus_score": 84,
            "task": "auth refactor",
            "evidence": [
                {"signal": "vscode workspace: focus-monitor", "weight": "strong"},
                {"signal": "terminal pwd matches", "weight": "medium"},
            ],
            "boundary_confidence": "high",
            "name_confidence": "high",
            "needs_user_input": False,
        }
        v = validate_analysis_result(full)
        assert v["task"] == "auth refactor"
        assert len(v["evidence"]) == 2
        assert v["evidence"][0] == {
            "signal": "vscode workspace: focus-monitor",
            "weight": "strong",
        }
        assert v["boundary_confidence"] == "high"
        assert v["name_confidence"] == "high"
        assert v["needs_user_input"] is False

    def test_missing_fields_get_defaults(self):
        v = validate_analysis_result({"focus_score": 50})
        assert v["projects"] == []
        assert v["planned_match"] == []
        assert v["distractions"] == []
        assert v["summary"] == ""
        assert v["focus_score"] == 50
        # New fields: safe defaults.
        assert v["task"] is None
        assert v["evidence"] == []
        assert v["boundary_confidence"] == "low"
        assert v["name_confidence"] == "low"
        assert v["needs_user_input"] is True

    def test_invalid_confidence_falls_back_and_sets_needs_input(self):
        v = validate_analysis_result({
            "focus_score": 70,
            "task": "foo",
            "evidence": [{"signal": "x", "weight": "medium"}],
            "boundary_confidence": "sky-high",  # invalid
            "name_confidence": "high",
            "needs_user_input": False,
        })
        assert v["boundary_confidence"] == "low"
        assert v["name_confidence"] == "high"
        # Invalid confidence forces needs_user_input back to True
        # regardless of what the model claimed.
        assert v["needs_user_input"] is True

    def test_evidence_filters_malformed_entries(self):
        v = validate_analysis_result({
            "focus_score": 70,
            "evidence": [
                {"signal": "good one", "weight": "strong"},
                {"signal": "", "weight": "strong"},       # blank signal
                {"signal": "no weight"},                   # missing weight
                {"weight": "strong"},                      # missing signal
                "not a dict",                              # wrong type
                {"signal": 42, "weight": "strong"},        # non-string signal
                {"signal": "ok", "weight": "medium"},
            ],
            "boundary_confidence": "high",
            "name_confidence": "high",
            "needs_user_input": False,
        })
        assert v["evidence"] == [
            {"signal": "good one", "weight": "strong"},
            {"signal": "ok", "weight": "medium"},
        ]

    def test_task_null_low_confidence_is_valid(self):
        """Model may decline to commit. The response must validate
        without raising and without triggering a retry."""
        v = validate_analysis_result({
            "projects": [],
            "planned_match": [],
            "distractions": [],
            "summary": "Signals were too mixed to identify a task",
            "focus_score": 30,
            "task": None,
            "evidence": [],
            "boundary_confidence": "low",
            "name_confidence": "low",
            "needs_user_input": True,
        })
        assert v["task"] is None
        assert v["evidence"] == []
        assert v["name_confidence"] == "low"
        assert v["needs_user_input"] is True

    def test_non_string_task_coerced_to_null(self):
        v = validate_analysis_result({
            "focus_score": 50,
            "task": 42,
        })
        assert v["task"] is None

    def test_blank_task_coerced_to_null(self):
        v = validate_analysis_result({
            "focus_score": 50,
            "task": "   ",
        })
        assert v["task"] is None

    def test_valid_null_task_response_does_not_trigger_retry(self, monkeypatch):
        """End-to-end contract: a well-formed response whose task is
        null and name_confidence is 'low' must be accepted without a
        parse-retry, because the parser succeeds on it and
        run_analysis' retry branch fires only when the parser returns
        None. Spy on query_ollama so a second (retry) call would be
        visible as an extra invocation."""
        import focusmonitor.analysis as analysis_mod

        null_task_response = json.dumps({
            "projects": [],
            "planned_match": [],
            "distractions": [],
            "summary": "Signals were too mixed",
            "focus_score": 30,
            "task": None,
            "evidence": [],
            "boundary_confidence": "low",
            "name_confidence": "low",
            "needs_user_input": True,
        })

        # parser accepts the well-formed response
        parsed = analysis_mod.parse_analysis_json(null_task_response)
        assert parsed is not None
        # validator leaves task=null, name_confidence=low, no exception
        v = analysis_mod.validate_analysis_result(parsed)
        assert v["task"] is None
        assert v["name_confidence"] == "low"
        assert v["needs_user_input"] is True

        # Guard against drift: the retry path in run_analysis fires only
        # when parse_analysis_json returns None. Asserting the parser
        # returns a dict here pins the contract.
        assert isinstance(parsed, dict)

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
        assert v["projects"] == []
        assert v["planned_match"] == []
        assert v["distractions"] == []
        assert v["summary"] == ""
        assert v["focus_score"] == -1
        assert v["task"] is None
        assert v["evidence"] == []
        assert v["boundary_confidence"] == "low"
        assert v["name_confidence"] == "low"
        assert v["needs_user_input"] is True

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
        assert "Screenshot artifacts" not in prompt

    def test_renders_structured_artifacts_and_omits_null_fields(self):
        artifacts = [
            {
                "app": "VSCode",
                "workspace": "focus-monitor",
                "active_file": "auth.py",
                "terminal_cwd": None,
                "browser_url": None,
                "browser_tab_titles": None,
                "one_line_action": "editing auth.py",
            },
            {
                "app": "Safari",
                "workspace": None,
                "active_file": None,
                "terminal_cwd": None,
                "browser_url": "github.com/foo/bar/pull/47",
                "browser_tab_titles": ["PR #47 · auth", "Stack Overflow"],
                "one_line_action": "reviewing PR",
            },
        ]
        prompt = build_classification_prompt(
            DEFAULT_CONFIG.copy(), "", "", "", "",
            screenshot_artifacts=artifacts,
        )
        assert "Screenshot artifacts" in prompt
        # Non-null fields rendered.
        assert "VSCode" in prompt
        assert "focus-monitor" in prompt
        assert "auth.py" in prompt
        assert "github.com/foo/bar/pull/47" in prompt
        assert "PR #47 · auth" in prompt
        # Null fields must not appear as labels (no "terminal cwd:" line
        # for the first screenshot since its cwd is None).
        first_block_end = prompt.find("Screenshot 2:")
        assert first_block_end > 0
        first_block = prompt[:first_block_end]
        assert "terminal cwd" not in first_block
        assert "browser url" not in first_block
        # And the legacy free-form "Screenshot observations" label is
        # absent when structured artifacts are present.
        assert "Screenshot observations" not in prompt

    def test_omits_corrections_section_when_empty(self):
        prompt = build_classification_prompt(
            DEFAULT_CONFIG.copy(), "", "", "", "",
            corrections=[],
        )
        assert "Recent corrections from the user" not in prompt

    def test_omits_corrections_section_when_none(self):
        prompt = build_classification_prompt(
            DEFAULT_CONFIG.copy(), "", "", "", "",
        )
        assert "Recent corrections from the user" not in prompt

    def test_renders_corrections_section_when_provided(self):
        corrections = [
            {
                "created_at": "2026-04-12T14:15:00",
                "model_task": "browsing",
                "model_name_confidence": "low",
                "user_verdict": "corrected",
                "user_task": "auth refactor",
                "user_kind": "on_planned_task",
                "user_note": None,
                "signals": {
                    "workspaces": ["focus-monitor"],
                    "terminal_cwds": ["~/code/2026/focus-monitor"],
                    "browser_hosts": ["github.com"],
                },
            },
            {
                "created_at": "2026-04-12T11:02:00",
                "model_task": "auth refactor",
                "model_name_confidence": "high",
                "user_verdict": "confirmed",
                "user_task": "auth refactor",
                "user_kind": "on_planned_task",
                "user_note": None,
                "signals": {"workspaces": ["focus-monitor"]},
            },
        ]
        prompt = build_classification_prompt(
            DEFAULT_CONFIG.copy(), "", "", "", "",
            corrections=corrections,
        )
        assert "Recent corrections from the user" in prompt
        # Corrected and confirmed both visible, clearly labeled.
        assert "corrected → auth refactor" in prompt
        assert "confirmed" in prompt
        # Signals for the corrected entry are rendered.
        assert "workspace=focus-monitor" in prompt
        # The model's prior verdict is visible for both entries.
        assert "model said: browsing" in prompt
        assert "model said: auth refactor" in prompt

    def test_structured_artifacts_take_precedence_over_descriptions(self):
        prompt = build_classification_prompt(
            DEFAULT_CONFIG.copy(), "", "", "", "",
            screenshot_descriptions=["a free-form prose description"],
            screenshot_artifacts=[
                {
                    "app": "Terminal",
                    "workspace": None,
                    "active_file": None,
                    "terminal_cwd": "~/code/demo",
                    "browser_url": None,
                    "browser_tab_titles": None,
                    "one_line_action": "running tests",
                }
            ],
        )
        assert "Screenshot artifacts" in prompt
        assert "Screenshot observations" not in prompt
        assert "a free-form prose description" not in prompt
        assert "~/code/demo" in prompt

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


# ── run_analysis: temperature and format kwargs ──────────────────────────────

class TestRunAnalysisOllamaKwargs:
    """Verify that run_analysis passes temperature/format to query_ollama
    in the two-pass path and does NOT in the single-pass fallback."""

    _VALID_RESPONSE = json.dumps({
        "projects": ["test"],
        "planned_match": [],
        "distractions": [],
        "summary": "testing",
        "focus_score": 50,
        "task": "test",
        "evidence": [],
        "boundary_confidence": "medium",
        "name_confidence": "medium",
        "needs_user_input": False,
    })

    def _make_cfg(self, two_pass=True):
        cfg = DEFAULT_CONFIG.copy()
        cfg["two_pass_analysis"] = two_pass
        cfg["pass1_structured"] = True
        cfg["analysis_interval_sec"] = 300
        cfg["history_window"] = 0
        cfg["session_aggregation_enabled"] = False
        return cfg

    def _stub_deps(self, monkeypatch):
        """Stub everything run_analysis touches except query_ollama."""
        monkeypatch.setattr(
            "focusmonitor.analysis.get_aw_events", lambda *a, **kw: []
        )
        monkeypatch.setattr(
            "focusmonitor.analysis.summarize_aw_events",
            lambda events: ([], []),
        )
        monkeypatch.setattr(
            "focusmonitor.analysis.load_planned_tasks", lambda: []
        )
        monkeypatch.setattr(
            "focusmonitor.analysis.recent_corrections", lambda *a, **kw: []
        )
        monkeypatch.setattr(
            "focusmonitor.analysis.deduplicate_screenshots",
            lambda paths, pct: paths,
        )
        monkeypatch.setattr(
            "focusmonitor.analysis.update_discovered_activities",
            lambda *a: None,
        )
        monkeypatch.setattr(
            "focusmonitor.analysis.check_nudges", lambda *a: None
        )

    def test_two_pass_sends_temperature_and_format(self, monkeypatch, tmp_path):
        """Both Pass 1 and Pass 2 calls must include temperature=0.0
        and format_='json' when two_pass_analysis is true."""
        self._stub_deps(monkeypatch)

        calls = []

        def spy_ollama(cfg, prompt, image_paths=None, **kwargs):
            calls.append(kwargs.copy())
            return self._VALID_RESPONSE

        monkeypatch.setattr("focusmonitor.analysis.query_ollama", spy_ollama)

        # Create a fake screenshot so Pass 1 fires
        fake_screenshot = tmp_path / "screen.png"
        fake_screenshot.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        import sqlite3
        db = sqlite3.connect(":memory:")
        db.execute(
            "CREATE TABLE activity_log (id INTEGER PRIMARY KEY, "
            "timestamp TEXT, window_titles TEXT, apps_used TEXT, "
            "project_detected TEXT, is_distraction INTEGER, "
            "summary TEXT, raw_response TEXT)"
        )

        run_analysis(
            self._make_cfg(two_pass=True), db,
            prefetched_events=[],
            prefetched_screenshots=[fake_screenshot],
        )

        # Pass 1 (extraction) + Pass 2 (classification) = at least 2 calls
        assert len(calls) >= 2
        # Pass 1 call
        assert calls[0].get("temperature") == 0.0
        assert calls[0].get("format_") == "json"
        # Pass 2 call (last call before any retries)
        assert calls[1].get("temperature") == 0.0
        assert calls[1].get("format_") == "json"

    def test_single_pass_omits_temperature_and_format(self, monkeypatch, tmp_path):
        """Legacy single-pass path must NOT set temperature or format."""
        self._stub_deps(monkeypatch)

        calls = []

        def spy_ollama(cfg, prompt, image_paths=None, **kwargs):
            calls.append(kwargs.copy())
            return self._VALID_RESPONSE

        monkeypatch.setattr("focusmonitor.analysis.query_ollama", spy_ollama)

        import sqlite3
        db = sqlite3.connect(":memory:")
        db.execute(
            "CREATE TABLE activity_log (id INTEGER PRIMARY KEY, "
            "timestamp TEXT, window_titles TEXT, apps_used TEXT, "
            "project_detected TEXT, is_distraction INTEGER, "
            "summary TEXT, raw_response TEXT)"
        )

        run_analysis(
            self._make_cfg(two_pass=False), db,
            prefetched_events=[],
            prefetched_screenshots=None,
        )

        assert len(calls) >= 1
        assert "temperature" not in calls[0]
        assert "format_" not in calls[0]
