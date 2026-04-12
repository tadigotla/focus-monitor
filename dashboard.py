#!/usr/bin/env python3
"""Dashboard — backward-compatible entry point."""
from focusmonitor.dashboard import build_dashboard

if __name__ == "__main__":
    import webbrowser
    import tempfile
    from pathlib import Path

    html = build_dashboard()
    if html is None:
        print("No activity database found yet. Run monitor.py first.")
    else:
        out = Path(tempfile.mktemp(suffix=".html"))
        out.write_text(html)
        webbrowser.open(f"file://{out}")
        print(f"📊 Dashboard opened: {out}")
