"""Territory: which folders each task may write, as a few rows of bars and numbers. Pure functions.

A task's scope is a list of globs; `in_scope(path, scope)` is Graphene's own rule (the same one the hook
that refuses a write uses), so what this shows is the law, not a guess. The file list is what git tracks.

Three lenses on the same rows:
  plan     what the tasks that are not done may touch (the blast radius, before you accept)
  live     the same, with what is being touched now and what was stopped at a folder's edge
  changed  what finished tasks actually changed, and whether any of it was outside their scope
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

from graphene_map import plan as P

LENSES = ("plan", "live", "changed")


@lru_cache(maxsize=200_000)
def _in(path: str, scope: tuple[str, ...]) -> bool:
    return P.in_scope(path, list(scope))


@dataclass
class Group:
    name: str  # "models/", "src/graphene_map/", "(root)"
    files: list[str] = field(default_factory=list)
    protected: bool = False
    owners: Counter = field(default_factory=Counter)  # task id -> files of this group inside its scope
    changed: Counter = field(default_factory=Counter)  # task id -> files it changed here
    new: bool = False  # a place where files may appear that git does not track yet
    outside: int = 0  # changed files that were outside the changing task's scope
    touched: int = 0  # files edited now (live)
    stopped: int = 0  # writes stopped at this group's edge (live)
    stopped_by: list[str] = field(default_factory=list)


def group_files(files: list[str], rows: int = 10) -> list[Group]:
    """Group tracked files by folder: start at the first level and split the biggest group until there
    are ``rows`` of them or none is worth splitting; tiny groups fold into "other"."""

    def key(path: str, depth: int) -> tuple[str, ...]:
        parts = path.split("/")[:-1]
        return tuple(parts[:depth])

    groups: dict[tuple[str, ...], list[str]] = {}
    for f in files:
        groups.setdefault(key(f, 1), []).append(f)
    total = max(len(files), 1)
    while len(groups) < rows:
        big = max((k for k in groups if len(k) < 3), key=lambda k: len(groups[k]), default=None)
        if big is None or len(groups[big]) < max(0.22 * total, 12):
            break
        here = groups.pop(big)
        split: dict[tuple[str, ...], list[str]] = {}
        for f in here:
            parts = f.split("/")[:-1]
            split.setdefault(tuple(parts[: len(big) + 1]) if len(parts) > len(big) else big, []).append(f)
        if len(split) == 1:
            groups[big] = here
            break
        groups.update(split)
    out = [Group((("/".join(k) + "/") if k else "(root)"), v) for k, v in groups.items()]
    keep = [g for g in out if len(g.files) >= max(2, total // 60)]
    rest = [g for g in out if g not in keep]
    if rest:
        other = Group("other", [f for g in rest for f in g.files])
        keep.append(other)
    return sorted(keep, key=lambda g: (g.name == "other", -len(g.files), g.name))


def compute(
    files: list[str],
    tasks: dict[str, dict],
    protected: list[str] | None = None,
    *,
    lens: str = "plan",
    rows: int = 10,
) -> tuple[list[Group], dict]:
    """The rows and a summary. ``tasks`` maps id -> {state, scope, changed, touched, stopped}."""
    groups = group_files(files, rows)
    protected = protected or []
    claimed: set[str] = set()
    for g in groups:
        g.protected = (
            any(_in(f, tuple(protected)) for f in g.files[:1] + g.files[-1:]) if protected else False
        )
    where = {f: g for g in groups for f in g.files}
    for tid, t in tasks.items():
        scope = tuple(t.get("scope") or ())
        live = t["state"] in ("running", "ready", "review", "proposed", "came back", "waiting", "yours")
        if live and scope:
            for g in groups:
                inside = [f for f in g.files if _in(f, scope)]
                if inside:
                    g.owners[tid] += len(inside)
                    claimed.update(inside)
        for p in t.get("changed") or ():
            if p in where:
                where[p].changed[tid] += 1
                if scope and not _in(p, scope):
                    where[p].outside += 1
        for p in t.get("touched") or ():
            if p in where:
                where[p].touched += 1
        for p in t.get("stopped") or ():
            g = next((g for g in groups if g.name != "(root)" and p.startswith(g.name)), None)
            g = g or next((g for g in groups if g.name == "other" or g.name == "(root)"), None)
            if g:
                g.stopped += 1
                g.stopped_by.append(tid)
    for tid, t in tasks.items():  # scopes that match nothing tracked: where new files may appear
        scope = tuple(t.get("scope") or ())
        live = t["state"] in ("running", "ready", "review", "proposed", "came back", "waiting", "yours")
        for glob in scope if live else ():
            if glob.startswith("!") or any(_in(f, (glob,)) for f in files):
                continue
            prefix = glob.split("*")[0].rstrip("/")
            if prefix and "." in prefix.rsplit("/", 1)[-1]:  # a file: its folder is where it will appear
                prefix = prefix.rsplit("/", 1)[0] if "/" in prefix else ""
            name = (prefix + "/ (new)") if prefix else "(root) (new)"
            g = next((g for g in groups if g.new and g.name == name), None)
            if g is None:
                g = Group(name, [], new=True)
                groups.append(g)
            g.owners[tid] += 1
    total = len(files)
    summary = {
        "files": total,
        "may": len(claimed),
        "new": sum(1 for g in groups if g.new),
        "percent": round(100 * len(claimed) / total) if total else 0,
        "protected": [g.name for g in groups if g.protected],
        "outside": sum(g.outside for g in groups),
    }
    return groups, summary


def bar(group: Group, width: int, lens: str, color_of) -> list[tuple[str, str]]:
    """A bar of ``width`` cells as (text, style) runs. Segments are each task's share of the folder."""
    if group.new:  # no files yet: a hatched bar, one run per task that may create some
        runs = [("▒" * max(2, width // 4), color_of(tid)) for tid in list(group.owners)[:2]]
        used = sum(len(t) for t, _ in runs)
        return runs + ([("░" * (width - used), "grey23")] if used < width else [])
    n = max(len(group.files), 1)
    counts = group.changed if lens == "changed" else group.owners
    out: list[tuple[str, str]] = []
    used = 0
    for tid, c in counts.most_common():
        cells = max(1, round(width * min(c, n) / n))
        cells = min(cells, width - used)
        if cells <= 0:
            break
        out.append(("█" * cells, color_of(tid)))
        used += cells
    if used < width:
        out.append(("░" * (width - used), "grey23"))
    return out
