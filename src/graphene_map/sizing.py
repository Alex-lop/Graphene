"""How coarse or fine the planner cuts a tree: the repo's files, lines and test layout, and the
directories the ask names."""

import re
from pathlib import Path, PurePosixPath

SIZES = ("auto", "finer", "coarser")


def _lines(root: Path, files: list[str]) -> int:
    total = 0
    for p in files:
        try:
            data = (root / p).read_bytes()
        except OSError:
            continue
        if b"\0" not in data[:8192]:
            total += data.count(b"\n")
    return total


def layout(files: list[str]) -> str:
    """'tests/' when the tests sit in one tests/ directory, 'beside' when next to the code, 'none' when
    there are none."""
    if any(set(PurePosixPath(p).parts[:-1]) & {"tests", "test"} for p in files):
        return "tests/"
    name = re.compile(r"(^test_.*|.*_test\.\w+|.*\.(test|spec)\.\w+)$")
    return "beside" if any(name.match(PurePosixPath(p).name) for p in files) else "none"


def named_dirs(sentence: str, files: list[str]) -> set[str]:
    """The directories of the repo the sentence names, by path or by a last name only one directory has;
    a named file names its directory."""
    dirs = {str(d) for p in files for d in PurePosixPath(p).parents if str(d) != "."}
    by_name: dict[str, set[str]] = {}
    for d in dirs:
        by_name.setdefault(PurePosixPath(d).name, set()).add(d)
    parent = {p: str(PurePosixPath(p).parent) for p in files}
    found: set[str] = set()
    for word in re.findall(r"[\w./-]+", sentence):
        word = word.strip("./")
        if word in dirs:
            found.add(word)
        elif parent.get(word, ".") != ".":
            found.add(parent[word])
        elif len(by_name.get(word, ())) == 1:  # a name many directories share ('sub', 'logs') means none
            found |= by_name[word]
    return found


def measure(root: str | Path, sentence: str, files: list[str], size: str = "auto") -> str:
    """One sentence telling the planner how coarse or fine to cut the tree for this repo and this ask."""
    if size not in SIZES:
        raise ValueError(f"size is auto, finer or coarser, not {size!r}")
    lines = _lines(Path(root), files)
    tests = layout(files)
    dirs = len(named_dirs(sentence, files))
    # ponytail: fixed line thresholds, tune against the four tasks and the public repos
    lo, hi = 1, 3 if lines < 2000 else 6 if lines < 20000 else 10  # the repo bounds it from above only
    lo = max(lo, min(dirs, hi))  # the directories named raise the floor, up to the repo's own bound
    hi = max(hi, lo + 1)
    if size == "finer":
        lo, hi = lo * 2, hi * 2
    elif size == "coarser":
        lo, hi = max(1, lo // 2), max(1, hi // 2)
    where = {
        "tests/": "tests live in one tests/ directory, so each leaf's check can be its own test file there",
        "beside": "tests sit next to the code, so each leaf's check can be a test beside what it changes",
        "none": "the repo has no tests, so each leaf's check must be a command that proves it",
    }[tests]
    named = "the ask names no directory"
    if dirs:
        named = f"the ask names {dirs} director{'y' if dirs == 1 else 'ies'}"
    leaves = f"{lo} leaf" if lo == hi == 1 else f"{lo} to {hi} leaves"
    return (
        f"The repo has {len(files):,} files and {lines:,} lines, {named}, and {where}: "
        f"cut the tree into about {leaves} ({size})."
    )
