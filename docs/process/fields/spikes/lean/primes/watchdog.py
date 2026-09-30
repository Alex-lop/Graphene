"""Run a command in its own process group and stop the whole group if the machine runs short.

    python3 watchdog.py [--swap-rise-gb 5] [--min-disk-gb 16] [--max-s 1800] -- COMMAND ...

Every 5 s it reads macOS's swap use (`sysctl vm.swapusage`) and the free space of $HOME; it kills the
group (TERM, then KILL) when swap use has risen more than --swap-rise-gb above where it began, when
free disk falls under --min-disk-gb, or after --max-s seconds. It prints the start, the peak and why it
stopped, and exits with the command's code (or 124 when it stopped it). macOS only (sysctl).
"""

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
import time


def swap_mb() -> float:
    out = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True).stdout
    return float(re.search(r"used = ([0-9.]+)M", out)[1])


def disk_gb() -> float:
    return shutil.disk_usage(os.path.expanduser("~")).free / 2**30


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--swap-rise-gb", type=float, default=5)
    ap.add_argument("--min-disk-gb", type=float, default=16)
    ap.add_argument("--max-s", type=float, default=1800)
    ap.add_argument("command", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    s0, t0 = swap_mb(), time.monotonic()
    peak, low = s0, disk_gb()
    print(f"watchdog: start {time.strftime('%T')}, swap {s0:.0f} MB, disk {low:.1f} GB free", flush=True)
    if low < args.min_disk_gb:
        print("watchdog: not started, disk under the floor", flush=True)
        return 3
    proc = subprocess.Popen(command, start_new_session=True)
    why = ""
    while proc.poll() is None:
        time.sleep(5)
        s, d = swap_mb(), disk_gb()
        peak, low = max(peak, s), min(low, d)
        if s - s0 > args.swap_rise_gb * 1024:
            why = f"swap rose {(s - s0) / 1024:.1f} GB"
        elif d < args.min_disk_gb:
            why = f"disk {d:.1f} GB free"
        elif time.monotonic() - t0 > args.max_s:
            why = f"{args.max_s:.0f} s"
        if why:
            os.killpg(proc.pid, signal.SIGTERM)
            time.sleep(3)
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
            break
    code = proc.wait()
    print(
        f"watchdog: end {time.strftime('%T')} after {time.monotonic() - t0:.0f} s, exit {code}; "
        f"swap peak {peak:.0f} MB (+{(peak - s0) / 1024:.1f} GB), disk low {low:.1f} GB"
        + (f"; STOPPED: {why}" if why else ""),
        flush=True,
    )
    return 124 if why else code


if __name__ == "__main__":
    sys.exit(main())
