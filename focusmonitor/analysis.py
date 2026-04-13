"""AI analysis pipeline — prompt building, JSON parsing, validation, two-pass."""

import json
import re
from datetime import datetime, timedelta
from focusmonitor.ollama import query_ollama
from focusmonitor.screenshots import recent_screenshots, deduplicate_screenshots
from focusmonitor.activitywatch import get_aw_events, summarize_aw_events
from focusmonitor.tasks import load_planned_tasks, update_discovered_activities
from focusmonitor.nudges import check_nudges
from focusmonitor.sessions import aggregate_day, extract_cycle_signals
from focusmonitor.corrections import recent_corrections


def _parse_json_strategies(text):
    """Run the three strategies (direct / fence-strip / brace-scan) over
    `text` and return the first successful parse, or None.

    Split out of `parse_analysis_json` so the same strategy set can be
    re-applied to a preprocessed variant of the raw text.
    """
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if text.startswith("```"):
        lines = text.split("\n")
        stripped = "\n".join(lines[1:])
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip().rsplit("```", 1)[0]
        try:
            return json.loads(stripped.strip())
        except json.JSONDecodeError:
            pass

    match = re.search(r'\{', text)
    if match:
        start = match.start()
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break

    return None


def parse_analysis_json(raw):
    """Try multiple strategies to extract valid JSON from model response."""
    if not raw:
        return None

    result = _parse_json_strategies(raw)
    if result is not None:
        return result

    # Some local models (notably llama3.2-vision via Ollama) emit
    # markdown-style backslash-escapes on underscore-bearing keys —
    # e.g. `"planned\_match"` instead of `"planned_match"`. `\_` is
    # never a valid escape in strict JSON, so replacing it globally
    # can only rescue a previously-failing parse. The original text
    # has already been tried above, so this branch never regresses
    # correctly-formed JSON.
    if "\\_" in raw:
        unescaped = raw.replace("\\_", "_")
        result = _parse_json_strategies(unescaped)
        if result is not None:
            return result

    return None


_CONFIDENCE_LEVELS = ("low", "medium", "high")


def _validate_evidence_list(val):
    """Drop malformed entries from the evidence list; keep well-formed ones.

    A well-formed entry is a dict with string `signal` and string
    `weight`. Anything else (missing keys, non-string values, extra
    types) is silently filtered out.
    """
    if not isinstance(val, list):
        return []
    cleaned = []
    for entry in val:
        if not isinstance(entry, dict):
            continue
        signal = entry.get("signal")
        weight = entry.get("weight")
        if not isinstance(signal, str) or not signal.strip():
            continue
        if not isinstance(weight, str) or not weight.strip():
            continue
        cleaned.append({"signal": signal.strip(), "weight": weight.strip().lower()})
    return cleaned


def validate_analysis_result(result):
    """Ensure parsed result has all required keys with correct types.

    Covers both the legacy fields (`projects`, `planned_match`,
    `distractions`, `summary`, `focus_score`) and the new Pass 2
    additions (`task`, `evidence`, `boundary_confidence`,
    `name_confidence`, `needs_user_input`). Missing or malformed fields
    fall back to safe defaults rather than rejecting the response.
    """
    legacy_defaults = {
        "projects": [],
        "planned_match": [],
        "distractions": [],
        "summary": "",
        "focus_score": -1,
    }
    new_defaults = {
        "task": None,
        "evidence": [],
        "boundary_confidence": "low",
        "name_confidence": "low",
        "needs_user_input": True,
    }

    if not isinstance(result, dict):
        validated = legacy_defaults.copy()
        validated.update(new_defaults)
        return validated

    validated = {}

    for key in legacy_defaults:
        val = result.get(key, legacy_defaults[key])
        if key == "focus_score":
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                val = legacy_defaults[key]
            else:
                val = max(0, min(100, int(val)))
        elif key == "summary":
            if not isinstance(val, str):
                val = str(val) if val is not None else ""
        else:
            if not isinstance(val, list):
                val = legacy_defaults[key]
        validated[key] = val

    # task: string or null
    task = result.get("task", None)
    if task is None:
        validated["task"] = None
    elif isinstance(task, str):
        stripped = task.strip()
        validated["task"] = stripped or None
    else:
        validated["task"] = None

    validated["evidence"] = _validate_evidence_list(result.get("evidence", []))

    needs_input = False

    for key in ("boundary_confidence", "name_confidence"):
        val = result.get(key, None)
        if isinstance(val, str) and val.strip().lower() in _CONFIDENCE_LEVELS:
            validated[key] = val.strip().lower()
        else:
            validated[key] = "low"
            needs_input = True

    raw_needs_input = result.get("needs_user_input", None)
    if isinstance(raw_needs_input, bool):
        validated["needs_user_input"] = raw_needs_input or needs_input
    else:
        validated["needs_user_input"] = needs_input or True

    return validated


