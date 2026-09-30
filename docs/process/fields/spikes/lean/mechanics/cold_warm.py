"""One-lemma check, cold (a fresh `lake env lean` per check) against warm (one REPL, Mathlib imported once).

Run from this directory:  python3 cold_warm.py REPL_BINARY [RUNS [COLD_RUNS [MODULE]]]
(MODULE is what the REPL imports, Mathlib by default.)
(logs/cold_warm-run1.log sent the same lemma text each time; now each is named clean1, clean2, ...)
Prints one line per run and a JSON summary at the end. Timeouts use subprocess's own timeout.
"""

import json
import statistics
import subprocess
import sys
import time

LEMMA = """theorem clean{i} (a b : ℤ) (ha : a % 4 = 1) (hb : b % 4 = 2) : (a * b) % 4 = 2 := by
  rw [Int.mul_emod, ha, hb]; norm_num

#print axioms clean{i}"""


def rss_mb(pid: int) -> int:
    """Resident memory of pid and its children (lake env runs the repl as a child)."""
    kids = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout.split()
    pids = ",".join([str(pid), *kids])
    out = subprocess.run(["ps", "-o", "rss=", "-p", pids], capture_output=True, text=True)
    return sum(int(x) for x in out.stdout.split()) // 1024


def cold(runs: int) -> list[float]:
    times = []
    for i in range(runs):
        t0 = time.monotonic()
        cmd = ["lake", "env", "lean", "Measure/Clean.lean"]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        dt = time.monotonic() - t0
        times.append(dt)
        print(f"cold {i + 1}: rc={p.returncode} {dt:.2f}s out={p.stdout.strip()!r}", flush=True)
    return times


def warm(repl: str, runs: int, module: str) -> tuple[float, list[float], int]:
    proc = subprocess.Popen(["lake", "env", repl], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    def send(cmd: dict) -> tuple[dict, float]:
        t0 = time.monotonic()
        proc.stdin.write(json.dumps(cmd) + "\n\n")
        proc.stdin.flush()
        lines = []
        while True:  # a response is a JSON object followed by a blank line
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError("repl exited")
            if not line.strip() and lines:
                break
            lines.append(line)
        return json.loads("".join(lines)), time.monotonic() - t0

    resp, t_import = send({"cmd": f"import {module}"})
    print(f"warm import: {t_import:.2f}s env={resp.get('env')} messages={resp.get('messages')}", flush=True)
    env = resp["env"]
    times = []
    for i in range(runs):
        resp, dt = send({"cmd": LEMMA.format(i=i + 1), "env": env})  # a new name each time
        times.append(dt)
        msgs = [m["data"] for m in resp.get("messages", [])]
        print(f"warm {i + 1}: {dt:.3f}s messages={msgs}", flush=True)
    rss = rss_mb(proc.pid)
    proc.stdin.close()
    proc.wait(timeout=60)
    return t_import, times, rss


def main() -> None:
    repl = sys.argv[1]
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    cold_runs = int(sys.argv[3]) if len(sys.argv) > 3 else runs  # 0 measures the warm side only
    cold_times = cold(cold_runs)
    module = sys.argv[4] if len(sys.argv) > 4 else "Mathlib"
    t_import, warm_times, rss = warm(repl, runs, module)
    print(json.dumps({
        "cold_s": [round(t, 2) for t in cold_times],
        "cold_median_s": round(statistics.median(cold_times), 2) if cold_times else None,
        "warm_module": module,
        "warm_import_s": round(t_import, 2),
        "warm_s": [round(t, 3) for t in warm_times],
        "warm_median_s": round(statistics.median(warm_times), 3),
        "repl_rss_mb_after": rss,
    }))


if __name__ == "__main__":
    main()
