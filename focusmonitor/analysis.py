"""AI analysis pipeline — prompt building, JSON parsing, validation, two-pass."""

import json
import re
from datetime import datetime
from focusmonitor.ollama import query_ollama
from focusmonitor.screenshots import recent_screenshots, deduplicate_screenshots
from focusmonitor.activitywatch import get_aw_events, summarize_aw_events
from focusmonitor.tasks import load_planned_tasks, update_discovered_activities
from focusmonitor.nudges import check_nudges


def parse_analysis_json(raw):
    """Try multiple strategies to extract valid JSON from model response."""
    if not raw:
        return None

    text = raw.strip()

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


def validate_analysis_result(result):
    """Ensure parsed result has all required keys with correct types."""
    defaults = {
        "projects": [],
        "planned_match": [],
        "distractions": [],
        "summary": "",
        "focus_score": -1,
    }

    if not isinstance(result, dict):
        return defaults.copy()

    validated = {}
    for key in defaults:
        val = result.get(key, defaults[key])
        if key == "focus_score":
            if not isinstance(val, (int, float)):
                val = defaults[key]
            else:
                val = max(0, min(100, int(val)))
        elif key == "summary":
            if not isinstance(val, str):
                val = str(val) if val is not None else ""
        else:
            if not isinstance(val, list):
                val = defaults[key]
        validated[key] = val

    return validated


def describe_screenshots(cfg, screenshots):
    """Pass 1: Ask the model to describe what's visible in each screenshot."""
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
                                history_text, screenshot_descriptions=None):
    """Build the classification prompt with explicit scoring criteria."""
    minutes = cfg['analysis_interval_sec'] // 60

    desc_section = ""
    if screenshot_descriptions:
        desc_lines = "\n".join(
            f"  {i+1}. {d}" for i, d in enumerate(screenshot_descriptions)
        )
        desc_section = f"\n## Screenshot observations:\n{desc_lines}\n"

    history_section = f"\n{history_text}\n" if history_text else ""

    return f"""You are a productivity assistant analyzing a user's recent computer activity.

## App usage (last {minutes} minutes):
{app_summary}

## Recent window titles:
{title_summary}

## User's planned tasks:
{task_list}

When matching planned tasks, look for signal keywords in window titles, file names, and app usage. Use the exact task "name" values in your planned_match output.
{desc_section}{history_section}
Classify the user's activity. Use these focus score criteria:
- 80-100: Actively working on one or more planned tasks
- 50-79: Productive work (coding, writing, research) but NOT on planned tasks
- 20-49: Mixed activity with significant distractions
- 0-19: Primarily distracted or idle

{"Consider the recent history above — note any trends in focus or task switching." if history_text else ""}

Respond in this EXACT JSON format and NOTHING else (no markdown, no explanation):
{{
  "projects": ["list of projects/tasks the user was working on"],
  "planned_match": ["which of the user's planned tasks they were actively working on — use exact task names from the list above"],
  "distractions": ["activities that appear to be distractions from planned work"],
  "summary": "One paragraph natural language summary of what the user did",
  "focus_score": <integer 0-100>
}}"""


def run_analysis(cfg, db):
    """Pull AW data + screenshots, ask Ollama to classify activity."""
    print(f"\n🔍 Running analysis at {datetime.now().strftime('%H:%M:%S')} ...")

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

    all_screenshots = recent_screenshots(cfg)
    screenshots = deduplicate_screenshots(
        all_screenshots, cfg["dedup_size_threshold_pct"]
    )
    deduped_count = len(all_screenshots) - len(screenshots)
    if deduped_count > 0:
        print(f"  📎 Deduped {deduped_count} identical screenshots "
              f"({len(screenshots)} unique)")

    history_text = get_recent_history(db, cfg["history_window"])

    if cfg["two_pass_analysis"] and screenshots:
        print("  🔬 Pass 1: Describing screenshots...")
        descriptions = describe_screenshots(cfg, screenshots)
        print("  🧠 Pass 2: Classifying activity...")
        prompt = build_classification_prompt(
            cfg, app_summary, title_summary, task_list,
            history_text, screenshot_descriptions=descriptions
        )
        raw = query_ollama(cfg, prompt)
    else:
        prompt = build_classification_prompt(
            cfg, app_summary, title_summary, task_list, history_text
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

    db.execute("""
        INSERT INTO activity_log (timestamp, window_titles, apps_used,
            project_detected, is_distraction, summary, raw_response)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(),
        json.dumps(top_titles[:15]),
        json.dumps([a for a, _ in top_apps]),
        json.dumps(result["projects"]),
        1 if result["distractions"] else 0,
        result["summary"],
        raw
    ))
    db.commit()

    score = result["focus_score"]
    print(f"  ✅ Focus score: {score}/100")
    print(f"  📋 Projects: {', '.join(result['projects'])}")
    if result["distractions"]:
        print(f"  ⚠️  Distractions: {', '.join(result['distractions'])}")

    update_discovered_activities(result["projects"], top_titles)
    check_nudges(cfg, db, result)

    return result
