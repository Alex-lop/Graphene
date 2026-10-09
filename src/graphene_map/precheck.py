"""Red first, in core and with no model: every accepted leaf's check run once at the base commit.

A check tells a leaf is done only if it fails now and passes after the work. `run` runs each distinct
check of the open leaves once, in a clean worktree as `node done` runs it, and writes a `precheck` row
a leaf: "passes" (it proves nothing), "outside" (it fails on a path no scope of the leaf covers), or
"red", the red a check should have. A proposed leaf's check was written by a planner and is never run
here (the Nemotron extra runs it in a sandbox fork). Output and why are hidden by demo.hider (the key,
anything shaped like a key, the repository's path) and a URL's user and password.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import plan as P

WORKERS = 4
# an escape sequence (CSI, OSC) or any other control character: what a check wrote must not move the
# person's cursor, clear a line or draw a verdict of its own over the real one
_CONTROL = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?|[\x00-\x1f\x7f-\x9f]")
_USER = re.compile(r"(//)[^/@\s]+@")  # a URL's user and password (a proxy's): never stored or said


class Rows(list):
    """The (node, detail) rows of a run, and the wall time it took."""

    seconds = 0.0


def state(root: Path) -> tuple[str | None, str | None]:
    """(HEAD, the checkout as git sees it now as one tree id): what a check runs on (tracked files as
    they are on disk, and new files git does not ignore, as `_clean_tree` takes them), so a commit or
    an uncommitted change makes a verdict stale. The tree is written from a copy of the index, so the
    checkout's own index is never touched."""
    import shutil  # here: only a precheck needs them
    import tempfile
    from contextlib import suppress

    base = P.head(root)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp, "index")
            with suppress(OSError):  # a repo where nothing was ever added has no index yet
                shutil.copyfile(Path(root, P._git(root, "rev-parse", "--git-path", "index").strip()), index)
            env = {**os.environ, "GIT_INDEX_FILE": str(index), "GIT_OPTIONAL_LOCKS": "0"}
            for args in (["add", "-A"], ["write-tree"]):
                done = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *args],
                                      env=env, capture_output=True, text=True, timeout=30)  # fmt: skip
            return base, (done.stdout.strip() if done.returncode == 0 else None)
    except (P.Refused, OSError, subprocess.TimeoutExpired):
        return base, None


def current(store, node: P.Node, base: str | None, tree: str | None) -> dict | None:
    """The leaf's last verdict, while it is about this rev, this check, this commit and this state of
    the checkout (``state``), and finished."""
    rows = [r["detail"] for r in store.node_log(node.id, ("precheck",))]
    last = rows[-1] if rows else None
    now = (node.rev, node.check, base, tree)
    fresh = last and tree and (last["rev"], last["check"], last["base"], last.get("tree")) == now
    unfinished = last and (last["verdict"] == "not-run" or last["why"].startswith("not read"))
    return last if fresh and not unfinished else None  # a check not run, or a red not read: try again


def _here(command: str, root: Path) -> tuple[int | None, str]:
    """An accepted check, run as `node done` runs it: in a clean worktree, without the key."""
    began = time.monotonic()
    env = P.check_env()
    try:
        with P._clean_tree(root, (), began) as tree:
            code, out, err = P._ended(command, tree, env, began)
    except subprocess.TimeoutExpired:
        return None, f"timed out after {P.CHECK_TIMEOUT:g} s"
    except (P.Refused, OSError) as no:
        return None, f"could not be run: {no}"
    return code, out + err


def _hider(root: Path):
    """demo.py's hider (the key in the environment, anything shaped like a key, the repository's path)
    and a URL's user and password: for every verdict stored or said, and what a model is sent."""
    from .demo import hider  # here: it brings the screen's imports, which only a run that reads needs

    hide = hider(root)[0]
    return lambda text: hide(_USER.sub(r"\1", str(text)))


def _plain(text) -> str:
    """One line, with no escape sequence or control character in it."""
    return " ".join(_CONTROL.sub(" ", str(text)).split())


