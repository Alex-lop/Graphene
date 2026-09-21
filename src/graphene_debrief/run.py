"""`graphene run`: Graphene takes each ready node, hands it to an executor, and decides itself whether
it is done.

The executor is a command the person chooses (`claude -p …`, `codex exec …`, anything that takes a
prompt as its last argument). It is given one node's contract and nothing else. When its process
ends, however it ended, Graphene runs the same boundary as `graphene node done`: git says what
changed, the check says whether it works. Refused, the executor is sent back with the refusal; out
of attempts, the node is handed back with the reason and the run moves on. Nothing here trusts an
exit code or a closing message, and no vendor's ceiling on refused stops applies: the loop is ours.

Alone (`graphene run`), one leaf at a time in the checkout the command was started in, and nothing
is committed: the work is left in the tree for the person. In parallel (`graphene run --parallel N`),
each leaf gets its own worktree on its own branch under .graphene/worktrees/, so executors never see
each other's half-written files; a leaf that passes its boundary is committed there, by Graphene, and
merged into the checkout the run was started from when the merge is clean. Leaves whose scopes overlap
are never in flight together, so two leaves cannot have written one file: what is left that can make
a merge unclean is the person's own work in the way, and that leaf waits for them, on its branch.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import uuid
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path

from . import plan as P

DEFAULT_WITH = "claude -p --permission-mode acceptEdits"
ATTEMPTS = 3
WORKTREES = "worktrees"  # under .graphene/, which git ignores: the run's own, one a leaf


def prompt_for(node: P.Node, notes: list[str], refusal: str | None, why: list[str] | None = None) -> str:
    lines = [
        "You are doing one leaf of a plan that a person and their agents share. `why` is the path from "
        "the plan's goal down to your leaf, in the person's words: it is what your work is for. The "
        "leaf is the whole of what you are asked to do; the rest of the plan is not yours.",
        "",
        P.contract(node, why),
        *(f"  sent back with: {note}" for note in notes),
        "",
        "Do the work inside the scope. Read anything you need; write only inside the scope. When you "
        f"believe it is done run `graphene node done {node.id}`: it runs the check and asks git what "
        "changed, and tells you what is wrong if it refuses. If it cannot be done as written, run the "
        "`release` command above and say why. Do not start any other node.",
    ]
    if refusal:
        lines += ["", "Your last attempt was not accepted:", refusal]
    return "\n".join(lines)


def command_for(template: str, prompt: str, session: str, again: bool) -> list[str]:
    """The executor's argv. Claude Code is told which session this is, so its hooks hold it to the
    node from its first call and a second attempt resumes with what the first one learned; any other
    executor gets the prompt (refusal included) as its last argument, fresh each time."""
    argv = shlex.split(template)
    if argv and Path(argv[0]).name == "claude":
        argv += ["--resume", session] if again else ["--session-id", session]
    return [*argv, prompt]


def run_node(
    store,
    node_id: str,
    checkout: Path,
    template: str,
    attempts: int,
    say: Callable[[str], None],
    logs: Path | None,
) -> P.Node | None:
    """One leaf, start to boundary, in ``checkout``. Returns it when it ended done (or in review);
    None when it could not start, was handed back, or ran out of attempts."""
    session = str(uuid.uuid4())
    who = P.Caller(f"run:{shlex.split(template)[0]}", False, session)
    try:
        node = P.start(store, node_id, who, checkout)
    except P.Refused as no:
        say(str(no) if "cannot start" in str(no) else f"{node_id} cannot start: {no}")
        return None
    say(f"{node.id} started (revision {node.rev}): {node.title}")
    refusal: str | None = None
    for attempt in range(1, attempts + 1):
        argv = command_for(
            template,
            prompt_for(node, P.notes(store, node.id), refusal, P.trail(store, node)),
            session,
            attempt > 1,
        )
        env = {**os.environ, "GRAPHENE_NODE": node.id}
        env.pop("GRAPHENE_AS", None)  # whoever started the run, the executor speaks for nobody
        try:
            done = subprocess.run(
                argv, cwd=checkout, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL
            )
        except OSError as no:  # the executor is not installed, or not executable: nothing ran
            P.release(store, node.id, who, f"the executor could not be started: {argv[0]}: {no.strerror}")
            raise P.Refused(
                f"cannot run `{argv[0]}`: {no.strerror}. {node.id} was handed back untouched; name "
                "another executor with --with"
            ) from None
        if logs is not None:
            logs.mkdir(parents=True, exist_ok=True)
            (logs / f"{node.id}-{attempt}.txt").write_text(done.stdout + done.stderr, encoding="utf-8")
        say(f"{node.id} attempt {attempt}: the executor ended (exit {done.returncode})")
        current = P.get(store, node.id)
        if current.state in (P.DONE, P.REVIEW):  # it ran `done` itself, and the boundary agreed
            return current
        if current.state != P.RUNNING:  # it handed the node back, and said why
            why = (store.node_log(node.id, ("released",)) or [{"detail": {}}])[-1]["detail"].get("why", "")
            say(f"{node.id} handed back by the executor: {why}")
            return None
        try:
            return P.finish(store, node.id, who)
        except P.Refused as no:
            refusal = str(no)
            say(f"{node.id} attempt {attempt} refused: {refusal.splitlines()[0]}")
    P.release(store, node.id, who, f"{attempts} attempts, the last one refused: {refusal}")
    say(f"{node.id} handed back after {attempts} attempts")
    return None


def _said_done(node: P.Node, say: Callable[[str], None]) -> None:
    say(f"{node.id} is {'done' if node.state == P.DONE else 'finished; it waits for a sign-off'}")


def run_plan(
    store,
    checkout: Path,
    template: str = DEFAULT_WITH,
    attempts: int = ATTEMPTS,
    only: list[str] | None = None,
    say: Callable[[str], None] = print,
    logs: Path | None = None,
) -> list[P.Node]:
    """Run every leaf an agent can reach, in order. Returns the ones that ended done (or in review)."""
    finished: list[P.Node] = []
    tried: set[str] = set()
    # The nodes that exist when the run starts are the run: a plan that grows while it is going (a
    # proposal accepted, or an executor adding nodes) does not make an unattended run unbounded.
    planned = {n.id for n in P.nodes(store) if n.state not in P.GONE}
    while True:
        ready = [
            n
            for n in P.ready(P.nodes(store), P.Caller("agent", False))
            if n.id in planned and n.id not in tried and (not only or n.id in only)
        ]
        if not ready:
            return finished
        tried.add(ready[0].id)
        node = run_node(store, ready[0].id, checkout, template, attempts, say, logs)
        if node is not None:
            finished.append(node)
            _said_done(node, say)


# -- in parallel, a worktree a leaf ---------------------------------------------------------------------


def _git(where: Path, *args: str, ok: bool = False) -> subprocess.CompletedProcess:
    out = subprocess.run(["git", "-C", str(where), *args], capture_output=True, text=True)
    if out.returncode != 0 and not ok:
        raise P.Refused(
            f"git {' '.join(args[:3])} failed in {where}: {(out.stderr or out.stdout).strip()[:300]}"
        )
    return out


def worktree_for(store, root: Path, target: Path, node_id: str) -> Path:
    """A fresh worktree for one leaf, on branch graphene/<id>, cut from where the target stands now
    (so it has everything that has landed). What an earlier run left under the same name goes."""
    path = root / ".graphene" / WORKTREES / node_id
    _git(target, "worktree", "remove", "--force", str(path), ok=True)
    _git(target, "worktree", "prune", ok=True)
    shutil.rmtree(path, ignore_errors=True)  # a directory git has lost track of (a killed run) goes too
    _git(target, "worktree", "add", "--quiet", "-B", f"graphene/{node_id}", str(path), "HEAD")
    # The person's hook settings are usually untracked (`graphene init` keeps them out of git through
    # .git/info/exclude, which every worktree shares), so a fresh worktree has none and the hooks
    # would not run there. Copied, they do; ignored by git, the copy is nobody's change.
    hooks = Path(".claude") / "settings.local.json"
    if (target / hooks).is_file() and _git(target, "check-ignore", "-q", str(hooks), ok=True).returncode == 0:
        (path / hooks).parent.mkdir(exist_ok=True)
        (path / hooks).write_bytes((target / hooks).read_bytes())
    P.mark_boundary(store, path)  # a path used before starts clean: nothing here was "changed between nodes"
    return path


def land(
    store,
    target: Path,
    tree: Path,
    node: P.Node,
    say: Callable[[str], None],
    not_here: set[str] = frozenset(),
) -> bool:
    """Commit the leaf's work on its branch and merge it into the checkout the run was started from.
    True when it landed. When the merge is not clean nothing in the target is touched: the leaf waits
    for the person in review, on its branch, and what needs it waits with it."""
    branch = f"graphene/{node.id}"
    who = P.Caller("graphene run", False)
    entry = (store.node_log(node.id, ("finished", "overruled")) or [{"detail": {}}])[-1]["detail"]
    paths = entry.get("changed") or []
    why = " > ".join(P.trail(store, node))
    message = f"{node.title}\n\n{node.goal or node.title}\n\n" + (f"Why: {why}\n" if why else "")
    ident = [] if _git(tree, "config", "user.email", ok=True).stdout.strip() else [
        "-c", "user.name=graphene", "-c", "user.email=graphene@localhost"]  # fmt: skip
    # a merge of the person's own, half done: theirs to finish, and never ours to abort
    theirs = _git(target, "rev-parse", "-q", "--verify", "MERGE_HEAD", ok=True).returncode == 0
    try:
        if theirs:
            raise P.Refused(f"a merge of your own is in progress in {target}; finish it or abort it first")
        _git(tree, "add", "-A", "--", *(paths if paths and not entry.get("more_changed") else ["."]))
        if _git(tree, "diff", "--cached", "--quiet", ok=True).returncode != 0:  # else it committed itself
            _git(tree, *ident, "commit", "-q", "--no-verify", "-m", f"{message}Graphene-Node: {node.id}\n")
        _git(target, *ident, "merge", "--no-ff", "--no-edit", "-m", f"{node.title} ({node.id})", branch)
    except P.Refused as no:
        if not theirs:
            _git(target, "merge", "--abort", ok=True)
        said = [" ".join(str(no).split())]
        with store.claim():
            fresh = P.get(store, node.id)
            fresh.state = P.REVIEW
            P._save(store, fresh, "unlanded", who, P._now(), branch=branch, worktree=str(tree), why=said[:6])
        say(
            f"{node.id} passed its boundary and did not land: {said[0]}. Your checkout is as it was; its "
            f"work is in {tree}, on {branch}. `git merge {branch}` when the way is clear, then `graphene "
            f"node signoff {node.id}`; or `graphene node reopen {node.id} --note …` to have it done again "
            "on top of what is there now"
        )
        return False
    store.log_node(node.id, P._now(), "landed", who.label, None, None,
                   {"commit": P.head(target), "branch": branch})  # fmt: skip
    _git(target, "worktree", "remove", "--force", str(tree), ok=True)
    _git(target, "branch", "-D", branch, ok=True)
    P.mark_boundary(store, target)
    for up in P.roll_up(store, who, target, not_here=not_here):
        say(f"{up.id} is {'done' if up.state == P.DONE else 'finished; it waits for a sign-off'}: "
            "everything under it is" + (f", and `{up.check}` passes" if up.check else ""))  # fmt: skip
    return True


def may_collide(a: list[str], b: list[str]) -> bool:
    """Could two scopes ever claim one path? Asked of the globs themselves, not of the files that
    exist: `**/*.py` and `src/**` share no tracked file in a repo with no Python under src/, and both
    leaves then wrote src/new.py. Two globs may meet unless the directories they name before their
    first wildcard are different branches of the tree. Exclusions are ignored: holding a leaf back
    costs minutes, and a collision costs the person a merge."""

    def fixed(glob: str) -> list[str]:
        parts = glob.strip().removeprefix("./").rstrip("/").split("/")
        upto = next((k for k, part in enumerate(parts) if any(c in part for c in "*?")), len(parts))
        return parts[:upto]

    pairs = [(fixed(x), fixed(y)) for x in a if not x.startswith("!") for y in b if not y.startswith("!")]
    return any(x[: len(y)] == y[: len(x)] for x, y in pairs)


def _only_run(root: Path):
    """One parallel run a repo: a second one would clear the first one's worktrees from under it."""
    lock = root / ".graphene" / "run.lock"
    lock.parent.mkdir(exist_ok=True)
    try:
        other = int(lock.read_text())
        os.kill(other, 0)
        raise P.Refused(
            f"another `graphene run --parallel` is going here (pid {other}); `graphene watch` shows it"
        )
    except (OSError, ValueError):
        pass  # no lock, or the run that left it is gone
    lock.write_text(str(os.getpid()))
    return lock


