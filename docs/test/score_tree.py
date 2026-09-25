#!/usr/bin/env python3
"""A tree, scored against its task before anything runs on it. Nothing is estimated or asked of a model.

    uv run python docs/test/score_tree.py <task> [--plan FILE] [--tasks DIR] [--after REPO]
        [--store REPO | --planner-prompt N --planner-model ID] [--scores FILE]

The plan is its text, as `graphene plan --text` prints it (by default docs/test/trees/<task>.plan).
Its leaves are scored with Graphene's own code:

- **coverage**: every glob of the task's intent_globs.txt that no leaf's scope reaches. A glob is
  reached when a path it names (a file of the task's repo, or a path a scope or the intent spells out)
  is inside the intent and inside some leaf's scope (`plan.in_scope`); a glob that names no such path
  is reached when a scope's globs may meet it (`run.may_collide`);
- **overreach**: per leaf, the repo's files and the new paths its scope spells out that no intent glob
  covers; and, apart, the scope globs that name nothing in the repo (new files, or a wrong guess);
- **overlap**: pairs of leaves whose scopes share a path (`plan.overlap`) or whose globs may meet
  (`run.may_collide`, which is what makes `graphene run --parallel` hold one of them back);
- **checks**: every leaf's check, run with `plan.run_check` at the base commit of a repo built fresh
  with make_task.py (a check that passes there is not a check), and with --after in a finished run's
  repo (one bench.py left), where each should pass. A leaf with no check passes, as bench.py counts it.

With --store (the repo where the planner made the tree), the planner's model and prompt version come
from the plan's log (its `usage` rows); else from the flags. The report is printed, and one JSON row
per call is appended to --scores, with the tree's hash as bench.py's rows carry it.

This is a measuring instrument: of docs/test/tasks/ it reads intent_globs.txt and nothing else.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_task  # noqa: E402
import tally  # noqa: E402  (it puts src/ on the path)

from graphene_map import plan as P  # noqa: E402
from graphene_map import plan_text  # noqa: E402
from graphene_map.run import may_collide  # noqa: E402
from graphene_map.store import Store  # noqa: E402

SCORES = HERE / "trees" / "scores.jsonl"


def leaves(text: str) -> dict[str, plan_text.Line]:
    """The text's leaves by id (or title): its node lines with no line under them, by indentation or
    by `parent:`."""
    lines = plan_text.parse(text)[1]
    ups = {ln.under for ln in lines if ln.under}
    over = {ln.parent for ln in lines} | {k for k, ln in enumerate(lines) if ln.id and ln.id in ups}
    return {ln.id or ln.title: ln for k, ln in enumerate(lines) if k not in over}


def spelled(globs: list[str]) -> list[str]:
    """The paths globs spell out: those with no wildcard, not taken out."""
    plain = [g for g in globs if g[:1] != "!" and not any(c in g for c in "*?")]
    return [g.strip().removeprefix("./").rstrip("/") for g in plain]


def planner_of(store_repo: Path | None, prompt: int | None, model: str | None) -> dict:
    """The planner's prompt versions and models: from the plan's log when a store is given."""
    if store_repo is None:
        return {"prompt": [] if prompt is None else [prompt], "model": [model] if model else []}
    if not (store_repo / ".graphene" / "graphene.db").is_file():
        raise SystemExit(f"no plan's log in {store_repo} (.graphene/graphene.db)")
    with Store.open(store_repo) as store:
        bills = [e["detail"] for e in store.node_log("*", ("usage",)) if e["actor"] == "planner:nemotron"]
    return {k: sorted({b[k] for b in bills if b.get(k) is not None}, key=str) for k in ("prompt", "model")}


def score(text: str, intent: list[str], build: Callable[[Path], str], after: Path | None = None) -> dict:
    """The tree's scores; `build` makes the task's repo in an empty directory and returns its base."""
    tree = leaves(text)
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        build(repo)
        listed = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"], capture_output=True, text=True,
                                check=True)  # fmt: skip
        files = [f for f in listed.stdout.split("\0") if f]
        at_base = [k for k, ln in tree.items() if not ln.check or P.run_check(ln.check, repo)[0]]
    fail_after = None
    if after is not None:
        fail_after = [k for k, ln in tree.items() if not (ln.check and P.run_check(ln.check, after)[0])]

    def names(glob: str, among) -> list[str]:
        return [p for p in among if P.in_scope(p, [glob])]

    new = {k: [p for p in spelled(ln.scope) if not names(p, files)] for k, ln in tree.items()}
    paths = {*files, *spelled(intent), *(p for ps in new.values() for p in ps)}
    unreached = []
    for g in (g for g in intent if g[:1] != "!"):
        named = [p for p in names(g, paths) if P.in_scope(p, intent)]
        if named:
            reached = any(P.in_scope(p, ln.scope) for p in named for ln in tree.values())
        else:  # it names nothing yet: whether the globs themselves may meet
            reached = any(may_collide([g], ln.scope) for ln in tree.values())
        unreached += [] if reached else [g]
    past = {k: [p for p in sorted({*files, *new[k]}) if P.in_scope(p, ln.scope) and not P.in_scope(p, intent)]
            for k, ln in tree.items()}  # fmt: skip
    empty = {k: [g for g in ln.scope if g[:1] != "!" and not names(g, files)] for k, ln in tree.items()}
    overlaps = []
    for a, b in itertools.combinations(tree, 2):
        shared = P.overlap(tree[a].scope, tree[b].scope, files)
        if shared or may_collide(tree[a].scope, tree[b].scope):
            overlaps.append([a, b, shared])
    overreach = {k: v for k, v in past.items() if v}
    return {
        "leaves": len(tree), "unreached": unreached, "overreach": overreach,
        "names_nothing": {k: v for k, v in empty.items() if v}, "overlaps": overlaps, "pass_at_base": at_base,
        "after": str(after) if after else None, "fail_after": fail_after,
        "counts": {"unreached": len(unreached), "overreaching_leaves": len(overreach),
                   "overlapping_pairs": len(overlaps), "checks_passing_at_base": len(at_base),
                   "checks_failing_after": None if fail_after is None else len(fail_after)},
    }  # fmt: skip


def report(row: dict) -> str:
    def said(label: str, items: list[str]) -> str:
        return f"  {label} ({len(items)}): {'; '.join(items) or 'none'}"

    def each(d: dict) -> list[str]:
        return [f"{k}: {', '.join(v)}" for k, v in d.items()]

    who = row["planner"]
    planner = ", ".join([*who["model"], *(f"prompt {v}" for v in who["prompt"])])
    pairs = [f"{a} & {b}: {', '.join(p) or 'their globs may meet'}" for a, b, p in row["overlaps"]]
    lines = [
        f"{row['task']}  tree {row['tree']}  {row['leaves']} leaves  planner: {planner or 'not given'}",
        said("intent globs no scope reaches", row["unreached"]),
        said("leaves reaching past the intent", each(row["overreach"])),
        said("scope globs naming nothing in the repo", each(row["names_nothing"])),
        said("pairs of leaves sharing a path", pairs),
        said("checks passing at base, which are not checks", row["pass_at_base"]),
    ]
    if row["fail_after"] is not None:
        lines.append(said(f"checks failing after, in {row['after']}", row["fail_after"]))
    return "\n".join(lines)


def main(argv: list[str] | None = None, build: Callable[[Path], str] | None = None) -> int:
    """`build` stands in for make_task.py's builder (a test's own task)."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("task")
    ap.add_argument("--plan", type=Path, help="the plan's text (default: docs/test/trees/<task>.plan)")
    ap.add_argument("--tasks", type=Path, default=HERE / "tasks", help="where <task>/intent_globs.txt is")
    ap.add_argument("--after", type=Path, help="a finished run's repo: every check should pass there")
    ap.add_argument("--store", type=Path, help="the repo whose plan's log holds the planner's calls")
    ap.add_argument("--planner-prompt", type=int, help="the planner's prompt version, without --store")
    ap.add_argument("--planner-model", help="the planner's model id, without --store")
    ap.add_argument("--scores", type=Path, default=SCORES)
    args = ap.parse_args(argv)
    plan = args.plan or HERE / "trees" / f"{args.task}.plan"
    globs = args.tasks / args.task / "intent_globs.txt"
    for need in (plan, globs):
        if not need.is_file():
            print(f"no {need}")
            return 2
    planner = planner_of(args.store, args.planner_prompt, args.planner_model)
    try:
        scored = score(plan.read_text(encoding="utf-8"), tally.intent_globs(globs),
                       build or (lambda d: make_task.build(args.task, d)),
                       args.after.resolve() if args.after else None)  # fmt: skip
    except P.Refused as no:
        print(f"{plan} is not a plan's text: {no}")
        return 2
    row = {"task": args.task, "tree": hashlib.sha256(plan.read_bytes()).hexdigest()[:12], "planner": planner,
           **scored, "plan": str(plan), "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}  # fmt: skip
    args.scores.parent.mkdir(parents=True, exist_ok=True)
    with args.scores.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    print(report(row))
    print(f"row appended to {args.scores}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