def describe_screenshots(cfg, screenshots):
    """Pass 1 (legacy): free-form prose description per screenshot.

    Retained for the `pass1_structured=false` escape hatch. The default
    path is `extract_screenshot_artifacts`, which returns typed artifacts
    the classification prompt can anchor on directly.
    """
    descriptions = []
    for path in screenshots:
        prompt = (
            "Describe what application and activity is visible in this screenshot. "
            "Be brief: app name, content type, what the user is doing. "
            "Respond in 1-2 sentences only."
        )
        desc = query_ollama(cfg, prompt, image_paths=[path])
        if desc:
            descriptions.append(desc.strip())
        else:
            descriptions.append(f"(screenshot: {path.name})")
    return descriptions


# Fields a structured artifact SHALL provide (per openspec change
# task-recognition-loop → specs/contextual-analysis). All fields except
# `one_line_action` are nullable.
_ARTIFACT_FIELDS = (
    "app",
    "workspace",
    "active_file",
    "terminal_cwd",
    "browser_url",
    "browser_tab_titles",
    "one_line_action",
)


_EXTRACTION_PROMPT = """You are inspecting a single screenshot of a developer's screen. Return ONE JSON object with EXACTLY these fields:

{
  "app": string or null,                    // foreground application name, if visible
  "workspace": string or null,              // project/folder name visible in IDE sidebar or title bar, or terminal cwd basename
  "active_file": string or null,            // currently-focused filename, if visible
  "terminal_cwd": string or null,           // a visible terminal working directory, if visible
  "browser_url": string or null,            // a visible browser URL, if visible
  "browser_tab_titles": array of strings or null,  // visible browser tab titles, if any
  "one_line_action": string                 // ≤ 12 words describing what the user appears to be doing
}

Rules:
- If a field is not clearly visible, return null. Do NOT guess.
- `one_line_action` is the only required field.
- Respond with ONLY the JSON object. No markdown, no prose, no code fence."""


def _coerce_artifact(parsed, raw_fallback):
    """Normalize a parsed Pass 1 response into the canonical artifact shape.

    - Every field in `_ARTIFACT_FIELDS` is present in the output.
    - `browser_tab_titles` is either a list of strings or None.
    - `one_line_action` is always a non-empty string (falls back to
      `raw_fallback` if the parsed value is missing or blank).
    """
    artifact = {field: None for field in _ARTIFACT_FIELDS}

    if isinstance(parsed, dict):
        for field in _ARTIFACT_FIELDS:
            if field not in parsed:
                continue
            value = parsed[field]
            if field == "browser_tab_titles":
                if isinstance(value, list):
                    titles = [str(t) for t in value if isinstance(t, (str, int, float))]
                    artifact[field] = titles or None
                elif value is None:
                    artifact[field] = None
            elif field == "one_line_action":
                if isinstance(value, str) and value.strip():
                    artifact[field] = value.strip()
            else:
                if isinstance(value, str) and value.strip():
                    artifact[field] = value.strip()
                elif value is None:
                    artifact[field] = None

    if not artifact["one_line_action"]:
        trimmed = (raw_fallback or "").strip()
        artifact["one_line_action"] = trimmed[:200] if trimmed else "(no description)"

    return artifact


def extract_screenshot_artifacts(cfg, screenshots):
    """Pass 1 (structured): return a typed artifact per screenshot.

    For each screenshot, query Ollama with the structured extraction
    prompt, parse with the shared multi-strategy JSON parser, and coerce
    the result into the canonical artifact shape. When parsing fails
    outright, emit a fallback artifact whose `one_line_action` carries
    the raw response and whose other fields are `null` — never raise.
    """
    artifacts = []
    for path in screenshots:
        raw = query_ollama(cfg, _EXTRACTION_PROMPT, image_paths=[path])
        parsed = parse_analysis_json(raw) if raw else None
        artifact = _coerce_artifact(parsed, raw)
        artifacts.append(artifact)
    return artifacts


