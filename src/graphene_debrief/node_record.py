"""One node's record: who held it, what git says changed while they did, how much of that is
verified, what was refused, and what a person decided about it.

The debrief this repo already builds is a run's. This is the same evidence scoped to one node's
intent, which is where the coverage line belongs now: "what did the agent do for this node, and how
much of that is verified". Plain functions over rows, and nothing from typer or rich at the top, so
asking for a record costs a store read and a git call.

Nothing inferred is shown as a fact. One record this repo does not keep is git's HEAD at the moment
a node finished, so ``git diff base..that`` cannot be asked for a window that has closed; the
window says so and names what was read instead. A count that cannot be computed honestly says
``not computed`` and why, and is never computed from something else that happens to be at hand.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import plan as P
from .record import RANK, Coverage, seconds

# a window ends when the node does, however it ended; ``reopened`` comes after one, never inside it
ENDS = ("finished", "overruled", "released")
ACTS = ("accepted", "edited", "signed_off", "reopened", "overruled", "released", "dropped")


@dataclass(slots=True)
class Window:
    """One span the node was held for: started, until it was finished, handed back, or now."""

    n: int
    started_at: str
    ended_at: str | None = None
    ended_by: str = "still open"
    said: str = ""  # the reason logged with the end: why it was handed back, why the gate was overruled
    executor: str | None = None
    session_id: str | None = None
    base_sha: str | None = None  # HEAD when it was taken, from the 'started' entry
    checkout: str | None = None
    commits: list[str] = field(default_factory=list)  # shas whose commit time falls inside the window
    changed: dict[str, str] = field(default_factory=dict)  # path -> the records it was read from
    sources: list[str] = field(default_factory=list)  # what was read, and what was not there to read


@dataclass(slots=True)
class Refusals:
    """What the plan said no to while the node was held, counted from the log."""

    denied: list[str] = field(default_factory=list)  # one path per write refused before it happened
    breaches: list[str] = field(default_factory=list)  # one path per change refused after the fact
    stops: int = 0
    done: list[list[str]] = field(default_factory=list)  # the stray paths of each refused `done`
    checks_failed: int = 0
    last_check: dict | None = None  # {"result": passed|failed, "at": …, "command": …}


@dataclass(slots=True)
class Act:
    at: str
    kind: str
    actor: str | None
    said: str


@dataclass(slots=True)
class NodeRecord:
    node_id: str
    title: str
    state: str
    owner: str
    scope: list[str]
    done: str  # what "done" means for it, in the words its executor was told
    at: str  # when this record was taken: an open window runs up to here
    windows: list[Window] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    refusals: Refusals = field(default_factory=Refusals)
    acts: list[Act] = field(default_factory=list)


def node_record(store, root: str | Path, node: P.Node, at: str | None = None) -> NodeRecord:
    """Everything the records hold about one node, from the store and from git."""
    at = at or P._now()
    log = store.node_log(node.id)
    windows = _windows(log)
    # ponytail: every commit the store holds, then windowed here; a windowed query when one repo's
    # store holds a year of them. The store only holds commits git had inside a recorded session's
    # window, which is the hole `_fill` prints: one made while nothing was recorded is in neither.
    by_sha = {c.sha: c for c in store.commits_between("0000", "9999")}
    for window in windows:
        _fill(window, node, list(by_sha.values()), root, at)
    inside = [by_sha[sha] for sha in dict.fromkeys(sha for w in windows for sha in w.commits)]
    return NodeRecord(
        node.id,
        node.title,
        node.state,
        node.owner,
        list(node.scope),
        P.done_means(node),
        at,
        windows,
        _coverage(store, windows, inside),
        _refusals(log),
        _acts(log),
    )


def to_dict(record: NodeRecord) -> dict:
    return asdict(record)


def _windows(log: list[dict]) -> list[Window]:
    """The spans, from the log alone: a 'started' opens one and the next ending closes it. A node
    taken again after it was handed back or sent back has a window per take, each with the session
    logged on its own 'started' entry, because that is who is answerable for what changed in it."""
    out: list[Window] = []
    for entry in log:
        detail = entry["detail"]
        if entry["kind"] == "started":
            out.append(
                Window(
                    len(out) + 1,
                    entry["timestamp"],
                    executor=entry["actor"],
                    session_id=entry["session_id"],
                    base_sha=detail.get("base"),
                    checkout=detail.get("checkout"),
                )
            )
        elif entry["kind"] in ENDS and out and out[-1].ended_at is None:
            out[-1].ended_at, out[-1].ended_by = entry["timestamp"], entry["kind"]
            out[-1].said = detail.get("why") or detail.get("override") or ""
    return out


def _and(before: str | None, source: str) -> str:
    return source if not before else f"{before} and {source}"


def _fill(window: Window, node: P.Node, commits: list, root: str | Path, at: str) -> None:
    """What changed in this window, from the records that exist. The HEAD a node finished at is not
    one of them, so a closed window is read from the commits whose commit time falls inside it; an
    open one is read from the working tree too, which is where work not yet committed shows up."""
    start, end = seconds(window.started_at), seconds(window.ended_at or at)
    mine = [c for c in commits if start <= seconds(c.committed_at) <= end]
    window.commits = [c.sha for c in mine]
    for commit in mine:
        for path, _status in commit.files:
            window.changed[path] = _and(window.changed.get(path), f"commit {commit.sha[:7]}")
    base = window.base_sha[:7] if window.base_sha else "no commit"
    window.sources.append(
        f"started at {base}; the HEAD it ended at is not recorded, so what changed in this window is "
        f"read from the {len(mine)} commit{'' if len(mine) == 1 else 's'} whose commit time falls inside it"
    )
    if window.ended_at is not None or node.state != P.RUNNING:
        if not mine and window.ended_at is not None:
            window.sources.append(
                "and no commit in the store falls inside it: a commit made while no session was "
                "recorded is in no record here, so this is not a record that nothing changed"
            )
        return
    checkout = node.checkout or str(root)
    try:
        paths = P.changed_since(checkout, node.base_sha, node.dirty_at_start)
    except (P.Refused, OSError) as no:
        window.sources.append(f"the working tree could not be read, so what is uncommitted is missing: {no}")
        return
    for path in paths:
        window.changed[path] = _and(window.changed.get(path), "the working tree")
    window.sources.append(f"and from the working tree of {checkout} as it stands at {at}, against {base}")


def _coverage(store, windows: list[Window], commits: list) -> dict:
    """The three counts for this node: of the files in the commits inside its windows, how many
    trace to a recorded write by the session that held it, how many only to an agent's commit, how
    many to nothing.

    Every commit those sessions are recorded for is graded first, and this node's are selected
    afterwards, never the other way round: ``record.coverage`` grades a commit's path by the writes
    recorded since the previous commit of that path *in the list it is given*, so a list cut to the
    window would grade its first commit against everything before it and flatter the count.
    """
    counts = {
        "commits": len(commits),
        "committed_files": 0,
        "write": 0,
        "edit": 0,
        "shell": 0,
        "commit": 0,
        "nothing": 0,
        "window": 0,
        "not_graded_commits": 0,
        "not_graded_files": 0,
        "computed": False,
        "how": "",
    }
    ids = sorted({w.session_id for w in windows if w.session_id})
    if not ids:
        return _not_computed(
            counts,
            commits,
            "no session is recorded as holding this node, so there is no record of a write for its "
            "commits to trace to",
        )
    # here, not at the top: graph reaches rich through the debrief, and a record is cheap without it
    from .graph import coverage_counts, run_records

    run = run_records(store, ids)
    if not run.sessions:
        return _not_computed(
            counts,
            commits,
            f"session{_s(len(ids))} {', '.join(i[:8] for i in ids)} held it and the store holds no "
            f"records of {'it' if len(ids) == 1 else 'them'}",
        )
    graded = {c.sha for c in run.commits}
    selected, ungraded = Coverage(), set()
    for commit in commits:
        for path, _status in commit.files:
            grade = run.coverage.pairs.get((commit.sha, path)) if commit.sha in graded else None
            if grade is None:
                ungraded.add(path)
                continue
            selected.pairs[(commit.sha, path)] = grade
            selected.grades[path] = max(selected.grades.get(path, grade), grade, key=RANK.__getitem__)
    for grade in selected.grades.values():
        setattr(selected, grade, getattr(selected, grade) + 1)
    selected.committed_files, selected.nothing = len(selected.grades), selected.window
    counts |= coverage_counts(selected)
    counts["not_graded_commits"] = len([c for c in commits if c.sha not in graded])
    counts["not_graded_files"] = len(ungraded - set(selected.grades))
    counts["computed"] = True
    counts["how"] = (
        f"graded over all {len(run.commits)} commit{_s(len(run.commits))} recorded for "
        f"session{_s(len(ids))} {', '.join(i[:8] for i in ids)}, and this node's "
        f"{len(commits) - counts['not_graded_commits']} selected afterwards"
    )
    return counts


def _not_computed(counts: dict, commits: list, why: str) -> dict:
    """A count nothing can support honestly says so, and says how much it leaves unaccounted for."""
    counts["not_graded_commits"] = len(commits)
    counts["not_graded_files"] = len({path for c in commits for path, _ in c.files})
    counts["how"] = f"not computed: {why}"
    return counts


def _refusals(log: list[dict]) -> Refusals:
    out = Refusals()
    for entry in log:
        kind, detail = entry["kind"], entry["detail"]
        if kind == "denied":
            out.denied.append(str(detail.get("path", "?")))
        elif kind == "breach":
            out.breaches.extend(str(p) for p in detail.get("paths", []))
        elif kind == "stop_refused":
            out.stops += 1
        elif kind == "refused":
            out.done.append([str(p) for p in detail.get("outside", [])])
        elif kind in ("check_failed", "check_passed"):
            out.checks_failed += kind == "check_failed"
            out.last_check = {
                "result": "failed" if kind == "check_failed" else "passed",
                "at": entry["timestamp"],
                "command": detail.get("command", ""),
            }
    return out


def _acts(log: list[dict]) -> list[Act]:
    """What was decided about the node, with the words that came with the decision."""
    out: list[Act] = []
    for entry in log:
        kind, detail = entry["kind"], entry["detail"]
        if kind not in ACTS:
            continue
        if kind == "edited":
            changed = detail.get("changed", {})
            said = "; ".join(f"{f}: {a!r} -> {b!r}" for f, (a, b) in changed.items())
            said = f"{said} (revision {detail.get('rev')})"
        elif kind == "overruled":
            said = str(detail.get("override", ""))
            outside = detail.get("outside") or []
            said += f" (outside its scope: {', '.join(outside)})" if outside else ""
            said += "" if detail.get("check_passed", True) else " (and its check had failed)"
        else:
            said = str(detail.get("why") or detail.get("note") or "")
        out.append(Act(entry["timestamp"], kind, entry["actor"], said))
    return out


# -- the lines ------------------------------------------------------------------------------------


def _s(n: int) -> str:
    return "" if n == 1 else "s"


def render(record: NodeRecord) -> list[str]:
    """The record as plain lines, never wrapped and never cut: an agent reads them as evidence about
    the node it holds, and a person greps them."""
    lines = [
        f"{record.node_id}  {record.title}",
        f"  state: {record.state} · owner {record.owner} · scope {', '.join(record.scope)} "
        f"· done when {record.done}",
    ]
    lines += _window_lines(record)
    lines += _coverage_lines(record.coverage)
    lines += _refusal_lines(record.refusals)
    lines += _act_lines(record.acts)
    return lines


def _window_lines(record: NodeRecord) -> list[str]:
    if not record.windows:
        return ["  nobody has held this node yet, so no window and nothing changed under it"]
    lines = []
    for w in record.windows:
        held = w.executor or "an executor the log does not name"
        held += f", session {w.session_id}" if w.session_id else ", no session recorded"
        if w.ended_at is None:
            ended = f"{w.ended_by}, as this was read at {record.at}"
        else:
            ended = f"{w.ended_at}  {w.ended_by}" + (f": {w.said}" if w.said else "")
        lines.append(f"  window {w.n}: {held}  {w.started_at} -> {ended}")
        lines += [f"    {line}" for line in w.sources]
        for path, source in sorted(w.changed.items()):
            where = "in scope" if P.in_scope(path, record.scope) else "outside the scope"
            lines.append(f"    {where}: {path}  ({source})")
        if not w.changed:
            lines.append("    no path is recorded as changed inside this window")
    return lines


def _coverage_lines(counts: dict) -> list[str]:
    if not counts["computed"]:
        lines = [f"  coverage: not computed — {counts['how'].removeprefix('not computed: ')}"]
    else:
        lines = [
            f"  coverage: of the {counts['committed_files']} file{_s(counts['committed_files'])} in the "
            f"{counts['commits']} commit{_s(counts['commits'])} inside its windows, {counts['write']} "
            f"trace{'s' if counts['write'] == 1 else ''} to a recorded write ({counts['edit']} edit, "
            f"{counts['shell']} shell), {counts['commit']} only to an agent's commit, "
            f"{counts['nothing']} to nothing",
            f"    {counts['how']}",
        ]
    if counts["not_graded_commits"] or counts["not_graded_files"]:
        lines.append(
            f"    {counts['not_graded_commits']} commit{_s(counts['not_graded_commits'])} inside its "
            f"windows ({counts['not_graded_files']} file{_s(counts['not_graded_files'])}) are in no "
            "session's records: not graded, and not counted above"
        )
    return lines


def _refusal_lines(refusals: Refusals) -> list[str]:
    head = []
    if refusals.denied:
        head.append(f"{len(refusals.denied)} write{_s(len(refusals.denied))} denied")
    if refusals.breaches:
        head.append(f"{len(refusals.breaches)} change{_s(len(refusals.breaches))} refused after the fact")
    if refusals.stops:
        head.append(f"{refusals.stops} stop{_s(refusals.stops)} refused")
    if refusals.done:
        head.append(f"{len(refusals.done)} `done` refused")
    if refusals.checks_failed:
        head.append(f"{refusals.checks_failed} check{_s(refusals.checks_failed)} failed")
    if not head and refusals.last_check is None:
        return ["  refused: nothing, and no check has run"]
    lines = [f"  refused: {', '.join(head) or 'nothing'}"]
    for label, paths in (("denied", refusals.denied), ("refused after the fact", refusals.breaches)):
        counted = Counter(paths)
        if counted:
            lines.append(
                f"    {label}: "
                + ", ".join(f"{p}{'' if n == 1 else f' ×{n}'}" for p, n in sorted(counted.items()))
            )
    for stray in refusals.done:
        lines.append(f"    `done` refused over: {', '.join(stray) or 'a failing check'}")
    if refusals.last_check:
        check = refusals.last_check
        lines.append(f"    last check: {check['result']} at {check['at']} (`{check['command']}`)")
    return lines


def _act_lines(acts: list[Act]) -> list[str]:
    if not acts:
        return ["  nobody has accepted, edited, signed off, sent back or handed back this node"]
    kinds = {a.kind: a.kind.replace("_", " ") for a in acts}
    wide, who = max(len(k) for k in kinds.values()), max(len(a.actor or "") for a in acts)
    lines = ["  what people did to it:"]
    for a in acts:
        lines.append(f"    {a.at}  {kinds[a.kind].ljust(wide)}  {(a.actor or '').ljust(who)}  {a.said}")
    return [line.rstrip() for line in lines]
