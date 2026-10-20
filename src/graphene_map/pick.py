"""Which fork of a leaf to keep, when several agents worked on it at once and more than one passed its check.

The rule, written on 20 October 2026 before any fork had run. Only a fork whose check passed in a clean copy,
with nothing outside its scope, can be kept. Among those, each step breaks only the ties of the step before:

1. **Agreement**: it passes the most of the passing forks' tests, its own included. A fork's tests are the
   files it changed that look like tests and that its check runs; "a's tests pass on b" means the leaf's own
   check passes on b's tree with a's versions of those files laid over it; a fork passes its own, since its
   check passed with them. A fork with no such files referees nobody. (CodeT's dual execution agreement, at
   its smallest: tests that only some forks pass are evidence about the others.)
2. **The check left alone**: it did not change a file its check ran at the base (a test made to agree).
3. **Smaller**: the fewest lines added and removed outside test files.
4. **Cheaper**: the fewest dollars, to the cent; a fork with no meter makes this step a tie.
5. **Sooner**: it finished first.

It is deterministic, never random and never a model's opinion, and the reason it gives names the step that
decided. The run calls `choose`; `overlay` and `size` are the git it needs."""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .views import money

TEST_DIRS = {"test", "tests", "spec", "specs", "__tests__", "testing"}


@dataclass
class Entry:
    """One fork, as it ended."""

    fork: str  # its letter
    passed: bool  # its check passed in its own tree, and it changed nothing outside its scope
    commit: str | None = None  # its in-scope changes, on the hold's base
    paths: list[str] = field(default_factory=list)  # what it changed
    lines: int = 0  # lines added and removed outside test files
    test_lines: int = 0
    tests: list[str] = field(default_factory=list)  # its changed test files that its check runs
    touched_check: list[str] = field(default_factory=list)  # files its check ran at the base that it changed
    dollars: float | None = None  # None: no meter
    seconds: float | None = None
    order: int = 0  # 0: it finished first
    state: str = ""  # how it ended, in a word: passed, refused, gave up, failed, stopped
    why: str = ""  # why it did not pass


@dataclass
class Choice:
    fork: str | None  # the letter kept; None when no fork passed
    reason: str  # one line, for the person
    table: list[dict]  # one row a fork, what each step saw
    agree: dict[str, list[str]]  # a fork, and the other forks whose tests pass on it


def is_test(path: str) -> bool:
    """Whether a path looks like a test, by the names test runners look for."""
    parts = PurePosixPath(path).parts
    if not parts:
        return False
    name = parts[-1]
    stem = name.split(".")[0]
    return (
        any(p in TEST_DIRS for p in parts[:-1])
        or stem.startswith("test_")
        or stem.endswith(("_test", "_spec", "Test", "Tests"))
        or ".test." in name
        or ".spec." in name
        or name == "conftest.py"
    )


def _owners(letters: list[str]) -> str:
    """`a's`, `a's and c's`, `a's, b's and c's`."""
    said = [f"{x}'s" for x in letters]
    return said[0] if len(said) == 1 else ", ".join(said[:-1]) + " and " + said[-1]


def _also(letters: list[str]) -> str:
    return letters[0] if len(letters) == 1 else ", ".join(letters[:-1]) + " and " + letters[-1]


def _cents(e: Entry) -> int | None:
    return None if e.dollars is None else round(e.dollars * 100)


def choose(entries: list[Entry], agrees: Callable[[str, str], bool] | None = None) -> Choice:
    """The fork to keep, by the rule above. ``agrees(a, b)``: whether a's tests pass on b's tree. It is asked
    only when two or more forks passed and one of them has tests, once for each such pair, in letter order;
    without it, agreement is a tie."""
    passed = sorted((e for e in entries if e.passed), key=lambda e: e.fork)
    agree: dict[str, list[str]] = {e.fork: [] for e in passed}
    scored = agrees is not None and len(passed) > 1 and any(e.tests for e in passed)
    if scored:
        for referee in passed:
            if not referee.tests:
                continue
            for other in passed:
                if other is not referee and agrees(referee.fork, other.fork):
                    agree[other.fork].append(referee.fork)
    table = [
        {"fork": e.fork, "state": e.state or ("passed" if e.passed else "refused"), "passed": e.passed,
         "agrees": agree.get(e.fork, []), "lines": e.lines, "test_lines": e.test_lines,
         "touched_check": bool(e.touched_check), "dollars": e.dollars, "seconds": e.seconds, "order": e.order,
         **({"why": e.why} if e.why and not e.passed else {})}
        for e in sorted(entries, key=lambda e: e.fork)
    ]  # fmt: skip
    if not passed:
        return Choice(None, "no fork's check passed", table, agree)
    if len(passed) == 1:
        return Choice(passed[0].fork, "the only fork whose check passed", table, agree)

    steps: list[tuple[str, Callable[[Entry], object]]] = [
        ("agreement", lambda e: -(len(agree[e.fork]) + bool(e.tests)) if scored else 0),  # its own pass
        ("untouched", lambda e: bool(e.touched_check)),
        ("lines", lambda e: e.lines),
        ("dollars", _cents),
        ("order", lambda e: e.order),
    ]
    pool, decided, losers = passed, "tie", []
    for name, value in steps:
        if name == "dollars" and any(_cents(e) is None for e in pool):
            continue  # an unmetered fork costs what nobody knows: no step to decide on
        best = min(value(e) for e in pool)  # type: ignore[type-var]
        kept = [e for e in pool if value(e) == best]
        if len(kept) < len(pool):
            decided, losers, pool = name, [e for e in pool if e not in kept], kept
            if len(pool) == 1:
                break
    if len(pool) > 1:  # the same in every step, finishing order included: the first letter, said so
        decided, losers = "tie", []
    k = pool[0]
    return Choice(k.fork, _reason(decided, k, losers, passed, agree), table, agree)