def _format_signals(signals):
    """Render the `cycle_signals` dict from a stored correction row as
    a short one-line string for the few-shot block."""
    if not isinstance(signals, dict):
        return "(none)"
    parts = []
    ws = signals.get("workspaces") or []
    cwds = signals.get("terminal_cwds") or []
    hosts = signals.get("browser_hosts") or []
    if ws:
        parts.append(f"workspace={','.join(ws)}")
    if cwds:
        parts.append(f"cwd={','.join(cwds)}")
    if hosts:
        parts.append(f"browser_host={','.join(hosts)}")
    return ", ".join(parts) if parts else "(none)"


def render_few_shot_corrections(records):
    """Render a list of correction dicts as a labeled prompt section.

    Each record is rendered with: timestamp, what the model said
    (task + name_confidence), what the user said (verdict + task/kind),
    and the structured signals visible at the time. Most-recent
    records appear first.
    """
    if not records:
        return ""

    lines = ["## Recent corrections from the user"]
    for r in records:
        ts = (r.get("created_at") or "")[:16]
        model_task = r.get("model_task") or "unclear"
        model_conf = r.get("model_name_confidence", "low")
        verdict = r.get("user_verdict", "corrected")
        user_kind = r.get("user_kind", "other")
        user_task = r.get("user_task")
        signals_str = _format_signals(r.get("signals"))
        note = r.get("user_note")

        if verdict == "confirmed":
            user_part = f"confirmed ({user_kind})"
        elif user_task:
            user_part = f"corrected → {user_task} ({user_kind})"
        else:
            user_part = f"corrected → {user_kind}"

        line = (
            f"  - [{ts}] model said: {model_task} "
            f"(name_confidence={model_conf}). "
            f"user: {user_part}. "
            f"signals: {signals_str}."
        )
        if note:
            line += f" note: {note}"
        lines.append(line)
    return "\n".join(lines)


def _render_artifact(index, artifact):
    """Render one structured artifact as a labeled prompt block.

    Null fields are omitted so the model's attention stays on the
    signal it actually has.
    """
    lines = [f"  Screenshot {index}:"]
    label_map = [
        ("app", "app"),
        ("workspace", "workspace"),
        ("active_file", "active file"),
        ("terminal_cwd", "terminal cwd"),
        ("browser_url", "browser url"),
    ]
    for field, label in label_map:
        value = artifact.get(field)
        if value:
            lines.append(f"    - {label}: {value}")
    tab_titles = artifact.get("browser_tab_titles")
    if tab_titles:
        joined = ", ".join(tab_titles)
        lines.append(f"    - browser tab titles: {joined}")
    action = artifact.get("one_line_action")
    if action:
        lines.append(f"    - action: {action}")
    return "\n".join(lines)


def get_recent_history(db, window=3):
    """Fetch summaries and focus scores from recent analyses."""
    if window <= 0:
        return ""
    rows = db.execute(
        "SELECT timestamp, summary, raw_response FROM activity_log "
        "ORDER BY timestamp DESC LIMIT ?",
        (window,)
    ).fetchall()

    if not rows:
        return ""

    lines = ["## Recent activity history:"]
    for ts, summary, raw in reversed(rows):
        score = -1
        if raw:
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                score = parsed.get("focus_score", -1)
            except (json.JSONDecodeError, AttributeError):
                pass
        score_str = f"{score}/100" if score >= 0 else "unknown"
        lines.append(f"  - [{ts[:16]}] Focus: {score_str} — {summary[:150]}")

    return "\n".join(lines)


