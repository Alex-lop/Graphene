"""One node's record: who held it, what git says changed while they did, how much of that is
verified, what was refused, and what a person decided about it.

This is the session product, re-rooted on the node, and it works for whoever did the work. The
evidence it stands on needs no vendor: the node's own log (started, with the base sha; finished or
released, with git's answer at that moment), git itself (the commits inside each window), and the
check Graphene ran. Where a Claude Code session held the node its records are read too, and they
add one thing only — which changed path traces to a write somebody recorded making. For a Codex
agent, a person, or `graphene run --with <anything>` that detail is missing and everything else
still holds, so the line says how many paths git named and that none of them traces to a recorded
write, never "0 of 0".

Plain functions over rows, and nothing from typer or rich at the top, so asking for a record costs
a store read and a git call.

Nothing inferred is shown as a fact. One record this repo does not keep is git's HEAD at the moment
a node finished, so ``git diff base..that`` cannot be asked for a window that has closed; the
window says so and names what was read instead. A count that cannot be computed honestly says
``not computed`` and why, and is never computed from something else that happens to be at hand.
"""

from __future__ import annotations

import subprocess
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import plan as P
from .commits import window as commits_in
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
    ended_head: str | None = None  # HEAD when it ended, from the entry that ended it
    at_end: list[str] | None = None  # what git said had changed when it ended; None when not logged
    under: list[str] | None = None  # git's own answer for this window; None when it cannot be had
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
    # TODO: every commit the store holds, then windowed here; a windowed query when one repo's
    # store holds a year of them.
    credited = {c.sha: c for c in store.commits_between("0000", "9999")}
    inside: dict[str, object] = {}
    for window in windows:
        mine = _commits(window, root, credited, at)
        window.commits = [c.sha for c in mine]
        inside |= {c.sha: c for c in mine}
        _fill(window, node, mine, root, at)
    return NodeRecord(
        node.id,
        node.title,
        node.state,
        node.owner,
        list(node.scope),
        P.done_means(node),
        at,
        windows,
        _coverage(store, node, windows, list(inside.values()), at),
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
            out[-1].ended_head, out[-1].at_end = detail.get("head"), detail.get("changed")
    return out


def _and(before: str | None, source: str) -> str:
    return source if not before else f"{before} and {source}"


def _shift(stamp: str, delta: int) -> str:
    """An ISO stamp moved a few seconds, because git's own date filter is coarser than ours: the
    window is asked of git wide and then cut to the second here."""
    moved = datetime.fromisoformat(stamp.replace("Z", "+00:00")) + timedelta(seconds=delta)
    return moved.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _commits(window: Window, root: str | Path, credited: dict, at: str) -> list:
    """Every commit git holds whose committer time falls inside the window, whoever made it.

    Git is asked directly, not only the store: the store holds a commit only when a recorded
    session's window covered it, so for a node done by Codex, by `graphene run --with …` or by a
    person there would be none, and a count of zero would read as "nothing was committed" when the
    truth is that nobody recorded it. The store's own rows are merged in where they exist, because
    those carry the call that made the commit, which is what grades it.
    """
    lo, hi = seconds(window.started_at), seconds(window.ended_at or at)
    wide = (_shift(window.started_at, -2), _shift(window.ended_at or at, 2))
    found = {c.sha: c for c in commits_in(Path(root), *wide)}
    found |= credited  # the store's rows win: they name the session and the call
    mine = [c for c in found.values() if lo <= seconds(c.committed_at) <= hi]
    return sorted(mine, key=lambda c: (seconds(c.committed_at), c.sha))


def _fill(window: Window, node: P.Node, commits: list, root: str | Path, at: str) -> None:
    """What changed in this window, from the records that exist: for a window that has ended, what
    git said had changed at that moment (logged by ``plan.finish`` and ``plan.release``); for the
    open window of a running node, the working tree now; and in both, the commits whose time falls
    inside it. ``under`` is git's own answer for the window, and stays None when there is none: a
    window that ended before that was logged has only its commits, and says so."""
    for commit in commits:
        for path, _status in commit.files:
            window.changed[path] = _and(window.changed.get(path), f"commit {commit.sha[:7]}")
    base = window.base_sha[:7] if window.base_sha else "no commit"
    if window.at_end is not None:  # logged when it ended: git's own answer, however it was written
        for path in window.at_end:
            window.changed[path] = _and(window.changed.get(path), "git, when it ended")
        window.under = list(window.at_end)
        end = f" to {window.ended_head[:7]}" if window.ended_head else ""
        window.sources.append(f"from {base}{end}: what git said had changed when it ended")
        return
    if window.ended_at is not None or node.state != P.RUNNING:
        n = len(commits)
        window.sources.append(
            f"started at {base}; what git said when it ended was not logged (a store from before "
            f"0.3), so this is read from the {n} commit{'' if n == 1 else 's'} whose "
            "time falls inside it, which is not evidence that nothing else changed"
        )
        return
    checkout = node.checkout or str(root)
    try:
        paths = P.changed_since(checkout, node.base_sha, node.dirty_at_start)
    except (P.Refused, OSError, subprocess.TimeoutExpired) as no:
        window.sources.append(f"the working tree could not be read, so what is uncommitted is missing: {no}")
        return
    for path in paths:
        window.changed[path] = _and(window.changed.get(path), "the working tree")
    window.under = paths
    window.sources.append(f"from {base}: the working tree of {checkout} as it stands at {at}")


def _coverage(store, node: P.Node, windows: list[Window], commits: list, at: str) -> dict:
    """What can be said about this node's work, and by what evidence.

    Two counts, and each says what it was read from. The first needs no vendor: of the paths git
    itself said had changed under the node (logged when each window ended, or read from the working
    tree while it is open), how many are inside the scope, and how many trace to a write somebody
    recorded making. The second is the commits inside the windows, graded the way a run's are.

    Where no Claude Code session held the node — Codex, `graphene run --with …`, a person — the
    grading detail is simply absent: the paths and the commits are still git's own answer, and the
    line says every one of them traces to git alone rather than reporting nothing at all.

    Every commit those sessions are recorded for is graded first, and this node's are selected
    afterwards, never the other way round: ``record.coverage`` grades a commit's path by the writes
    recorded since the previous commit of that path *in the list it is given*, so a list cut to the
    window would grade its first commit against everything before it and flatter the count.

    And a write counts for this node only when it was recorded inside one of its windows. Grading
    has no floor at the window's start, so a write recorded before the node was taken, with no
    commit of that path in between, would otherwise verify a commit made inside it (the review of
    this module found that with a probe; tests/test_node_record.py keeps it).
    """
    under = sorted({path for w in windows for path in (w.under or [])})
    blind = [w.n for w in windows if w.under is None]
    counts = {
        "changed_files": len(under),  # what git itself said had changed under the node
        "changed_in_scope": sum(P.in_scope(path, node.scope) for path in under),
        "changed_edit": 0,
        "changed_shell": 0,
        "changed_nothing": len(under),
        "changed_computed": bool(windows) and not (blind and not under),
        "blind_windows": blind,
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
        "read_from": "",
        "why_not": "",
    }
    if not windows:
        counts["why_not"] = "nobody has held this node, so there is no window for git to answer for"
    elif not counts["changed_computed"]:
        counts["why_not"] = (
            f"what git said had changed was not logged when window{_s(len(blind))} "
            f"{', '.join(str(n) for n in blind)} ended, and no window is open to read the tree of"
        )
    ids = sorted({w.session_id for w in windows if w.session_id})
    held = ", ".join(dict.fromkeys(w.executor or "an executor the log does not name" for w in windows))
    if not ids:
        counts["read_from"] = (
            f"the node's log and git. No vendor keeps records for {held or 'nobody'}, so nothing here "
            "says which path a write somebody recorded making accounts for"
        )
        one = "it" if len(commits) == 1 else "them"
        return _not_computed(counts, commits, f"no session's records account for {one}")
    # here, not at the top: graph reaches rich through its own imports, and a record is cheap without it
    from .graph import coverage_counts, run_records

    run = run_records(store, ids)
    counts["read_from"] = (
        f"the node's log, git, and Claude Code's records for "
        f"session{_s(len(ids))} {', '.join(i[:8] for i in ids)}"
    )
    if not run.sessions:
        return _not_computed(
            counts,
            commits,
            f"session{_s(len(ids))} {', '.join(i[:8] for i in ids)} held it and the store holds no "
            f"records of {'it' if len(ids) == 1 else 'them'}",
        )
    graded = {c.sha for c in run.commits}
    spans = [(seconds(w.started_at), seconds(w.ended_at or at)) for w in windows]
    written_inside: dict[str, str] = {}  # path -> the best grade of a write recorded inside a window
    for change in run.written:
        if any(lo <= seconds(change.timestamp) <= hi for lo, hi in spans):
            best = written_inside.get(change.path, change.grade)
            written_inside[change.path] = max(best, change.grade, key=RANK.__getitem__)
    for (
        path
    ) in under:  # a node's work is often never committed inside it: git's answer at its end is graded too
        grade = written_inside.get(path)
        if grade:
            counts[f"changed_{grade}"] += 1
            counts["changed_nothing"] -= 1
    selected, ungraded = Coverage(), set()
    for commit in commits:
        for path, _status in commit.files:
            grade = run.coverage.pairs.get((commit.sha, path)) if commit.sha in graded else None
            if grade is None:
                ungraded.add(path)
                continue
            if grade in ("edit", "shell"):  # a write: only one recorded while the node was held counts
                inside = written_inside.get(path)
                grade = (
                    min(grade, inside, key=RANK.__getitem__)
                    if inside
                    else ("commit" if commit.session_id else "window")
                )
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
        f"  state: {record.state} · owner {record.owner}",
    ]
    lines += _window_lines(record)
    lines += _coverage_lines(record.coverage, record.refusals.last_check)
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
            lines.append("    nothing changed")
    return lines


