#!/usr/bin/env python3
"""
Setup script — probes dependencies and scaffolds ~/.focus-monitor/.

Run once: python3 setup.py

This script no longer writes the launchd plist. Background-service
management is owned by `python3 cli.py service install` / `service start`
— see the README's Quick Start.
"""

import sys
from pathlib import Path


# Map probe states to the icon used in setup's console output.
_STATE_ICON = {
    "ok": "✅",
    "missing": "❌",
    "daemon_down": "⚠️ ",
    "wrong_state": "⚠️ ",
    "unknown": "⚠️ ",
}


def _print_probe(label, result):
    """Print a probe result with the right icon + fix-it command (if any)."""
    icon = _STATE_ICON.get(result.state, "⚠️ ")
    print(f"  {icon} {label}: {result.message}")
    if result.next_command:
        print(f"     → {result.next_command}")


def main():
    print("=" * 50)
    print("  Focus Monitor — Setup")
    print("=" * 50)

    # focusmonitor.install lives inside the runtime package and uses
    # stdlib only — safe to import here before the dev venv exists.
    sys.path.insert(0, str(Path(__file__).parent))
    from focusmonitor.install import probe_ollama, probe_activitywatch

    print("\nChecking dependencies...")

    ollama_result = probe_ollama()
    _print_probe("Ollama", ollama_result)

    aw_result = probe_activitywatch()
    _print_probe("ActivityWatch", aw_result)

    print("  ✅ screencapture (built-in)")

    # macOS Screen Recording permission — not automatable, so we print the
    # reminder inline where it lands before the first screencapture call.
    print("\n⚠️  IMPORTANT: You need to grant Screen Recording permission.")
    print("   System Settings → Privacy & Security → Screen Recording")
    print("   Add Terminal (or your terminal app) to the allowed list.\n")

    # Bootstrap ~/.focus-monitor/ with defaults so the user can edit
    # planned_tasks.json immediately after setup completes.
    from focusmonitor.config import load_config, TASKS_JSON_FILE
    load_config()
    print(f"  ✅ Scaffolded {TASKS_JSON_FILE.parent}")

    # Warn about the legacy launchd agent if the user is upgrading.
    from focusmonitor.service import legacy_plist_warning
    warning = legacy_plist_warning()
    if warning:
        print(warning)

    cli_script = (Path(__file__).parent / "cli.py").resolve()
    print(f"""
Next steps:
  1. Edit your planned tasks:
     nano {TASKS_JSON_FILE}

  2. Run Focus Monitor in the foreground to test:
     python3 {cli_script} start

  3. Once happy, install and start the background services:
     python3 {cli_script} service install
     python3 {cli_script} service start

  4. To stop the background services later:
     python3 {cli_script} service stop

  5. View your dashboard anytime Pulse is running:
     http://localhost:9876
""")


if __name__ == "__main__":
    main()
