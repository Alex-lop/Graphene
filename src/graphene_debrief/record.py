"""What the records say was written, and how much of what git committed they account for.

Two kinds of recorded write exist: ``edit`` (the payload of an Edit, Write, MultiEdit or
NotebookEdit call) and ``shell`` (the list of changed files Claude Code attaches to a Bash call as
``bashEditDiff``). Coverage then grades every path in the commits of a run's window by the best
evidence for it; it is always several counts, never one number (docs/PRODUCT_THESIS.md, section 9).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime

from .model import Agent, Commit, ToolEvent

FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
WRITE_GRADES = ("edit", "shell")


def seconds(stamp: str) -> float:
    """An ISO timestamp (``Z`` or an offset) as seconds since the epoch."""
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()


@dataclass(slots=True)
class Change:
    """One recorded write to one file in the repo."""

    path: str  # repo-relative
    session_id: str
    agent_id: str | None
    timestamp: str
    grade: str  # edit | shell
    event_id: str
    shared: bool = False  # the vendor's flag: the change may belong to a concurrent command
    copy: bool = False  # written in a worktree copy of the path


@dataclass(slots=True)
class Omitted:
    """What the vendor's change lists say they left out."""

    more_files: int = 0  # files past the end of a list
    unavailable: int = 0  # Bash calls whose list could not be computed


def worktree_roots(agents: list[Agent]) -> list[str]:
    """Worktree roots the agents are recorded working in, longest first (``.claude/worktrees/`` is
    inside the repo root, so the longer prefix has to win)."""
    roots = {os.path.normpath(a.worktree) for a in agents if a.worktree}
    return sorted(roots, key=len, reverse=True)


def repo_path(path: str, repo: str, roots: list[str]) -> tuple[str, bool] | None:
    """(repo-relative path, is it a worktree copy) for an absolute path, or None when it lies
    outside the repo and every known worktree of it."""
    p = os.path.normpath(path)
    for root in roots:
        if p.startswith(root + os.sep):
            return os.path.relpath(p, root), True
    r = os.path.normpath(repo)
    return (os.path.relpath(p, r), False) if p.startswith(r + os.sep) else None


def changes(events: list[ToolEvent], agents: list[Agent], repo: str) -> tuple[list[Change], Omitted]:
    """Every recorded write in these events, oldest first, and what the vendor's lists left out."""
    roots = worktree_roots(agents)
    out: list[Change] = []
    omitted = Omitted()
    for e in events:
        if e.success is False:
            continue
        if e.tool in FILE_TOOLS and e.file_path and not os.path.isabs(e.file_path):
            given = str(e.input.get("file_path") or e.input.get("notebook_path") or "")
            given = given if os.path.isabs(given) else os.path.join(e.cwd or repo, given)
            copy = any(os.path.normpath(given).startswith(root + os.sep) for root in roots)
            out.append(Change(e.file_path, e.session_id, e.agent_id, e.timestamp, "edit", e.id, copy=copy))
        diff = e.response.get("bashEditDiff") if e.tool == "Bash" and isinstance(e.response, dict) else None
        if not isinstance(diff, dict):
            continue
        if diff.get("unavailable"):
            omitted.unavailable += 1
            continue
        more = diff.get("moreFiles")
        omitted.more_files += more if isinstance(more, int) else 0
        listed = [p for p in diff.get("changedFiles") or [] if isinstance(p, str)]
        listed += [f.get("filePath") for f in diff.get("files") or [] if isinstance(f, dict)]
        for path in dict.fromkeys(p for p in listed if isinstance(p, str)):
            full = path if os.path.isabs(path) else os.path.join(e.cwd or repo, path)
            mapped = repo_path(full, repo, roots)
            if mapped:
                out.append(
                    Change(
                        mapped[0],
                        e.session_id,
                        e.agent_id,
                        e.timestamp,
                        "shell",
                        e.id,
                        shared=bool(diff.get("shared")),
                        copy=mapped[1],
                    )
                )
    out.sort(key=lambda c: (c.timestamp, c.event_id, c.path))
    return out, omitted


RANK = {"edit": 3, "shell": 2, "commit": 1, "window": 0}


@dataclass(slots=True)
class Coverage:
    """Of the files the window's commits changed: traced to a recorded write (``edit``, else
    ``shell``), only to an agent's recorded commit, or to nothing. ``window`` is the part of
    ``nothing`` committed inside the window by no identifiable agent; every path is in one grade."""

    committed_files: int = 0
    edit: int = 0
    shell: int = 0
    commit: int = 0
    nothing: int = 0
    window: int = 0
    grades: dict[str, str] = field(default_factory=dict)  # path -> its best grade over its commits
    pairs: dict[tuple[str, str], str] = field(default_factory=dict)  # (sha, path) -> grade

    @property
    def write(self) -> int:
        return self.edit + self.shell


def window_commits(commits: list[Commit], session_ids: list[str]) -> list[Commit]:
    """The run's commits: those in its window that no other session is recorded making."""
    return [c for c in commits if c.session_id is None or c.session_id in session_ids]


def coverage(commits: list[Commit], written: list[Change], session_ids: list[str]) -> Coverage:
    """Grade every path of every commit in the run (every path, no exclusions). A commit's path is
    graded by the writes recorded since the previous commit that held it and no later than this
    one: ``edit``, else ``shell``; with none, ``commit`` when an agent is recorded making the commit,
    else ``window``. That depends only on records up to the commit, so it never changes afterwards.
    A path counts once, under the best grade any of its commits reached."""
    cov = Coverage()
    since: dict[str, float] = {}
    for c in sorted(window_commits(commits, session_ids), key=lambda c: (seconds(c.committed_at), c.sha)):
        at = seconds(c.committed_at)
        for path, _status in c.files:
            grade = "commit" if c.session_id is not None else "window"
            for w in written:
                if w.path == path and since.get(path, float("-inf")) < seconds(w.timestamp) <= at:
                    grade = max(grade, w.grade, key=RANK.__getitem__)
            since[path] = at
            if c.origin_sha:  # a recorded cherry-pick copies its origin's change, and its evidence
                grade = max(grade, cov.pairs.get((c.origin_sha, path), grade), key=RANK.__getitem__)
            cov.pairs[(c.sha, path)] = grade
            cov.grades[path] = max(cov.grades.get(path, grade), grade, key=RANK.__getitem__)
    for grade in cov.grades.values():
        setattr(cov, grade, getattr(cov, grade) + 1)
    cov.committed_files, cov.nothing = len(cov.grades), cov.window
    return cov