def _coverage_lines(counts: dict, check: dict | None) -> list[str]:
    """The coverage block, in the same shape whoever did the work: what git said changed, what the
    grading was read from, what Graphene's own check said, and the commits inside the windows."""
    n, k = counts["changed_files"], counts["commits"]
    if not counts["changed_computed"]:
        lines = [f"  coverage: not computed — {counts['why_not']}"]
        if not k:
            return lines
    elif n:
        lines = [
            f"  coverage: of the {n} path{_s(n)} git said had changed under this node, "
            f"{counts['changed_in_scope']} inside its scope; {counts['changed_edit']} to a recorded "
            f"edit, {counts['changed_shell']} to a recorded shell command, "
            f"{counts['changed_nothing']} to git alone"
        ]
    else:
        lines = ["  coverage: git says nothing changed under this node"]
    if n or k:
        lines.append(f"    read from: {counts['read_from']}")
    if check:
        lines.append(
            f"    check: `{check['command']}` {check['result']} at {check['at']}, run by Graphene itself"
        )
    else:
        lines.append("    check: none has run for this node, so nothing here is verified by one")
    if not k:
        lines.append("    no commit was made inside its windows, so there is no commit to grade")
    elif counts["computed"]:
        lines.append(
            f"    of the {counts['committed_files']} file{_s(counts['committed_files'])} in the "
            f"{k} commit{_s(k)} inside its windows, {counts['write']} "
            f"trace{'s' if counts['write'] == 1 else ''} to a recorded write ({counts['edit']} edit, "
            f"{counts['shell']} shell), {counts['commit']} only to an agent's commit, "
            f"{counts['nothing']} to nothing"
        )
        lines.append(f"      {counts['how']}")
    else:
        lines.append(
            f"    {k} commit{_s(k)} inside its windows ({counts['not_graded_files']} "
            f"file{_s(counts['not_graded_files'])}), not graded: "
            f"{counts['how'].removeprefix('not computed: ')}"
        )
    if counts["computed"] and counts["not_graded_commits"]:
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
    if not head:
        return ["  refused: nothing"]
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
    return lines  # the last check is a coverage line: it is what verifies the change set


def _act_lines(acts: list[Act]) -> list[str]:
    if not acts:
        return ["  nobody has accepted, edited, signed off, sent back or handed back this node"]
    kinds = {a.kind: a.kind.replace("_", " ") for a in acts}
    wide, who = max(len(k) for k in kinds.values()), max(len(a.actor or "") for a in acts)
    lines = ["  what people did to it:"]
    for a in acts:
        lines.append(f"    {a.at}  {kinds[a.kind].ljust(wide)}  {(a.actor or '').ljust(who)}  {a.said}")
    return [line.rstrip() for line in lines]