def build_classification_prompt(cfg, app_summary, title_summary, task_list,
                                history_text, screenshot_descriptions=None,
                                screenshot_artifacts=None,
                                corrections=None):
    """Build the classification prompt with explicit scoring criteria.

    Pass `screenshot_artifacts` (a list of dicts from
    `extract_screenshot_artifacts`) to render structured Pass 1 output,
    or `screenshot_descriptions` (a list of strings) for the legacy
    free-form path. When both are supplied, structured artifacts win.

    Pass `corrections` — a list of correction dicts as returned by
    `corrections.recent_corrections` — to inject a few-shot block of
    recent user corrections and confirmations. When None or empty,
    the block is omitted entirely (no empty header).
    """
    minutes = cfg['analysis_interval_sec'] // 60

    desc_section = ""
    if screenshot_artifacts:
        artifact_lines = "\n".join(
            _render_artifact(i + 1, art)
            for i, art in enumerate(screenshot_artifacts)
        )
        desc_section = (
            "\n## Screenshot artifacts (structured extraction):\n"
            f"{artifact_lines}\n"
        )
    elif screenshot_descriptions:
        desc_lines = "\n".join(
            f"  {i+1}. {d}" for i, d in enumerate(screenshot_descriptions)
        )
        desc_section = f"\n## Screenshot observations:\n{desc_lines}\n"

    corrections_section = ""
    if corrections:
        rendered = render_few_shot_corrections(corrections)
        if rendered:
            corrections_section = f"\n{rendered}\n"

    history_section = f"\n{history_text}\n" if history_text else ""

    return f"""You are a productivity assistant analyzing a user's recent computer activity.

## App usage (last {minutes} minutes):
{app_summary}

## Recent window titles:
{title_summary}

## User's planned tasks:
{task_list}

When matching planned tasks, look for signal keywords in window titles, file names, and app usage. Use the exact task "name" values in your planned_match output.
{desc_section}{corrections_section}{history_section}
Classify the user's activity. Use these focus score criteria:
- 80-100: Actively working on one or more planned tasks
- 50-79: Productive work (coding, writing, research) but NOT on planned tasks
- 20-49: Mixed activity with significant distractions
- 0-19: Primarily distracted or idle

{"Consider the recent history above — note any trends in focus or task switching." if history_text else ""}

## Evidence and confidence

In addition to the legacy fields, your response MUST include:

- `task`: the single best-guess canonical task name for this window, or null when signals are genuinely mixed. This may be a planned task name or a short descriptor.
- `evidence`: a list of {{signal, weight}} objects tying your classification to observable signals from the structured artifacts, app usage, or window titles. Each `signal` is a short human-readable string (for example: "vscode workspace: focus-monitor", "terminal pwd matches", "github PR url"). `weight` is one of "strong", "medium", "weak".
- `boundary_confidence`: one of "low" | "medium" | "high". HIGH means the signals clearly represent ONE coherent activity. LOW means you see evidence of multiple unrelated activities mixed within this window.
- `name_confidence`: one of "low" | "medium" | "high". HIGH means the named `task` is clearly the right label. LOW means you cannot commit to a specific task name, even when boundaries look coherent.
- `needs_user_input`: true when signals are insufficient to identify a task (you should also set task=null and name_confidence="low"); false otherwise.

Returning `task=null`, `name_confidence="low"`, `needs_user_input=true`, and an empty `evidence` array is a CORRECT, EXPECTED outcome when the signals are genuinely unclear. Do NOT invent a task to fill the field.

An empty `evidence` array is permitted ONLY when `task` is null and `name_confidence` is "low". Otherwise your `evidence` must list at least one signal supporting the named task.

Confidence anchors:

- boundary_confidence=high: one workspace / one repo / consistent window titles throughout
- boundary_confidence=medium: predominantly one activity with minor excursions
- boundary_confidence=low: two or more unrelated workspaces or apps share the window
- name_confidence=high: workspace or cwd matches a planned task signal, evidence is consistent
- name_confidence=medium: strong category (e.g. "dev work") but specific task is a guess
- name_confidence=low: cannot commit to a specific task name

Respond in this EXACT JSON format and NOTHING else (no markdown, no explanation):
{{
  "projects": ["list of projects/tasks the user was working on"],
  "planned_match": ["which of the user's planned tasks they were actively working on — use exact task names from the list above"],
  "distractions": ["activities that appear to be distractions from planned work"],
  "summary": "One paragraph natural language summary of what the user did",
  "focus_score": <integer 0-100>,
  "task": "<single best-guess task name, or null>",
  "evidence": [{{"signal": "<short string>", "weight": "strong|medium|weak"}}],
  "boundary_confidence": "low|medium|high",
  "name_confidence": "low|medium|high",
  "needs_user_input": <true|false>
}}"""


