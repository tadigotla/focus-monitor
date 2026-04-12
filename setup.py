#!/usr/bin/env python3
"""
Setup script — creates the launchd plist so Focus Monitor runs automatically.
Run once: python3 setup.py
"""

import os
import subprocess
import sys
from pathlib import Path

PLIST_NAME = "com.focusmonitor.agent"
PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST_PATH = PLIST_DIR / f"{PLIST_NAME}.plist"
MONITOR_SCRIPT = Path(__file__).parent / "monitor.py"
LOG_DIR = Path.home() / ".focus-monitor" / "logs"


def create_plist():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_DIR.mkdir(parents=True, exist_ok=True)

    python = subprocess.run(["which", "python3"], capture_output=True, text=True).stdout.strip()

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>{MONITOR_SCRIPT.resolve()}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{LOG_DIR / 'stdout.log'}</string>
    <key>StandardErrorPath</key>
    <string>{LOG_DIR / 'stderr.log'}</string>
</dict>
</plist>
"""
    PLIST_PATH.write_text(plist)
    print(f"✅ Created {PLIST_PATH}")


def main():
    print("=" * 50)
    print("  Focus Monitor — Setup")
    print("=" * 50)

    # Check dependencies
    print("\nChecking dependencies...")

    # Ollama
    r = subprocess.run(["which", "ollama"], capture_output=True)
    if r.returncode != 0:
        print("❌ Ollama not found. Install: brew install ollama")
        sys.exit(1)
    print("  ✅ Ollama")

    # Check if recommended model is available
    model_check = subprocess.run(
        ["ollama", "list"], capture_output=True, text=True
    )
    if "llama3.2-vision" not in model_check.stdout:
        print("  ⚠️  Recommended model 'llama3.2-vision' not found.")
        print("     Pull it with: ollama pull llama3.2-vision")
    else:
        print("  ✅ llama3.2-vision model")

    # ActivityWatch
    aw = Path("/Applications/ActivityWatch.app")
    if not aw.exists():
        aw = Path.home() / "Applications" / "ActivityWatch.app"
    if aw.exists():
        print("  ✅ ActivityWatch")
    else:
        print("  ⚠️  ActivityWatch.app not found — make sure it's running")

    # screencapture
    print("  ✅ screencapture (built-in)")

    # macOS Screen Recording permission
    print("\n⚠️  IMPORTANT: You need to grant Screen Recording permission.")
    print("   System Settings → Privacy & Security → Screen Recording")
    print("   Add Terminal (or your terminal app) to the allowed list.\n")

    create_plist()

    # Bootstrap ~/.focus-monitor/ with defaults so the user can edit
    # planned_tasks.json immediately after setup completes.
    sys.path.insert(0, str(Path(__file__).parent))
    from focusmonitor.config import load_config, TASKS_JSON_FILE
    load_config()
    print(f"  ✅ Scaffolded {TASKS_JSON_FILE.parent}")

    cli_script = Path(__file__).parent / "cli.py"
    print(f"""
Next steps:
  1. Edit your planned tasks:
     nano ~/.focus-monitor/planned_tasks.txt

  2. Start the monitor manually first to test:
     python3 {cli_script.resolve()} run

  3. Once happy, load the background agent:
     launchctl load {PLIST_PATH}

  4. To stop it:
     launchctl unload {PLIST_PATH}

  5. View your dashboard anytime:
     http://localhost:9876  (available when monitor is running)
     python3 {cli_script.resolve()} dashboard  (standalone)
""")


if __name__ == "__main__":
    main()
