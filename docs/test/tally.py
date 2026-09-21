#!/usr/bin/env python3
"""One arm of one task, counted. Nothing here is estimated, judged or asked of a model.

    docs/test/tally.py <repo> --base <sha> --intent <intent_globs.txt> \\
        --accept <accept.py> [--quality <quality.py>] --arm <prompt|graphene> \\
        --runlog <runlog.jsonl>

Every number comes from one of four places and the output says which:

  git                 what changed against the base commit, and how many lines that is
  .graphene/graphene.db   every write the hooks recorded as it happened, and every refusal
  .graphene/runs/     what an executor `graphene run` started printed, cost included
  the run log         what the person did, and what an executor the person started cost

A recorded write is an Edit/Write/MultiEdit/NotebookEdit event, *and* the change list Claude Code
attaches to a Bash call. Both count, because the first real run against this harness did all of its
editing through a shell heredoc and none of it through a file tool; the output keeps the two apart
so anyone can see which record a number came from.

Three things changed after the 20 September run, because the numbers it printed were wrong:

1. **Churn is counted once per file, not once per record.** A file that appears both as a `Write`
   event and in a `Bash` change list used to have both counted; `.plan-logs.json` written once and
   removed once came out as 26 lines of "rework". The two records are two views of the same
   filesystem, so per file the larger of the two is taken, never their sum. That makes rework a
   lower bound where it used to be an inflated upper bound, and `churn_double_counted_lines` says
   how much the old arithmetic would have added.
2. **A file created and removed inside the run is not rework.** Not in the base commit and not on
   disk at the end: nobody rewrote code, a scratch file came and went. Its churn is reported as
   `transient_churn_lines` and kept out of `rework_lines`.
3. **Executor cost is read out of `.graphene/runs/`.** `graphene run` writes each executor's
   stdout+stderr to `.graphene/runs/<node>-<attempt>.txt` and parses none of it; when the executor
   was run with `--output-format json` that file *is* the vendor's JSON object, so the cost is
   recoverable after all. The run log no longer has to carry it.

The scope matcher is Graphene's own (``graphene_debrief.plan.in_scope``), so "outside intent" here
means exactly what "outside a node's scope" means to the hook that refuses a write.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from graphene_debrief.plan import in_scope  # noqa: E402

WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
REFUSAL_KINDS = ("denied", "breach", "refused")
# The harness's own two directories. `graphene init` runs in both arms, so both arms grow a store
# and a hooks file; neither is the task, and neither is anybody's change.
OURS = (".graphene/", ".claude/")


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return done.stdout


# `graphene run --parallel N` gives each leaf a worktree under .graphene/worktrees/<node>/, and the
# hook records what an executor does in there against the main repo's root, so every one of those
# writes arrives looking like a write to .graphene/. It is a write to the file it names.
WORKTREE = re.compile(r"^\.graphene/worktrees/[^/]+/")


def in_repo(path: str) -> str:
    return WORKTREE.sub("", path)


def ours(path: str) -> bool:
    return path.startswith(OURS)


def changed_files(repo: Path, base: str) -> list[str]:
    """Everything that differs from the base commit: tracked changes (committed or not) and files
    git does not know about yet."""
    tracked = git(repo, "diff", "--name-only", base).split("\n")
    untracked = git(repo, "ls-files", "--others", "--exclude-standard").split("\n")
    return sorted({p for p in tracked + untracked if p and not ours(p)})


def final_diff_lines(repo: Path, base: str) -> int:
    """Added + removed lines in the final state against the base: numstat for what git tracks, and
    the whole of every new file it does not."""
    total = 0
    for line in git(repo, "diff", "--numstat", base).splitlines():
        added, removed, path = (line.split("\t", 2) + ["", "", ""])[:3]
        if added == "-" or ours(path):  # binary
            continue
        total += int(added or 0) + int(removed or 0)
    for path in git(repo, "ls-files", "--others", "--exclude-standard").splitlines():
        if not path or ours(path):
            continue
        try:
            total += len((repo / path).read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeDecodeError):
            pass
    return total


def edit_size(old: str | None, new: str) -> int:
    """Added + removed lines in one recorded write, the way a diff counts them."""
    diff = difflib.unified_diff((old or "").splitlines(), new.splitlines(), n=0, lineterm="")
    return sum(1 for ln in diff if ln[:1] in "+-" and not ln.startswith(("+++", "---")))


def shell_writes(response, repo: Path, notes: list[str]) -> tuple[dict[str, int], bool]:
    """A Bash call's change list: ({repo-relative path: added+removed lines}, lines were countable).

    The first real executor run against this harness edited every file through a `python3 - <<EOF`
    heredoc, so nothing came through Edit or Write at all. Claude Code attaches what a command
    changed to the call as `bashEditDiff`, and that is where those writes are. Left out, the record
    would say an arm touched nothing.
    """
    diff = response.get("bashEditDiff") if isinstance(response, dict) else None
    if not isinstance(diff, dict):
        return {}, True
    if diff.get("shared"):
        notes.append("a Bash change list was marked shared (another command's changes may be in it)")
    counted: dict[str, int] = {}
    for entry in diff.get("files") or []:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("filePath") or "")
        lines = sum(
            1 for hunk in entry.get("hunks") or [] for ln in (hunk.get("lines") or []) if str(ln)[:1] in "+-"
        )
        counted[path] = counted.get(path, 0) + lines
    # `changedFiles` repeats the same paths as a bare list; a path in it with no entry in `files`
    # is one whose lines nobody can count.
    listed = [p for p in diff.get("changedFiles") or [] if isinstance(p, str)]
    countable = not [p for p in listed if p not in counted] and not diff.get("unavailable")
    if diff.get("moreFiles"):
        notes.append(f"a Bash change list left out {diff['moreFiles']} further files")
    for path in listed:
        counted.setdefault(path, 0)
    out: dict[str, int] = {}
    for path, lines in counted.items():
        if not path:
            continue
        try:
            rel = in_repo(str(Path(path).resolve().relative_to(repo)))
        except ValueError:
            continue  # written outside this repo
        out[rel] = out.get(rel, 0) + lines
    return out, countable


def read_store(db: Path, repo: Path, intent: list[str], notes: list[str]) -> dict:
    """Everything the record says: what was written where, how much churn, what was refused.

    Churn comes back keyed by file (`tool_churn`, `shell_churn`) rather than already summed, so the
    caller can take the larger of the two records per file instead of adding them together.
    """
    blank = {"by_tool": [], "by_shell": [], "tool_churn": {}, "shell_churn": {}, "refusals": {}, "events": 0}
    if not db.exists():
        notes.append(f"no store at {db}: the recorded numbers are 0 and prove nothing")
        return blank
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    marks = ", ".join("?" * len(WRITE_TOOLS))
    rows = conn.execute(
        f"SELECT file_path, old_content, new_content FROM tool_events "
        f"WHERE tool IN ({marks}) AND (success IS NULL OR success != 0) ORDER BY timestamp, rowid",
        WRITE_TOOLS,
    ).fetchall()
    by_tool, tool_churn, skipped = [], {}, 0
    for row in rows:
        path = in_repo(row["file_path"] or "")
        if not path or path.startswith("/"):
            skipped += 1  # a write outside this repo, or one the recorder could not place
            continue
        if not ours(path) and not in_scope(path, intent):
            by_tool.append(path)
        if row["new_content"] is None:
            skipped += 1  # the payload was too big to keep, or the tool carried no content
            continue
        if ours(path):
            continue  # .graphene/ and .claude/ are the harness's, in both arms; not anybody's change
        tool_churn[path] = tool_churn.get(path, 0) + edit_size(row["old_content"], row["new_content"])
    if skipped:
        notes.append(f"{skipped} recorded write events had no usable content and were not counted as rework")

    by_shell, shell_churn = [], {}
    for (raw,) in conn.execute(
        "SELECT response FROM tool_events WHERE tool = 'Bash' AND (success IS NULL OR success != 0)"
    ).fetchall():
        try:
            response = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            continue
        per_file, countable = shell_writes(response, repo, notes)
        for path, lines in per_file.items():
            if ours(path):
                continue
            shell_churn[path] = shell_churn.get(path, 0) + lines
        if not countable:
            notes.append("a Bash change list had no hunks to count; its lines are missing from rework")
        by_shell += [p for p in per_file if not ours(p) and not in_scope(p, intent)]

    refusals = {
        k: int(n)
        for k, n in conn.execute(
            f"SELECT kind, COUNT(*) FROM node_log WHERE kind IN ({', '.join('?' * len(REFUSAL_KINDS))}) "
            "GROUP BY kind",
            REFUSAL_KINDS,
        ).fetchall()
    }
    conn.close()
    if not rows and by_shell:
        notes.append("nothing came through Edit or Write: this executor writes through the shell")
    return {
        "by_tool": sorted(set(by_tool)),
        "by_shell": sorted(set(by_shell)),
        "tool_churn": tool_churn,
        "shell_churn": shell_churn,
        "refusals": refusals,
        "events": len(rows),
    }


def runs_cost(runs: Path, notes: list[str]) -> dict:
    """What the executors `graphene run` started cost, out of `.graphene/runs/<node>-<attempt>.txt`.

    `graphene run` writes its executor's stdout and stderr there and parses neither. With
    `--with '… --output-format json'` that text is the vendor's own JSON object, so the cost is in
    the file even though nothing in Graphene ever looks at it. Files that are not that JSON are
    counted as calls whose cost is unknown, and the output says how many.
    """
    out = {"cost_usd": 0.0, "turns": 0, "calls": 0, "unpriced": 0, "sessions": []}
    if not runs.is_dir():
        return out
    for path in sorted(runs.glob("*.txt")):
        out["calls"] += 1
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        start = text.find("{")
        try:
            data = json.loads(text[start:]) if start >= 0 else None
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict) or not ("total_cost_usd" in data or "cost_usd" in data):
            out["unpriced"] += 1
            notes.append(f"{path.name} is not an --output-format json result: its cost is unknown")
            continue
        out["cost_usd"] += float(data.get("total_cost_usd") or data.get("cost_usd") or 0)
        out["turns"] += int(data.get("num_turns") or data.get("turns") or 0)
        if data.get("session_id"):
            out["sessions"].append(str(data["session_id"]))
    out["cost_usd"] = round(out["cost_usd"], 6)
    return out


def seconds(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        from datetime import datetime

        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def read_runlog(path: Path, notes: list[str]) -> dict:
    entries = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            notes.append(f"{path.name}:{number} is not JSON and was skipped ({exc.msg})")
    person = [e for e in entries if e.get("who") == "person"]
    stamps = [s for s in (seconds(e.get("t")) for e in entries) if s is not None]
    if len(stamps) < len(entries):
        notes.append("some run log entries carry no readable `t`; wall_seconds spans the ones that do")
    corrections = [e for e in entries if e.get("type") == "correction"]
    return {
        "restarts": len(corrections),
        # The card's own change of mind is mandated by the protocol, and the 20 September run
        # counted it as a restart in one arm and not the other. Both numbers are printed now.
        "restarts_unmandated": sum(1 for e in corrections if not e.get("mandated")),
        "person_actions": len(person),
        "person_chars": sum(
            int(e["chars"]) if isinstance(e.get("chars"), int) else len(str(e.get("text") or ""))
            for e in person
        ),
        "executor_cost_usd": round(sum(float(e.get("cost_usd") or 0) for e in entries), 6),
        "executor_turns": sum(int(e.get("turns") or 0) for e in entries),
        "wall_seconds": round(max(stamps) - min(stamps), 1) if len(stamps) > 1 else 0.0,
        "results": sum(1 for e in entries if e.get("type") == "result"),
        "results_unpriced": sum(1 for e in entries if e.get("type") == "result" and not e.get("cost_usd")),
    }


def acceptance(accept: Path, repo: Path) -> dict:
    done = subprocess.run(
        [sys.executable, str(accept), str(repo)], capture_output=True, text=True, timeout=600
    )
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError:
        return {"passed": 0, "failed": 0, "details": [], "error": (done.stdout + done.stderr)[-800:]}


def intent_globs(path: Path) -> list[str]:
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repo")
    ap.add_argument("--base", required=True, help="the commit make_task.py printed")
    ap.add_argument("--intent", required=True, help="intent_globs.txt")
    ap.add_argument("--accept", required=True, help="accept.py")
    ap.add_argument("--quality", help="quality.py: the same checks on inputs the code never saw")
    ap.add_argument("--arm", required=True, choices=("prompt", "graphene"))
    ap.add_argument("--runlog", required=True, help="runlog.jsonl")
    args = ap.parse_args(argv[1:])

    repo = Path(args.repo).expanduser().resolve()
    intent = intent_globs(Path(args.intent))
    notes: list[str] = []

    final = changed_files(repo, args.base)
    outside_final = [p for p in final if not in_scope(p, intent)]
    rec = read_store(repo / ".graphene" / "graphene.db", repo, intent, notes)
    ever = sorted(set(rec["by_tool"]) | set(rec["by_shell"]) | set(outside_final))
    log = read_runlog(Path(args.runlog), notes)
    runs = runs_cost(repo / ".graphene" / "runs", notes)
    final_lines = final_diff_lines(repo, args.base)
    refusals = rec["refusals"]

    # Churn, once per file: the two records are two views of one filesystem, so adding them counts
    # the same change twice. The larger of the two is what that file can be shown to have suffered.
    churn = {
        path: max(rec["tool_churn"].get(path, 0), rec["shell_churn"].get(path, 0))
        for path in set(rec["tool_churn"]) | set(rec["shell_churn"])
    }
    naive = sum(rec["tool_churn"].values()) + sum(rec["shell_churn"].values())
    in_base = set(git(repo, "ls-tree", "-r", "--name-only", args.base).split("\n")) - {""}
    transient = sorted(p for p in churn if p not in in_base and not (repo / p).exists())
    transient_lines = sum(churn[p] for p in transient)
    rework_recorded = sum(churn.values())

    if args.arm == "prompt" and sum(refusals.values()):
        notes.append("the prompt arm recorded refusals: there was a plan in force, which it should not have")

    out = {
        "arm": args.arm,
        "repo": str(repo),
        "base": args.base,
        "intent": intent,
        "files_changed_final": final,
        "files_changed_final_n": len(final),
        "files_outside_intent_final": outside_final,
        "files_outside_intent_final_n": len(outside_final),
        "files_written_outside_intent_ever": ever,
        "files_written_outside_intent_ever_n": len(ever),
        "files_written_outside_intent_by_source": {
            "edit_events": rec["by_tool"],
            "shell": rec["by_shell"],
            "final_diff": outside_final,
        },
        "refused_writes": sum(refusals.values()),
        "refused_writes_by_kind": refusals,
        "restarts": log["restarts"],
        "restarts_unmandated": log["restarts_unmandated"],
        "rework_lines": max(0, rework_recorded - transient_lines - final_lines),
        "rework_recorded_lines": rework_recorded,
        "churn_naive_lines": naive,
        "churn_double_counted_lines": naive - rework_recorded,
        "churn_by_file": dict(sorted(churn.items())),
        "transient_files": transient,
        "transient_churn_lines": transient_lines,
        "rework_from_edit_events": sum(rec["tool_churn"].values()),
        "rework_from_shell": sum(rec["shell_churn"].values()),
        "final_diff_lines": final_lines,
        "recorded_write_events": rec["events"],
        "acceptance": acceptance(Path(args.accept), repo),
        "quality": acceptance(Path(args.quality), repo) if args.quality else None,
        "person_actions": log["person_actions"],
        "person_chars": log["person_chars"],
        "executor_cost_usd": round(log["executor_cost_usd"] + runs["cost_usd"], 6),
        "executor_cost_from_runlog_usd": log["executor_cost_usd"],
        "executor_cost_from_graphene_runs_usd": runs["cost_usd"],
        "executor_turns": log["executor_turns"] + runs["turns"],
        "executor_calls": log["results"] + runs["calls"],
        "executor_calls_unpriced": log["results_unpriced"] + runs["unpriced"],
        "wall_seconds": log["wall_seconds"],
        "notes": notes,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
