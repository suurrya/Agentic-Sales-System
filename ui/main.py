"""
ui/main.py
==========
Launches both PaperTrail Co. web apps as separate processes.

    python ui/main.py

Ports
-----
  8080  ui/app.py       — Customer portal  (order, login)
  8081  ui/dashboard.py — Manager dashboard (live feed, analytics)

Press Ctrl+C to stop both servers.
"""

import os
import sys
import subprocess
import signal

_here = os.path.dirname(os.path.abspath(__file__))


def main():
    app_path       = os.path.join(_here, "app.py")
    dashboard_path = os.path.join(_here, "dashboard.py")

    print()
    print("=" * 50)
    print("  PaperTrail Co. — Starting servers")
    print("=" * 50)
    print(f"  Customer portal  →  http://localhost:8080")
    print(f"  Manager dashboard →  http://localhost:8081")
    print("  Press Ctrl+C to stop both.")
    print("=" * 50)
    print()

    procs = [
        subprocess.Popen([sys.executable, app_path]),
        subprocess.Popen([sys.executable, dashboard_path]),
    ]

    def _shutdown(sig, frame):
        print("\n  Shutting down both servers...")
        for p in procs:
            p.terminate()
        for p in procs:
            p.wait()
        print("  Done.")
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Wait for both processes — if either exits on its own, shut down the other
    while True:
        for p in procs:
            ret = p.poll()
            if ret is not None:
                print(f"  A server exited unexpectedly (code {ret}). Stopping all.")
                _shutdown(None, None)
        import time
        time.sleep(1)


if __name__ == "__main__":
    main()