def _gist(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return lines[-1][:200] if lines else "no output"


def _outside(node: P.Node, text: str, files: list[str], live: list[P.Node]) -> list[str]:
    """The paths a red check fails on that no scope of the leaf covers: those the output's lines name
    (a failing test's file), and those the command names when it names nothing of the leaf's own (a
    whole suite, another leaf's file). A command that runs a file of its own (its new test, not there
    yet) is red for its own reason, unless the output says otherwise. A path is one ``check_paths``
    reads: a tracked file, a tracked directory, or a path a live leaf's scope covers. A directory that
    holds a glob of the leaf's own scope is the leaf's own."""
    mine = [g for g in node.scope if not g.startswith("!")]

    def own(path: str) -> bool:
        return P.in_scope(path, node.scope) or any(g.startswith(path.rstrip("/") + "/") for g in mine)

    named = [path for path, _ in P.check_paths(node.check, files, live)]
    found = [] if any(own(p) for p in named) else [p for p in named if not own(p)]
    there = set(files)
    for line in text[-P.TAIL :].splitlines():
        read = [path for path, _ in P.check_paths("x " + line, files, live)]  # "x": the first word counts
        read += _tails(line, there)
        for path in read:
            if not own(path) and path not in found:
                found.append(path)
    return found


def _tails(line: str, there: set[str]) -> list[str]:
    """A tracked file named by its absolute path (a traceback's `File "/…/tree/tests/test_x.py"`), as
    its longest tail that is one: a check runs in a clean worktree, whose path is nobody's."""
    out = []
    for word in re.findall(r"[\w./-]+", line):
        parts = word.split("/")
        if len(parts) < 2 or word in there:
            continue
        tail = next(("/".join(parts[k:]) for k in range(1, len(parts)) if "/".join(parts[k:]) in there), None)
        if tail and tail not in out:
            out.append(tail)
    return out


def judge(node: P.Node, code: int | None, text: str, files: list[str],
          live: list[P.Node]) -> tuple[str, str, list[str]]:  # fmt: skip
    """(verdict, why, paths) of a check that was run: passes, outside or red."""
    if code == 0:
        return "passes", "it exits 0 before any work is done", []
    if code is None:  # it timed out or could not be run: no verdict, and it is tried again next time
        return "not-run", _gist(text), []
    paths = _outside(node, text, files, live)
    if paths:
        return "outside", f"it fails and names {', '.join(paths)}, which no scope of the leaf covers", paths
    return "red", _gist(text), []


def run(store, root: Path, ids=(), again: bool = False, say=None) -> Rows:
    """The check of every open leaf (or of ``ids``) at the checkout as it stands, each distinct command
    once, up to four at a time, each verdict a row. A leaf whose verdict is current is not run again;
    a proposed leaf's check is never run here. ``say`` is called with a line as a check starts."""
    everything = [n for n in P.nodes(store) if n.state not in P.GONE]
    todo = [P.get(store, i) for i in dict.fromkeys(ids)] or [n for n in everything if n.state == P.OPEN]
    for n in todo:
        if n.state not in (P.PROPOSED, P.OPEN):
            raise P.Refused(f"{n.id} is {n.state}: a check is run first only before its work starts")
    began, (base, tree), out = time.monotonic(), state(root), Rows()
    under = P.kids(everything, drawn=True)  # a sub-goal's check runs once its leaves are done, not here
    todo = [n for n in todo if n.check and n.state == P.OPEN and not under.get(n.id)]
    kept = {} if again else {n.id: current(store, n, base, tree) for n in todo}
    commands = list(dict.fromkeys(n.check for n in todo if not kept.get(n.id)))

    def one(command: str) -> tuple[int | None, str]:
        if say:
            say(f"running {command}")
        try:
            return _here(command, root)
        except Exception as no:  # one check that breaks its runner is its own line
            return None, f"could not be run: {' '.join(str(no).split())[:200]}"

    # a Ctrl-C, a closed terminal or a `kill` while the checks run ends them with everything they started
    # (`end_checks`), as `node done`'s check is ended: nothing a run begins outlives it. The pool is shut
    # after the kill, not before: shut first, it waited for a check that was never told to stop
    pool = ThreadPoolExecutor(WORKERS)
    try:
        with P.ctrl_c_on_hangup():
            futures = {c: pool.submit(one, c) for c in commands}
            ran = {c: f.result() for c, f in futures.items()}
    except BaseException:
        P.end_checks()
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    pool.shutdown(wait=True)
    hide = _hider(root) if ran else str
    files, live = sorted(P.tracked(root)), P._live(everything)
    for node in todo:
        if kept.get(node.id):
            out.append((node, {**kept[node.id], "kept": True}))  # never logged again
            continue
        code, text = ran[node.check]
        found, why, paths = judge(node, code, hide(text), files, live)  # hidden whole, before any cut
        detail = {"rev": node.rev, "check": node.check, "base": base, "tree": tree, "verdict": found,
                  "why": _plain(hide(why)), "paths": [_plain(hide(p)) for p in paths], "exit": code,
                  "where": "here", "by": None}  # fmt: skip
        store.log_node(node.id, P._now(), "precheck", "graphene:precheck", None, None, detail)
        out.append((node, detail))
    out.seconds = time.monotonic() - began
    return out


def said(rows) -> list[str]:
    """The lines a run prints: none for a red, a line each for a check that passes or names a path outside
    its scope, then the header."""
    base = next((d["base"] for _, d in rows if d.get("base")), None)
    if not base:
        return []
    at, lines = base[:7], []
    for node, d in rows:
        if d["verdict"] == "passes":
            lines.append(f"{node.id}: its check passes at the base commit {at}: it proves nothing; "
                         f"`graphene node set {node.id} --check '…'` or e in watch")  # fmt: skip
        elif d["verdict"] == "outside":
            lines.append(f"{node.id}: its check names {', '.join(d['paths'])}, outside its scope, at {at}")
    seconds = getattr(rows, "seconds", 0.0)
    return [*lines, f"red first: {len(rows)} check{'s' * (len(rows) != 1)} at {at} in {seconds:.0f} s"]
