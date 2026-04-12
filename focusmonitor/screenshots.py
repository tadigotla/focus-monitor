"""Screenshot capture, deduplication, and cleanup."""

import subprocess
from datetime import datetime, timedelta
from focusmonitor.config import SCREENSHOT_DIR


def take_screenshot():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = SCREENSHOT_DIR / f"screen_{ts}.png"
    subprocess.run(
        ["screencapture", "-x", "-C", str(path)],
        capture_output=True
    )
    if path.exists():
        return path
    return None


def recent_screenshots(cfg):
    """Return the N most recent screenshot paths."""
    n = cfg["screenshots_per_analysis"]
    shots = sorted(SCREENSHOT_DIR.glob("screen_*.png"), key=lambda p: p.name)
    return shots[-n:]


def cleanup_old_screenshots(cfg):
    """Delete screenshots older than screenshot_keep_hours. Returns count deleted."""
    cutoff = datetime.now() - timedelta(hours=cfg["screenshot_keep_hours"])
    deleted = 0
    for p in SCREENSHOT_DIR.glob("screen_*.png"):
        try:
            ts_str = p.stem.replace("screen_", "")
            ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
            if ts < cutoff:
                p.unlink()
                deleted += 1
        except ValueError:
            pass
    return deleted


def deduplicate_screenshots(paths, threshold_pct=2):
    """Remove consecutive near-identical screenshots based on file size.
    Always returns at least 1 screenshot."""
    if not paths:
        return []
    if threshold_pct <= 0:
        return list(paths)

    unique = [paths[0]]
    for i in range(1, len(paths)):
        prev_size = paths[i - 1].stat().st_size
        curr_size = paths[i].stat().st_size
        if prev_size == 0:
            unique.append(paths[i])
            continue
        diff_pct = abs(curr_size - prev_size) / prev_size * 100
        if diff_pct > threshold_pct:
            unique.append(paths[i])

    if not unique:
        unique = [paths[-1]]

    return unique