def _reason(step: str, k: Entry, losers: list[Entry], passed: list[Entry], agree: dict) -> str:
    """The step that decided, in a line, against the forks that step set aside."""
    if step == "agreement":
        said = f"passes {_owners(agree[k.fork])} tests" if agree[k.fork] else "passes its own tests"
        if k.tests:  # who the kept fork's own tests turned away
            failing = [e.fork for e in passed if e is not k and k.fork not in agree[e.fork]]
            if failing:
                said += f" ({_also(failing)} {'fails' if len(failing) == 1 else 'fail'} {k.fork}'s)"
        return said
    if step == "untouched":
        other = losers[0]
        return f"left the check's own files as they were ({other.fork} changed {other.touched_check[0]})"
    if step == "lines":
        other = min(losers, key=lambda e: e.lines)
        return f"{k.lines} line{'s' * (k.lines != 1)} against {other.lines}"
    if step == "dollars":
        other = min(losers, key=lambda e: e.dollars or 0.0)
        return f"{money(k.dollars or 0.0)} against {money(other.dollars or 0.0)}"
    if step == "order":
        return "finished first"
    return "the same in every step: the first by letter"


def _git(repo: str | Path, *args: str, env: dict | None = None) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60,
                         env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", **(env or {})})  # fmt: skip
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {repo}: {out.stderr.strip()[:200]}")
    return out.stdout


# an object made for one check run, never on a branch: who made it does not matter, that it can be made does
ANYONE = {"GIT_AUTHOR_NAME": "graphene", "GIT_AUTHOR_EMAIL": "graphene@localhost",
          "GIT_COMMITTER_NAME": "graphene", "GIT_COMMITTER_EMAIL": "graphene@localhost"}  # fmt: skip


def overlay(repo: str | Path, onto: str, source: str, paths: list[str]) -> str:
    """A commit with ``onto``'s tree and ``source``'s versions of ``paths`` laid over it (a path ``source``
    does not have is taken out). Made in an index of its own: nobody's checkout or index is touched."""
    fd, index = tempfile.mkstemp(prefix="graphene-overlay-", suffix=".index")
    os.close(fd)
    os.unlink(index)  # git makes it; an empty file is no index
    env = {"GIT_INDEX_FILE": index, **ANYONE}
    try:
        _git(repo, "read-tree", f"{onto}^{{tree}}", env=env)
        for path in paths:
            entry = _git(repo, "ls-tree", "-z", source, "--", path).rstrip("\0")
            if entry:
                mode, _kind, rest = entry.split(" ", 2)
                blob = rest.split("\t", 1)[0]
                _git(repo, "update-index", "--add", "--cacheinfo", f"{mode},{blob},{path}", env=env)
            else:
                _git(repo, "update-index", "--force-remove", "--", path, env=env)
        tree = _git(repo, "write-tree", env=env).strip()
        said = f"{source[:10]}'s {len(paths)} on {onto[:10]}"
        return _git(repo, "commit-tree", tree, "-p", onto, "-m", said, env=env).strip()
    finally:
        Path(index).unlink(missing_ok=True)


def size(repo: str | Path, base: str, commit: str, paths: list[str] | None = None) -> tuple[int, int]:
    """Lines added and removed from ``base`` to ``commit`` (in ``paths``, when given): outside test files, and
    in them. A binary file counts as no lines."""
    only = ["--", *paths] if paths else []
    out = _git(repo, "diff", "--numstat", "-z", "--no-renames", base, commit, *only)
    code = tests = 0
    for record in out.split("\0"):
        if not record:
            continue
        added, removed, path = record.split("\t", 2)
        n = (int(added) if added.isdigit() else 0) + (int(removed) if removed.isdigit() else 0)
        if is_test(path):
            tests += n
        else:
            code += n
    return code, tests
