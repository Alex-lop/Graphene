#!/usr/bin/env python3
"""The benchmark: one task, one configuration, one run, counted. Nothing is estimated.

    uv run python docs/test/bench.py <task> --config NAME --executor SPEC [--planner SPEC]
        [--parallel 4] [--run 1] [--rounds 3] [--timeout 3600] [--checks-only]
        [--tasks DIR] [--trees DIR] [--out DIR] [--rows FILE] [--ledger FILE]

In order:

1. builds the task's repo fresh with make_task.py, outside this repository (by default in
   ~/graphene-bench/<date>/<task>-<config>-<run>/repo), and runs `graphene init` there;
2. loads the task's fixed tree, <trees>/<task>.plan, as the person, all of it accepted;
3. runs every leaf's check at the base commit, in a scratch worktree: a check that passes before any
   work is done is not a check. Such a leaf is flagged and counted; fixing the tree is the person's;
4. `graphene run --parallel N --with <executor>`, then plays the person mechanically: a leaf that
   came back with offers has its widen (`w`) taken when every path it adds falls inside the task's
   intent_globs.txt, by Graphene's own scope matching, and any other offer refused. Each is a person
   action in <run>/runlog.jsonl. A refused leaf is not run again. Then it runs again, until nothing
   is left to run, at most --rounds times, and says so when the cap is hit;
5. counts, from git, the store, .graphene/runs/ and the run log, and appends a JSON row per leaf and
   one for the run to --rows. accept.py and quality.py are run as tally.py runs them.

`w` and not `b`: both offers add the same paths, and `b`'s sibling leaf, with its check `true`, would
land and be counted as a leaf of the tree. A widened leaf is the tree's own leaf, held to its own check.

The spend: every Token Factory call goes to one ledger for the night (GRAPHENE_LEDGER, set here). At
80% of GRAPHENE_SPEND_CAP_USD (30 if unset) no new run starts; at 100% a run stops between rounds
(the client already refuses a call at the cap). Either way the exit code is 3. A Nemotron
configuration that cannot reach Token Factory starts nothing (exit 2), rather than count a run whose
every leaf failed for want of a key.

This is the measuring instrument, and the only code here that reads docs/test/tasks/:
intent_globs.txt at run time, and accept.py and quality.py only by running them. Nothing it reads
there reaches an executor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import make_task  # noqa: E402
import tally  # noqa: E402  (it puts src/ on the path)

from graphene_map import plan as P  # noqa: E402
from graphene_map import tokenfactory as tf  # noqa: E402
from graphene_map.executor import PROMPT_VERSION  # noqa: E402
from graphene_map.run import STOPPED  # noqa: E402
from graphene_map.store import Store  # noqa: E402

ROWS = HERE / "runs-2026-09-25.jsonl"
LEDGER = HERE / "ledger-2026-09-25.jsonl"
CAP = 30.0
PERSON = P.Caller("bench", True, stand_in=True)  # GRAPHENE_AS=person:bench; the log says "(no terminal)"
# what an agent's shell carries (plan.caller reads them); the person carries none, even when the
# bench is started from inside an agent's session
MARKS = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT", "CODEX_SESSION_ID",
         "CODEX_SANDBOX", "AI_AGENT", "GRAPHENE_AS", *P.AGENT_MARKS)  # fmt: skip
CLI = "import sys; from graphene_map.cli import app; sys.argv[0] = 'graphene'; app()"
# what an executor's own `done` or `release` logs; the run's boundary after it ended logs as the run
VERDICTS = ("finished", "refused", "check_passed", "check_failed", "released")


def graphene(repo: Path, env: dict, *args: str) -> str:
    said = subprocess.run([sys.executable, "-c", CLI, *args], cwd=repo, env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True)  # fmt: skip
    if said.returncode:
        raise SystemExit(f"graphene {shlex.join(args)} failed: {(said.stdout + said.stderr).strip()[-600:]}")
    return said.stdout


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True).stdout.strip()


def graphene_sha() -> str:
    """The commit of the Graphene that ran, "-dirty" when its code (or this harness's) differs from it;
    the night's rows and ledger, which grow as it runs, are not code."""
    where = Path(P.__file__).parents[2]
    sha = git(where, "rev-parse", "HEAD")
    if not sha:
        return f"not a git checkout: {where}"
    return sha[:12] + ("-dirty" if git(where, "status", "--porcelain", "--", "src", "docs/test/*.py") else "")


def logger(runlog: Path):
    """A person action, in the run log's shape (logline.py's): the command as it was run."""

    def log(kind: str, text: str, **more) -> None:
        with runlog.open("a", encoding="utf-8") as f:
            entry = {"t": time.time(), "who": "person", "type": kind, "text": text, "chars": len(text)}
            f.write(json.dumps({**entry, **more}) + "\n")

    return log


def prepare(run_dir: Path, task: str, tree: Path, log) -> tuple[Path, str, dict]:
    """The repo, fresh, with graphene init run and the tree loaded as the person."""
    repo = run_dir / "repo"
    (run_dir / "tmp").mkdir(parents=True)
    base = make_task.build(task, repo)
    (run_dir / "base.sha").write_text(base + "\n")
    env = {k: v for k, v in os.environ.items() if k not in MARKS}
    env |= {"GRAPHENE_AS": f"person:{PERSON.name}", "TMPDIR": str(run_dir / "tmp")}
    graphene(repo, env, "init")
    graphene(repo, env, "plan", "propose", str(tree))
    graphene(repo, env, "plan", "accept")
    log("accept", f"graphene plan propose {shlex.quote(str(tree))} && graphene plan accept")
    return repo, base, env


def base_checks(repo: Path, base: str, where: Path) -> dict[str, bool]:
    """Each leaf's check, run as Graphene runs it, at the base commit: True when it already passes (a
    leaf with no check passes by definition)."""
    git(repo, "worktree", "add", "-q", "--detach", str(where), base)
    try:
        with Store.open(repo) as store:
            leaves = P.order(P.leaves(P.nodes(store)))
        return {n.id: P.run_check(n.check, where)[0] if n.check else True for n in leaves}
    finally:
        git(repo, "worktree", "remove", "--force", str(where))


def one_round(repo: Path, env: dict, argv: list[str], out: Path, timeout: float) -> str:
    """`graphene run`, its output kept; past the timeout it is stopped as a Ctrl-C stops it (every leaf
    handed back, every executor ended). Returns its last line."""
    with out.open("w", encoding="utf-8") as sink:
        proc = subprocess.Popen([sys.executable, "-c", CLI, *argv], cwd=repo, env=env,
                                stdin=subprocess.DEVNULL, stdout=sink, stderr=subprocess.STDOUT)  # fmt: skip
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.terminate()  # graphene takes SIGTERM as Ctrl-C
            try:
                proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    return lines[-1] if lines else f"(no output; exit {proc.returncode})"


def play(store, n: P.Node, intent: list[str]) -> tuple[list[str] | None, list[str], str]:
    """The person, mechanically: (the offer's command when it is taken, the paths it adds, what it said)."""
    offers = P.offers(store, n)
    paths = P.offerable(store, n)
    widen = next((o for o in offers if o[0] == "w"), None)
    if widen and all(P.in_scope(p, intent) for p in paths):
        return widen[2], paths, widen[1]
    return None, paths, "; ".join(o[1] for o in offers)


def last_words(log: str | None) -> str:
    """The last thing an attempt's executor printed (the Nemotron executor's bill line aside)."""
    try:
        lines = Path(log).read_text(encoding="utf-8", errors="replace").splitlines()  # type: ignore[arg-type]
    except (OSError, TypeError):
        return "no output"
    said = [ln for ln in lines if ln.strip() and not ln.startswith("bill:")]
    return " ".join(said[-1].split())[:200] if said else "no output"


def ended(hold: list[dict]) -> tuple[str, str]:
    """How one hold of a leaf ended, from the plan's log: landed, handed back or failed, and why. A
    failed attempt is one whose executor ended with no done and no release of its own (a crash, a
    timeout, a step cap, silence): the run's own boundary after it is logged as the run."""
    if any(e["kind"] == "landed" for e in hold):
        return "landed", ""
    back = [str(e["detail"].get("why", "")) for e in hold if e["kind"] == "released"]
    why = back[-1] if back else ""
    if why == STOPPED:
        return "failed", "timeout: the round ran past --timeout and the run was stopped"
    tries = [k for k, e in enumerate(hold) if e["kind"] == "attempt"]
    last = hold[tries[-1] :] if tries else hold
    if not any(e["kind"] in VERDICTS and e["actor"] != hold[0]["actor"] for e in last):
        said = last_words(last[0]["detail"].get("log")) if tries else "it never started"
        said += f"; {why}" if why else ""
        return "failed", f"its executor ended with no done and no release: {said}"
    if back:
        return "handed back", why
    return "unlanded", "it passed and its merge did not go in; it waits in review"


def leaf_rows(repo: Path, runlog: Path, at_base: dict[str, bool]) -> list[dict]:
    entries = [json.loads(ln) for ln in runlog.read_text(encoding="utf-8").splitlines() if ln.strip()]
    decided: dict[str, dict] = {}
    for e in entries:
        if e.get("node"):
            decided.setdefault(e["node"], e)  # the first hand-back's offer, the one the outcome is of
    rows = []
    with Store.open(repo) as store:
        everything = P.nodes(store)
        by_id = {n.id: n for n in everything}
        for n in P.order(P.leaves(everything)):
            log = store.node_log(n.id)
            starts = [k for k, e in enumerate(log) if e["kind"] == "started"]
            holds = [log[a:b] for a, b in zip(starts, [*starts[1:], len(log)], strict=True)]
            waits = ", ".join(m.id for m in P.unmet(n, by_id)) or "nothing"
            outcome, why = ended(holds[0]) if holds else ("not started", f"it waited on {waits}")
            finished = [e["detail"] for e in log if e["kind"] == "finished"]
            changed = finished[-1].get("changed") or [] if finished else []
            if outcome == "landed" and not all(P.in_scope(p, n.scope) for p in changed):
                outcome, why = "landed outside its scope", ", ".join(changed)
            d = decided.get(n.id)
            offer = None if d is None else ("w" if d["type"] == "widen" else "refused")
            then = None
            if offer == "w":
                then = ended(holds[-1])[0] if len(holds) > 1 else "not run again"
            usage = [e["detail"] for e in log if e["kind"] == "usage"]
            attempts = sum(e["kind"] == "attempt" for e in log)
            wall = 0.0
            for h in holds:
                own = [tally.seconds(e["timestamp"]) for e in h if e["actor"] != PERSON.label]
                wall += max(own) - min(own)
            rows.append({
                "kind": "leaf", "leaf": n.id, "title": n.title, "scope": n.scope, "state": n.state,
                "outcome": outcome, "why": why, "offer": offer,
                "offer_paths": d.get("paths", []) if d else [],
                "offer_outside_intent": d.get("outside_intent", []) if d else [],
                "then": then, "attempts": attempts, "holds": len(holds),
                "writes_refused": sum(e["kind"] == "denied" for e in log),
                "check_passes_at_base": at_base.get(n.id),
                "calls": sum(u.get("calls") or 0 for u in usage),
                "tokens_in": sum(u.get("prompt_tokens") or 0 for u in usage),
                "tokens_out": sum(u.get("completion_tokens") or 0 for u in usage),
                "dollars": round(sum(u.get("dollars") or 0 for u in usage), 6),
                "models": sorted({u["model"] for u in usage if u.get("model")}),
                "unpriced_attempts": max(0, attempts - len(usage)),
                "wall_seconds": round(wall, 1),
            })  # fmt: skip
    return rows


def parse(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("task")
    ap.add_argument("--config", required=True, help="the configuration's name, in the rows and the run's dir")
    ap.add_argument("--executor", required=True, help="as `graphene run --with` takes it: 'nemotron …'")
    ap.add_argument("--planner", default="nemotron",
                    help="what made the tree (recorded: the tree is fixed, so no planner runs here)")
    ap.add_argument("--parallel", type=int, default=4, help="N for `graphene run --parallel`, 2 or more")
    ap.add_argument("--run", type=int, default=1, help="the run number")
    ap.add_argument("--rounds", type=int, default=3, help="`graphene run`s at most, offers taken between")
    ap.add_argument("--timeout", type=float, default=3600, help="seconds a round may take; then it stops")
    ap.add_argument("--checks-only", action="store_true",
                    help="build, load the tree, run each leaf's check at the base commit, and stop")
    ap.add_argument("--tasks", type=Path, default=HERE / "tasks", help="where <task>/intent_globs.txt is")
    ap.add_argument("--trees", type=Path, default=HERE / "trees", help="where <task>.plan is")
    ap.add_argument("--out", type=Path, default=Path.home() / "graphene-bench" / time.strftime("%Y-%m-%d"))
    ap.add_argument("--rows", type=Path, default=ROWS)
    ap.add_argument("--ledger", type=Path, default=LEDGER, help="the night's Token Factory ledger")
    return ap.parse_args(argv)  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    card = (args.tasks / args.task).resolve()
    tree = (args.trees / f"{args.task}.plan").resolve()  # read by graphene, which runs in the repo
    for need in (card / "intent_globs.txt", card / "accept.py", tree):
        if not need.is_file():
            print(f"no {need}" + ("; docs/test/trees/README.md says how one is made" if need == tree else ""))
            return 2
    if args.parallel < 2:
        print("--parallel 1 works in place and merges nothing, so no leaf could land: use 2 or more")
        return 2
    if args.checks_only:
        with tempfile.TemporaryDirectory() as tmp:
            repo, base, _ = prepare(Path(tmp), args.task, tree, logger(Path(tmp) / "runlog.jsonl"))
            at_base = base_checks(repo, base, Path(tmp) / "base-check")
        for leaf, passes in at_base.items():
            print(f"{leaf:32} {'PASSES at the base commit: not a check' if passes else 'fails at base'}")
        return 1 if any(at_base.values()) else 0

    unreached = tf.reach() if args.executor.split()[:1] == ["nemotron"] else None
    if unreached:  # else every leaf would fail, and the rows would count a run that never was
        print(f"no run: {unreached}")
        return 2
    cap = float(os.environ.get("GRAPHENE_SPEND_CAP_USD") or CAP)
    os.environ["GRAPHENE_LEDGER"] = str(args.ledger.resolve())
    os.environ["GRAPHENE_SPEND_CAP_USD"] = str(cap)  # set, so the client refuses a call at the cap
    if tf.spent() >= 0.8 * cap:
        print(f"no new run: the ledger ({args.ledger}) is at ${tf.spent():.2f} of ${cap:.2f}, 80% or more")
        return 3
    run_dir = (args.out / f"{args.task}-{args.config}-{args.run}").resolve()
    if run_dir.is_relative_to(ROOT):
        print(f"{run_dir} is inside this repository; a task repo is built outside it (--out)")
        return 2
    if run_dir.exists():
        print(f"{run_dir} exists already; a run is never redone in place")
        return 2
    runlog = run_dir / "runlog.jsonl"
    log = logger(runlog)
    repo, base, env = prepare(run_dir, args.task, tree, log)
    print(f"repo  {repo}  (base {base[:12]})")
    at_base = base_checks(repo, base, run_dir / "base-check")
    flagged = [leaf for leaf, passes in at_base.items() if passes]
    if flagged:
        print(f"checks passing at the base commit, which are not checks: {', '.join(flagged)} (fix the tree)")
    intent = tally.intent_globs(card / "intent_globs.txt")

    only: list[str] = []
    stopped, cap_hit, rounds, began = None, False, 0, time.monotonic()
    while True:
        rounds += 1
        with Store.open(repo) as store:
            since = len(store.node_log())
        argv = ["run", "--parallel", str(args.parallel), "--with", args.executor]
        argv += [x for i in only for x in ("--node", i)]
        log("run", "graphene " + shlex.join(argv))
        print(f"round {rounds}: {one_round(repo, env, argv, run_dir / f'round-{rounds}.txt', args.timeout)}")
        decisions = []
        with Store.open(repo) as store:
            ran = {e["node_id"] for e in store.node_log()[since:] if e["kind"] == "started"}
            for n in P.nodes(store):
                if n.id in ran and P.came_back(store, n) and P.offers(store, n):
                    decisions.append((n.id, *play(store, n, intent)))
        for node, command, paths, said in decisions:
            if command:
                graphene(repo, env, *command)
                log("widen", "graphene " + shlex.join(command), node=node, paths=paths)
            else:
                outside = [p for p in paths if not P.in_scope(p, intent)]
                log("refuse", f"not taken: {said}", node=node, paths=paths, outside_intent=outside)
            print(f"  {node} came back: {said}: {'taken' if command else 'refused'}")
        with Store.open(repo) as store:
            everything = P.nodes(store)
            left = [n for n in P.leaves(everything) if n.state == P.OPEN and not P.came_back(store, n)]
            only = [n.id for n in left]
            ready = [n.id for n in P.ready(everything, P.Caller("agent", False)) if n.id in only]
        if not ran or not ready:
            break
        if tf.spent() >= cap:
            stopped = "the spend cap"
            print(f"stopped: the ledger is at ${tf.spent():.2f} of ${cap:.2f}; {', '.join(ready)} not run")
            break
        if rounds == args.rounds:
            cap_hit = True
            print(f"the cap of {args.rounds} rounds is hit: {', '.join(ready)} not run again")
            break
    wall = time.monotonic() - began

    meta = {
        "task": args.task, "config": args.config, "run": args.run, "planner": args.planner,
        "executor": args.executor, "parallel": args.parallel, "graphene_sha": graphene_sha(),
        "prompt_version": PROMPT_VERSION if args.executor.split()[:1] == ["nemotron"] else None,
        "tree": hashlib.sha256(tree.read_bytes()).hexdigest()[:12],
    }  # fmt: skip
    leaves = [{**meta, **row} for row in leaf_rows(repo, runlog, at_base)]
    kinds = ("landed", "handed back", "failed", "not started")
    count = {k: sum(r["outcome"] == k for r in leaves) for k in kinds}
    dollars = round(sum(r["dollars"] for r in leaves), 6)
    quality = card / "quality.py"
    outside = [p for p in tally.changed_files(repo, base) if not P.in_scope(p, intent)]
    run = {
        **meta, "kind": "run", "leaves": len(leaves), "landed": count["landed"],
        "handed_back": count["handed back"], "failed": count["failed"], "not_started": count["not started"],
        "other": len(leaves) - sum(count.values()),
        "landed_after_offer": sum(r["then"] == "landed" for r in leaves),
        "offers_taken": sum(r["offer"] == "w" for r in leaves),
        "offers_refused": sum(r["offer"] == "refused" for r in leaves),
        "checks_passing_at_base": flagged,
        "accept": tally.acceptance(card / "accept.py", repo),
        "quality": tally.acceptance(quality, repo) if quality.is_file() else None,
        "dollars": dollars, "tokens_in": sum(r["tokens_in"] for r in leaves),
        "tokens_out": sum(r["tokens_out"] for r in leaves),
        "cost_per_landed_usd": round(dollars / count["landed"], 6) if count["landed"] else None,
        "rounds": rounds, "rounds_cap_hit": cap_hit, "stopped": stopped, "wall_seconds": round(wall, 1),
        "files_outside_intent_final": outside,
        "person_actions": tally.read_runlog(runlog, [])["person_actions"],
        "repo": str(repo), "base": base, "runlog": str(runlog), "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }  # fmt: skip
    args.rows.parent.mkdir(parents=True, exist_ok=True)
    with args.rows.open("a", encoding="utf-8") as f:
        for row in [*leaves, run]:
            f.write(json.dumps(row) + "\n")
    for r in leaves:
        more = f", offer {r['offer']}" + (f", then {r['then']}" if r["then"] else "") if r["offer"] else ""
        print(f"  {r['leaf']:28} {r['outcome']}{more}  {r['attempts']} attempts  ${r['dollars']:.4f}")
    acc = run["accept"]
    print(f"{run['landed']} of {len(leaves)} landed, {run['handed_back']} handed back "
          f"({run['landed_after_offer']} then landed), {run['failed']} failed; accept "
          f"{acc.get('passed')}/{(acc.get('passed') or 0) + (acc.get('failed') or 0)}; "
          f"${dollars:.4f} at list price; rows in {args.rows}")  # fmt: skip
    return 3 if stopped else 0


if __name__ == "__main__":
    raise SystemExit(main())
