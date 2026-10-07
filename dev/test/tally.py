#!/usr/bin/env python3
"""One arm of one task, counted. Nothing here is estimated, judged or asked of a model.

    dev/test/tally.py <repo> --base <sha> --intent <intent_globs.txt> \\
        --accept <accept.py> [--quality <quality.py>] [--traps <traps.py>] \\
        --arm <prompt|graphene|tree|board> --runlog <runlog.jsonl>

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

Three measures were added for the statements task (October 2026), and each says where it comes from:

- **Traps**, 0 to 5, from the task's traps.py, run on the final state. A script counts them, never a
  judge.
- **Minutes to the first visible wrong inference**, from the first `prompt`. A wrong inference is a
  trap tripped or a board default the person overrode. It is seen at the earliest of: a node proposed
  with a scope that names a protected path (traps.NAMED); an agent's board item whose default the
  person overrode; the first commit since the base, on any branch or snapshot ref, whose tree trips
  a trap that the final state trips too. A trap that came and went on the way to a right answer is
  not one. Snapshots are the `snap` refs newrun.sh's env.sh writes. A trap seen only in the final
  state counts at the run log's last entry. A wrong inference said only in a node's words is not read.
- **Person minutes at the start and at the end**, clocked by the person's own `clock` entries in the
  run log: `start` to `away`, then every `back` to the next `away` or `done`. A `clock` is not an act.

The scope matcher is Graphene's own (``graphene_map.plan.in_scope``), so "outside intent" here
means exactly what "outside a node's scope" means to the hook that refuses a write.
"""

from __future__ import annotations

import argparse
import difflib
import importlib.util
import io
import json
import re
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from graphene_map.plan import in_scope  # noqa: E402

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


def forks_and_escalations(log: list[dict]) -> dict[str, int]:
    """Decision 75, counted from leaf logs (one leaf's, or a whole store's). A fork is a `fork` row
    that says it started (state `running`: each fork writes one as it starts and one as it ends; a leaf
    run with one conversation writes none, and has 0). An escalation is a `model` row that names the
    model before it (`from`): an attempt on another model than the attempt before."""

    def said(e: dict) -> dict:
        return e.get("detail") or {}

    return {
        "forks": sum(e["kind"] == "fork" and said(e).get("state") == "running" for e in log),
        "escalations": sum(e["kind"] == "model" and bool(said(e).get("from")) for e in log),
    }


def store_log(db: Path) -> list[dict]:
    """The store's `model` and `fork` rows, read only; none when there is no store."""
    if not db.exists():
        return []
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = conn.execute("SELECT kind, detail FROM node_log WHERE kind IN ('model', 'fork')").fetchall()
    conn.close()
    return [{"kind": kind, "detail": json.loads(detail) if detail else None} for kind, detail in rows]


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
    # a `read` is what the person was shown, not something they did or typed (attention.py counts
    # its words), and a `clock` is the person's watch; a `reopen` sends finished work back, which is
    # a restart however it is spelled
    person = [e for e in entries if e.get("who") == "person" and e.get("type") not in ("read", "clock")]
    stamps = [s for s in (seconds(e.get("t")) for e in entries) if s is not None]
    if len(stamps) < len(entries):
        notes.append("some run log entries carry no readable `t`; wall_seconds spans the ones that do")
    corrections = [e for e in entries if e.get("type") in ("correction", "reopen")]
    # `claude -p --resume` prints the session's running total as total_cost_usd, not the call's:
    # the modelUsage token counts in the same JSON grow by exactly each call's `usage` (checked on
    # 23 September, and in the 21 September runs' raw JSON). A session costs its largest total;
    # adding them up counted every earlier call again on each resume.
    session_cost: dict = {}
    for i, e in enumerate(x for x in entries if x.get("cost_usd") is not None):
        key = e.get("session_id") or i
        session_cost[key] = max(session_cost.get(key, 0.0), float(e.get("cost_usd") or 0))
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
        "executor_cost_usd": round(sum(session_cost.values()), 6),
        "executor_cost_summed_usd": round(sum(float(e.get("cost_usd") or 0) for e in entries), 6),
        "executor_turns": sum(int(e.get("turns") or 0) for e in entries),
        "wall_seconds": round(max(stamps) - min(stamps), 1) if len(stamps) > 1 else 0.0,
        "results": sum(1 for e in entries if e.get("type") == "result"),
        "results_unpriced": sum(1 for e in entries if e.get("type") == "result" and not e.get("cost_usd")),
        "started": next(
            (seconds(e.get("t")) for e in entries if e.get("who") == "person" and e.get("type") == "prompt"),
            min(stamps) if stamps else None,
        ),
        "ended": max(stamps) if stamps else None,
        **clocked(entries, notes),
    }


def clocked(entries: list[dict], notes: list[str]) -> dict:
    """Person minutes from the person's own clock entries. Each stretch at the keyboard runs from
    `start` or `back` to `away` or `done`. The first stretch is the start; the rest are the end."""
    stretches: list[float] = []
    since = None
    for e in entries:
        word, at = str(e.get("text") or "").strip(), seconds(e.get("t"))
        if e.get("type") != "clock" or at is None:
            continue
        if word in ("start", "back"):
            since = at
        elif word in ("away", "done") and since is not None:
            stretches.append((at - since) / 60)
            since = None
        else:
            notes.append(f"a clock entry `{word}` out of order was left out")
    if any(e.get("type") == "clock" for e in entries) and len(stretches) < 2:
        notes.append("the clock has no stretch after the person came back: the end minutes are unknown")
    return {
        "person_minutes_start": round(stretches[0], 1) if stretches else None,
        "person_minutes_end": round(sum(stretches[1:]), 1) if len(stretches) > 1 else None,
    }


