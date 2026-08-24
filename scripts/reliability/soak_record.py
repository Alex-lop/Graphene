"""One NDJSON soak record. Compares declared semantic invariants only."""

from __future__ import annotations

import json
import sys

# `--inject-check-fault` is honoured only on the gemini-adk path and is SILENTLY
# IGNORED on scripted-local (verified: no demo_injected_deterministic_check_failure
# label reaches the store), and `mission start --driver adk-fake` fails closed with
# "adk-fake planning is test-only". So the injected-fault flag is BLOCKED under the
# zero-spend cap.
#
# The deterministic failure this soak proves is the fixture scenario's OWN: exactly
# one attempt ends `acceptance_check_failed`, its authorised retry passes, and the
# task still reaches `done`. That is real failure-and-recovery, credential-free and
# reproducible -- it is simply not the flag.
FAILED_CODE = "acceptance_check_failed"


def _json(path: str) -> object | None:
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return None


def main() -> int:
    (mode, i, started, dur, rc, vrc, startp, verifyp, statusp, log,
     orphans, dirty) = sys.argv[1:13]
    start, verify = _json(startp), _json(verifyp)
    status_doc = _json(statusp)
    problems: list[str] = []
    if int(rc):
        problems.append(f"mission start exit {rc}")
    if int(vrc):
        problems.append(f"db verify exit {vrc}")
    if not isinstance(start, dict):
        problems.append("mission start produced no JSON")
    else:
        if start.get("status") != "awaiting_result":
            problems.append(f"status {start.get('status')!r}")
        if start.get("driver") != "scripted-local":
            problems.append("driver drifted")
        if not start.get("parallel_overlap_observed"):
            problems.append("no parallel overlap observed")
    failed = retried = tasks_done = None
    if not isinstance(status_doc, dict):
        problems.append("mission status unreadable")
    else:
        attempts = status_doc.get("attempts", [])
        failed = [a for a in attempts if a.get("result_code") == FAILED_CODE]
        by_task: dict[str, list[dict]] = {}
        for attempt in attempts:
            by_task.setdefault(attempt.get("task_id"), []).append(attempt)
        retried = [
            t for t, items in by_task.items()
            if any(a.get("result_code") == FAILED_CODE for a in items)
            and any(a.get("result_code") == "passed" for a in items)
        ]
        tasks_done = all(t.get("state") == "done" for t in status_doc.get("tasks", []))
        if len(failed) != 1:
            problems.append(f"expected exactly one failed acceptance check, saw {len(failed)}")
        if len(retried) != 1:
            problems.append(f"the failed check was not recovered by a retry: {retried}")
        if not tasks_done:
            problems.append("not every task reached done")
    if not isinstance(verify, dict):
        problems.append("db verify produced no JSON")
    elif not (
        verify.get("status") == "current"
        and verify.get("verified_missions") == verify.get("mission_count") == 1
    ):
        problems.append(f"store verify {verify}")
    if int(orphans) > 0:
        problems.append(f"{orphans} orphan process(es)")
    if int(dirty) > 0:
        problems.append(f"{dirty} repository path(s) changed")
    print(json.dumps({
        "mode": mode, "iteration": int(i), "started": started,
        "duration_s": int(dur), "exit": int(rc), "timed_out": int(rc) == 142,
        "attempt_count": (start or {}).get("attempt_count"),
        "dispatch_batches": (start or {}).get("dispatch_batches"),
        "failed_acceptance_checks": len(failed) if failed is not None else None,
        "recovered_by_retry": retried,
        "all_tasks_done": tasks_done,
        "store_verified": bool(isinstance(verify, dict) and verify.get("status") == "current"),
        "orphan_procs": int(orphans), "repo_unchanged": int(dirty) == 0,
        "ok": not problems, "problems": problems, "log": log,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