def run_analysis(cfg, db, *, prefetched_events=None, prefetched_screenshots=None):
    """Pull AW data + screenshots, ask Ollama to classify activity."""
    cycle_end_dt = datetime.now()
    print(f"\n🔍 Running analysis at {cycle_end_dt.strftime('%H:%M:%S')} ...")

    if prefetched_events is not None:
        events = prefetched_events
    else:
        events = get_aw_events(cfg, minutes=cfg["analysis_interval_sec"] // 60)
    top_apps, top_titles = summarize_aw_events(events)
    tasks = load_planned_tasks()

    app_summary = "\n".join(f"  - {app}: {int(dur)}s" for app, dur in top_apps)
    title_summary = "\n".join(f"  - {t}" for t in top_titles[:15])

    if tasks:
        task_lines = []
        for t in tasks:
            line = f'  - "{t["name"]}"'
            if t["signals"]:
                line += f' — signals: {", ".join(t["signals"])}'
            if t["notes"]:
                line += f'\n    ({t["notes"]})'
            task_lines.append(line)
        task_list = "\n".join(task_lines)
    else:
        task_list = "  (none specified)"

    if prefetched_screenshots is not None:
        all_screenshots = prefetched_screenshots
    else:
        all_screenshots = recent_screenshots(cfg)
    screenshots = deduplicate_screenshots(
        all_screenshots, cfg["dedup_size_threshold_pct"]
    )
    deduped_count = len(all_screenshots) - len(screenshots)
    if deduped_count > 0:
        print(f"  📎 Deduped {deduped_count} identical screenshots "
              f"({len(screenshots)} unique)")

    history_text = get_recent_history(db, cfg["history_window"])
    few_shot_corrections = recent_corrections(
        db, int(cfg.get("corrections_few_shot_n", 5))
    )

    pass1_artifacts = None
    if cfg["two_pass_analysis"] and screenshots:
        if cfg.get("pass1_structured", True):
            print("  🔬 Pass 1: Extracting structured artifacts...")
            pass1_artifacts = extract_screenshot_artifacts(cfg, screenshots)
            print("  🧠 Pass 2: Classifying activity...")
            prompt = build_classification_prompt(
                cfg, app_summary, title_summary, task_list,
                history_text, screenshot_artifacts=pass1_artifacts,
                corrections=few_shot_corrections,
            )
        else:
            print("  🔬 Pass 1: Describing screenshots...")
            descriptions = describe_screenshots(cfg, screenshots)
            print("  🧠 Pass 2: Classifying activity...")
            prompt = build_classification_prompt(
                cfg, app_summary, title_summary, task_list,
                history_text, screenshot_descriptions=descriptions,
                corrections=few_shot_corrections,
            )
        raw = query_ollama(cfg, prompt)
    else:
        prompt = build_classification_prompt(
            cfg, app_summary, title_summary, task_list, history_text,
            corrections=few_shot_corrections,
        )
        raw = query_ollama(
            cfg, prompt,
            image_paths=screenshots if screenshots else None
        )

    if not raw:
        print("  ⚠️  No response from Ollama, skipping.")
        return

    result = parse_analysis_json(raw)
    if result is None:
        max_retries = cfg["max_parse_retries"]
        for attempt in range(max_retries):
            print(f"  🔄 JSON parse failed, retry {attempt + 1}/{max_retries}...")
            retry_prompt = (
                "Your previous response was not valid JSON. "
                "Return ONLY a valid JSON object with these keys: "
                "projects, planned_match, distractions, summary, focus_score. "
                "No markdown, no explanation, just the JSON object.\n\n"
                f"Your previous response was:\n{raw[:500]}"
            )
            raw_retry = query_ollama(cfg, retry_prompt)
            if raw_retry:
                result = parse_analysis_json(raw_retry)
                if result is not None:
                    raw = raw_retry
                    break

    if result is None:
        result = {"summary": raw, "projects": [], "planned_match": [],
                  "distractions": [], "focus_score": -1}
    result = validate_analysis_result(result)

    # Stash Pass 1 signals and cycle bounds alongside the validated
    # result so the session aggregator can reconstruct a cycle dict
    # from activity_log rows later. The dashboard/history helpers
    # simply ignore unknown keys in this blob, so this is additive.
    cycle_end_iso = cycle_end_dt.isoformat()
    cycle_start_iso = (
        cycle_end_dt - timedelta(seconds=cfg["analysis_interval_sec"])
    ).isoformat()
    result["cycle_start"] = cycle_start_iso
    result["cycle_end"] = cycle_end_iso
    if pass1_artifacts is not None:
        result["pass1_artifacts"] = pass1_artifacts
        result["cycle_signals"] = extract_cycle_signals(pass1_artifacts)
    else:
        result["cycle_signals"] = {
            "workspaces": [],
            "terminal_cwds": [],
            "browser_hosts": [],
        }

    # project_detected is the raw LLM output for forensic trace; planned-task
    # filtering happens downstream in update_discovered_activities.
    # raw_response stores the validated dict as JSON so the new Pass 2
    # fields (task, evidence, boundary/name confidence, needs_user_input)
    # are always present for downstream readers — matching the shape the
    # dashboard and history helpers already expect.
    db.execute("""
        INSERT INTO activity_log (timestamp, window_titles, apps_used,
            project_detected, is_distraction, summary, raw_response)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        cycle_end_iso,
        json.dumps(top_titles[:15]),
        json.dumps([a for a, _ in top_apps]),
        json.dumps(result["projects"]),
        1 if result["distractions"] else 0,
        result["summary"],
        json.dumps(result),
    ))
    db.commit()

    # Re-aggregate today's sessions. Cheap for the small per-day
    # corpus (≤ 100 cycles); idempotent by design. Failures here
    # should not break the analysis cycle — wrap in a broad except
    # that logs and continues.
    if cfg.get("session_aggregation_enabled", True):
        try:
            aggregate_day(db, cfg, cycle_end_dt.date().isoformat())
        except Exception as e:
            print(f"  ⚠️  Session aggregation failed: {e}")

    score = result["focus_score"]
    print(f"  ✅ Focus score: {score}/100")
    print(f"  📋 Projects: {', '.join(result['projects'])}")
    if result["distractions"]:
        print(f"  ⚠️  Distractions: {', '.join(result['distractions'])}")

    update_discovered_activities(result["projects"], top_titles, tasks)
    if not cfg.get("batch_analysis", False):
        check_nudges(cfg, db, result)

    return result


def batch_analyze(cfg, db):
    """Process all pending collection data in analysis-interval-sized windows."""
    rows = db.execute(
        "SELECT id, collected_at, screenshot_path, aw_events_json "
        "FROM pending_data WHERE processed = 0 ORDER BY collected_at"
    ).fetchall()

    if not rows:
        print("\n📦 Batch: no pending data to process.")
        return

    print(f"\n📦 Batch: processing {len(rows)} pending rows...")

    window_sec = cfg["analysis_interval_sec"]
    windows = []
    current_window = []
    window_start = None

    for row in rows:
        row_id, collected_at, screenshot_path, aw_json = row
        if window_start is None:
            window_start = collected_at
        elapsed = (
            datetime.fromisoformat(collected_at)
            - datetime.fromisoformat(window_start)
        ).total_seconds()
        if elapsed >= window_sec and current_window:
            windows.append(current_window)
            current_window = []
            window_start = collected_at
        current_window.append(row)

    if current_window:
        windows.append(current_window)

    print(f"  📊 Grouped into {len(windows)} analysis windows")

    for i, window in enumerate(windows):
        row_ids = []
        merged_events = []
        screenshot_paths = []
        for row_id, collected_at, screenshot_path, aw_json in window:
            row_ids.append(row_id)
            try:
                events = json.loads(aw_json)
                if isinstance(events, list):
                    merged_events.extend(events)
            except (json.JSONDecodeError, TypeError):
                pass
            if screenshot_path:
                from pathlib import Path
                p = Path(screenshot_path)
                if p.exists():
                    screenshot_paths.append(p)

        print(f"\n  📦 Window {i + 1}/{len(windows)}: "
              f"{len(window)} rows, {len(screenshot_paths)} screenshots")

        run_analysis(
            cfg, db,
            prefetched_events=merged_events,
            prefetched_screenshots=screenshot_paths or None,
        )

        placeholders = ",".join("?" for _ in row_ids)
        db.execute(
            f"UPDATE pending_data SET processed = 1 WHERE id IN ({placeholders})",
            row_ids,
        )
        db.commit()

    print(f"\n  ✅ Batch complete: {len(windows)} windows processed")
