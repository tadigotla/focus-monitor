#!/usr/bin/env python3
"""Focus Monitor CLI — unified entry point.

Verbs:
  start [pulse|scope]   Run components in the foreground.
                        No argument = both, Ctrl-C tears down both.
  stop                  No-op for foreground sessions (prints a note).
  service install       Write both launchd plists. Does not start them.
  service uninstall     Stop and remove both plists.
  service start         Load both plists into launchd.
  service stop          Bootout both plists from launchd.
  service status        Per-component launchd state.
  setup                 Run probes and scaffold ~/.focus-monitor/.

Deprecated aliases (removed in a future release):
  run         → start
  dashboard   → start pulse
"""

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


# ── Foreground supervision ─────────────────────────────────────────────────


_SHUTDOWN_TIMEOUT_SEC = 10


def _tee(stream, prefix: str, out):
    """Copy lines from `stream` to `out` with a tag prefix."""
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            out.write(f"{prefix} {line}" if not line.startswith(prefix) else line)
            out.flush()
    except (ValueError, OSError):
        pass


def _spawn(component: str) -> subprocess.Popen:
    module = "focusmonitor" if component == "pulse" else "scope.api"
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    return subprocess.Popen(
        [sys.executable, "-m", module],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        cwd=str(REPO_ROOT),
    )


def _terminate(proc: subprocess.Popen, label: str):
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=_SHUTDOWN_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        print(f"[{label}] did not exit within {_SHUTDOWN_TIMEOUT_SEC}s, killing",
              file=sys.stderr)
        proc.kill()
        proc.wait()


def _supervise(children: dict, shutdown: threading.Event) -> int:
    """Run the supervisor loop until `shutdown` is set or a child exits.

    Separated from `cmd_start` so tests can drive the loop without
    installing signal handlers on a non-main thread.
    """
    tee_threads = []
    for name, proc in children.items():
        t = threading.Thread(
            target=_tee,
            args=(proc.stdout, f"[{name}]", sys.stdout),
            daemon=True,
        )
        t.start()
        tee_threads.append(t)

    exit_code = 0
    try:
        while not shutdown.is_set():
            for name, proc in children.items():
                rc = proc.poll()
                if rc is not None:
                    print(f"\n[{name}] exited with status {rc}; tearing down",
                          file=sys.stderr)
                    exit_code = rc if rc != 0 else 1
                    shutdown.set()
                    break
            time.sleep(0.1)
    finally:
        for name, proc in children.items():
            _terminate(proc, name)
        for t in tee_threads:
            t.join(timeout=1)

    return exit_code


def cmd_start(args):
    """Start components in the foreground."""
    component = args.component

    if component == "pulse":
        os.execvp(sys.executable, [sys.executable, "-m", "focusmonitor"])
    if component == "scope":
        os.execvp(sys.executable, [sys.executable, "-m", "scope.api"])

    # Both components — supervise as child processes.
    children = {"pulse": _spawn("pulse"), "scope": _spawn("scope")}

    shutdown = threading.Event()

    def _handle_signal(signum, frame):
        shutdown.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    exit_code = _supervise(children, shutdown)
    sys.exit(exit_code)


def cmd_stop(args):
    """Stop any foreground session in this terminal."""
    # Foreground sessions are owned by the tty's process group. There
    # is no cross-process handle to reach into from another shell, so
    # the honest answer is: Ctrl-C the running session. Background
    # services are managed via `cli.py service stop`.
    print("no foreground session to stop", file=sys.stderr)
    print("(hint: Ctrl-C the running `cli.py start`, or use "
          "`cli.py service stop` for background services)", file=sys.stderr)
    sys.exit(0)


# ── Service management ────────────────────────────────────────────────────


def cmd_service_install(args):
    from focusmonitor import service

    warning = service.legacy_plist_warning()
    if warning:
        print(warning, file=sys.stderr)

    written = service.write_plists()
    for path in written:
        print(f"✅ wrote {path}")
    print("\nRun `python3 cli.py service start` to load them into launchd.")


def cmd_service_uninstall(args):
    from focusmonitor import service

    cmd_service_stop(args)
    for label in (service.PULSE_LABEL, service.SCOPE_LABEL):
        path = service.plist_path(label)
        if path.exists():
            path.unlink()
            print(f"🗑  removed {path}")


def cmd_service_start(args):
    from focusmonitor import service

    for label in (service.PULSE_LABEL, service.SCOPE_LABEL):
        path = service.plist_path(label)
        if not path.exists():
            print(f"⚠️  {label}: plist not installed (run `service install` first)",
                  file=sys.stderr)
            continue
        result = service.bootstrap(path)
        if result.returncode == 0:
            print(f"▶️  {label}: started")
        else:
            print(f"⚠️  {label}: launchctl failed: {result.stderr.strip()}",
                  file=sys.stderr)


def cmd_service_stop(args):
    from focusmonitor import service

    for label in (service.PULSE_LABEL, service.SCOPE_LABEL):
        result = service.bootout(label)
        if result.returncode == 0:
            print(f"⏹  {label}: stopped")


def cmd_service_status(args):
    from focusmonitor import service

    for label in (service.PULSE_LABEL, service.SCOPE_LABEL):
        print(f"{label}: {service.service_state(label)}")


def cmd_setup(args):
    from setup import main
    main()


# ── Deprecated aliases ────────────────────────────────────────────────────


def cmd_run(args):
    print("run is deprecated; use 'start' instead", file=sys.stderr)
    args.component = None
    cmd_start(args)


def cmd_dashboard(args):
    print("dashboard is deprecated; use 'start pulse' instead", file=sys.stderr)
    args.component = "pulse"
    cmd_start(args)


# ── Argparse wiring ───────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        prog="focusmonitor",
        description="Focus Monitor — local AI productivity tracker",
    )
    sub = parser.add_subparsers(dest="command")

    p_start = sub.add_parser("start", help="Run components in the foreground")
    p_start.add_argument("component", nargs="?", choices=["pulse", "scope"],
                         help="Run only one component (default: both)")

    sub.add_parser("stop", help="Stop a foreground session (no-op for background)")

    p_service = sub.add_parser("service", help="Manage launchd background services")
    svc = p_service.add_subparsers(dest="service_command")
    svc.add_parser("install", help="Write both launchd plists")
    svc.add_parser("uninstall", help="Remove both launchd plists")
    svc.add_parser("start", help="Load both services into launchd")
    svc.add_parser("stop", help="Bootout both services from launchd")
    svc.add_parser("status", help="Per-component launchd state")

    sub.add_parser("setup", help="Probe dependencies and scaffold ~/.focus-monitor/")

    # Deprecated.
    sub.add_parser("run", help="(deprecated) alias for `start`")
    sub.add_parser("dashboard", help="(deprecated) alias for `start pulse`")

    args = parser.parse_args()
    cmd = args.command or "start"

    if cmd == "start":
        if not hasattr(args, "component"):
            args.component = None
        cmd_start(args)
    elif cmd == "stop":
        cmd_stop(args)
    elif cmd == "service":
        dispatch = {
            "install": cmd_service_install,
            "uninstall": cmd_service_uninstall,
            "start": cmd_service_start,
            "stop": cmd_service_stop,
            "status": cmd_service_status,
        }
        sc = args.service_command
        if not sc:
            p_service.print_help()
            sys.exit(2)
        dispatch[sc](args)
    elif cmd == "setup":
        cmd_setup(args)
    elif cmd == "run":
        cmd_run(args)
    elif cmd == "dashboard":
        cmd_dashboard(args)


if __name__ == "__main__":
    main()