def run_parallel(
    open_store: Callable[[], object],
    root: Path,
    target: Path,
    workers: int,
    template: str = DEFAULT_WITH,
    attempts: int = ATTEMPTS,
    only: list[str] | None = None,
    say: Callable[[str], None] = print,
    logs: Path | None = None,
) -> list[P.Node]:
    """Every leaf an agent can reach, up to ``workers`` at once, each in its own worktree; landed one
    at a time, here, as they finish. A leaf never starts while something it needs has not landed, or
    while a leaf whose scope overlaps its own is in flight."""
    if _git(target, "symbolic-ref", "-q", "HEAD", ok=True).returncode != 0:
        raise P.Refused(
            f"{target} is on no branch (a detached HEAD): leaves merged here would belong to no branch "
            "and be lost at the next checkout. `git switch <branch>` first"
        )
    lock = _only_run(root)
    try:
        return _run_parallel(open_store, root, target, workers, template, attempts, only, say, logs)
    finally:
        lock.unlink(missing_ok=True)


def _run_parallel(open_store, root, target, workers, template, attempts, only, say, logs) -> list[P.Node]:
    store = open_store()
    # No other run is alive (the lock), so a leaf still held from inside a run's worktree was left
    # by one that was killed: hand it back, or this run would find nothing ready and say nothing.
    for n in P.nodes(store, (P.RUNNING,)):
        if (n.executor or "").startswith("run:") and f"{os.sep}.graphene{os.sep}{WORKTREES}{os.sep}" in (
            n.checkout or ""
        ):
            P.release(
                store, n.id, P.Caller("graphene run", True), "the run that held it ended without finishing it"
            )
            say(f"{n.id} was left running by a run that ended; handed back, and it is ready again")
    planned = {n.id for n in P.nodes(store) if n.state not in P.GONE}
    files = P.tracked(target)
    tried: set[str] = set()
    flying: dict[Future, tuple[P.Node, Path]] = {}
    unlanded: set[str] = set()
    finished: list[P.Node] = []

    def work(node_id: str, tree: Path) -> P.Node | None:
        with open_store() as mine:  # a thread, a connection
            return run_node(mine, node_id, tree, template, attempts, say, logs)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        while True:
            everything = P.nodes(store)
            by_id = {n.id: n for n in everything}
            busy = {n.id for n, _ in flying.values()} | unlanded
            for n in P.ready(everything, P.Caller("agent", False)):
                if len(flying) >= workers:
                    break
                if n.id not in planned or n.id in tried or (only and n.id not in only):
                    continue
                if busy & set(P.all_needs(n, by_id)):
                    continue  # done in its worktree is not yet here
                clash = next(
                    (
                        o
                        for o, _ in flying.values()
                        if may_collide(n.scope, o.scope) or P.overlap(n.scope, o.scope, files)
                    ),
                    None,
                )
                if clash is not None:
                    continue  # one writer a path: it starts when that one has landed, on top of it
                tried.add(n.id)
                tree = worktree_for(store, root, target, n.id)
                flying[pool.submit(work, n.id, tree)] = (n, tree)
            if not flying:
                return finished
            for future in wait(flying, return_when=FIRST_COMPLETED).done:
                was, tree = flying.pop(future)
                try:
                    node = future.result()
                except P.Refused as no:  # one leaf's trouble (its executor would not start) is not the run's
                    say(str(no))
                    node = None
                if node is None:  # handed back: its worktree stays, with whatever it tried, for the person
                    say(f"{was.id}: what it tried is kept in {tree} until the next run takes {was.id} again")
                    continue
                elsewhere = {n.id for n, _ in flying.values()} | unlanded
                if land(store, target, tree, node, say, elsewhere):
                    finished.append(P.get(store, node.id))
                    _said_done(finished[-1], say)
                    files = P.tracked(target)
                else:
                    unlanded.add(node.id)