def load_traps(path: Path):
    """A task's traps.py, as a module: `count(repo)` and `NAMED`."""
    spec = importlib.util.spec_from_file_location("task_traps", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def names(glob: str, named) -> bool:
    """Does the scope glob name a protected path outright? A path ending in / is a directory."""
    return any(glob.startswith(n) if n.endswith("/") else glob == n for n in named)


def tree_sightings(db: Path, named) -> list[tuple[float, str]]:
    """Wrong inferences the tree and the board showed: a node's scope as proposed (every edit rolled
    back) that names a protected path, at its proposal; an agent's board item with a default that the
    person overrode (picked, answered or dropped), at the time it was put up."""
    if not db.exists():
        return []
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = conn.execute("SELECT node_id, timestamp, kind, detail FROM node_log ORDER BY id").fetchall()
    data = {i: json.loads(d) for i, d in conn.execute("SELECT id, data FROM nodes")}
    meta = conn.execute("SELECT value FROM plan_meta WHERE key = 'board'").fetchone()
    conn.close()
    out = []
    proposed: dict[str, str] = {}
    for node, at, kind, _ in rows:
        if kind == "proposed":
            proposed.setdefault(node, at)
    for node, at in proposed.items():
        scope = (data.get(node) or {}).get("scope") or []
        for nid, _, kind, detail in reversed(rows):
            changed = (json.loads(detail or "{}").get("changed") or {}) if kind == "edited" else {}
            if nid == node and "scope" in changed:
                scope = changed["scope"][0] or []
        hit = [g for g in scope if names(g, named)]
        if hit and seconds(at) is not None:
            out.append((seconds(at), f"{node} was proposed with scope {hit[0]}"))
    for item in json.loads(meta[0]) if meta else []:
        default = item.get("default") or item.get("kind") in ("assume", "leave out")
        if item.get("agent") and default and item.get("state") in ("picked", "answered", "dropped"):
            out.append(
                (seconds(item.get("created_at")), f"board item {item['id']}: the person overrode its default")
            )
    return [s for s in out if s[0] is not None]


def diff_sighting(
    repo: Path, base: str, count, final: list[str], notes: list[str]
) -> tuple[float, str] | None:
    """The first commit since the base, on any ref (branches, merges, snapshots), whose tree trips a
    trap in `final`: its commit time. Each distinct tree is counted once, oldest first."""
    if not final:
        return None
    seen: set[str] = set()
    lines = git(repo, "log", "--all", "--format=%ct %T %H %s", f"^{base}").split("\n")
    for line in sorted(ln for ln in lines if ln):
        at, tree, sha, subject = (line.split(" ", 3) + [""])[:4]
        if tree in seen:
            continue
        seen.add(tree)
        tar = subprocess.run(["git", "-C", str(repo), "archive", sha], capture_output=True, check=True).stdout
        with tempfile.TemporaryDirectory(prefix="tally-at-") as where:
            with tarfile.open(fileobj=io.BytesIO(tar)) as archive:
                archive.extractall(where, filter="data")
            said = count(Path(where))
        hit = [trap for trap in said["tripped"] if trap in final]
        if hit:
            return float(
                at
            ), f"{'snapshot' if subject == 'snap' else 'commit'} {sha[:10]} trips {', '.join(hit)}"
    notes.append(f"{len(seen)} trees since the base were counted, and none showed a trap the end has")
    return None


def first_wrong(repo: Path, base: str, module, final: dict, log: dict, notes: list[str]) -> dict:
    """When a wrong inference first showed, in minutes from the first `prompt`, and how."""
    seen = tree_sightings(repo / ".graphene" / "graphene.db", getattr(module, "NAMED", ()))
    found = diff_sighting(repo, base, module.count, final["tripped"], notes)
    seen += [found] if found else []
    if not seen and final["traps"] and log["ended"] is not None:
        seen.append((log["ended"], f"only in the final state: {', '.join(final['tripped'])}"))
    if not seen or log["started"] is None:
        return {"first_wrong_minutes": None, "first_wrong_at": None, "first_wrong_how": None}
    at, how = min(seen)
    return {
        "first_wrong_minutes": round((at - log["started"]) / 60, 2),
        "first_wrong_at": datetime.fromtimestamp(at, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "first_wrong_how": how,
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
    ap.add_argument("--traps", help="traps.py: the task's traps, counted from the final state")
    ap.add_argument("--arm", required=True, choices=("prompt", "graphene", "tree", "board"))
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
    module = load_traps(Path(args.traps)) if args.traps else None
    trapped = module.count(repo) if module else None
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
        # what 20 and 21 September printed: every resumed call's running total added up
        "executor_cost_from_runlog_summed_usd": log["executor_cost_summed_usd"],
        "executor_cost_from_graphene_runs_usd": runs["cost_usd"],
        "executor_turns": log["executor_turns"] + runs["turns"],
        "executor_calls": log["results"] + runs["calls"],
        "executor_calls_unpriced": log["results_unpriced"] + runs["unpriced"],
        "wall_seconds": log["wall_seconds"],
        **forks_and_escalations(store_log(repo / ".graphene" / "graphene.db")),
        "traps": trapped["traps"] if trapped else None,
        "traps_tripped": trapped["tripped"] if trapped else None,
        **(first_wrong(repo, args.base, module, trapped, log, notes) if module else {}),
        "person_minutes_start": log["person_minutes_start"],
        "person_minutes_end": log["person_minutes_end"],
        "notes": notes,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
