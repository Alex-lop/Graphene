"""Reading a shell command: which files it writes, and whether it runs a check.

No model is involved and nothing here needs a vendor: it is text a shell would parse, and it
answers the two questions Graphene asks of a command. ``bash_written_paths`` is what the hook
refuses a write with, before the write happens (``gate.py``); ``check_segments`` is what names a
test or lint run on the map; ``shell_segments`` is what ``commits.py`` reads a `git commit` out of.
Deliberately incomplete, and the holes are printed where the controls are: a script that opens a
file itself is invisible here and is caught later, at the boundary, by git.
"""

from __future__ import annotations

import os
import re
import shlex
from functools import lru_cache
from pathlib import Path

CHECKERS = {
    "pytest",
    "py.test",
    "ruff",
    "mypy",
    "pyright",
    "tsc",
    "jest",
    "vitest",
    "eslint",
    "flake8",
    "make",
}
RUNNER_PREFIXES = (("uv", "run"), ("python", "-m"), ("python3", "-m"), ("poetry", "run"), ("pipenv", "run"))
_NOT_A_PATH = re.compile(r"[*?$`{}\[\]<>|]")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_SEPARATORS = re.compile(r"&&|\|\||;|\||\n")
_REDIRECTS = (">", ">>", "&>", ">|", "<", ">&", "<&")


# -- shell commands -----------------------------------------------------------------------------


def strip_heredocs(command: str) -> str:
    """Drop heredoc bodies so a `>` inside a script fed to a command is not read as a redirection."""
    lines = command.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        for marker in _HEREDOC.finditer(line):
            terminator = marker.group(2)
            while i < len(lines) and lines[i].strip() != terminator:
                i += 1
            i += 1
    return "\n".join(out)


def _strip_wrappers(tokens: list[str]) -> list[str]:
    while tokens and (
        ("=" in tokens[0] and not tokens[0].startswith("-")) or tokens[0] in ("sudo", "env", "time")
    ):
        tokens.pop(0)
    return tokens


def _unquoted_newlines_to_semicolons(text: str) -> str:
    out: list[str] = []
    quote: str | None = None
    escaped = False
    for ch in text:
        if escaped:
            escaped = False
        elif ch == "\\" and quote != "'":
            escaped = True
        elif quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "\n":
            out.append(";")
            continue
        out.append(ch)
    return "".join(out)


def shell_segments(command: str) -> list[list[str]]:
    """Token lists of each simple command, split on && || | ; & ( ) and unquoted newlines.

    Quotes are respected, so a `|` or an `rm` inside a grep pattern is not shell syntax.
    """
    text = _unquoted_newlines_to_semicolons(strip_heredocs(command))
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    segments: list[list[str]] = [[]]
    try:
        for token in lexer:
            if token in ("&&", "||", "|", ";", "&", "(", ")", ";;"):
                segments.append([])
            else:
                segments[-1].append(token)
    except ValueError:  # unbalanced quotes: fall back to a crude split
        segments = [segment.split() for segment in _SEPARATORS.split(text)]
    return [_strip_wrappers(segment) for segment in segments if segment]


def bash_written_paths(command: str, root: Path) -> list[tuple[str, str]]:
    """(repo-relative path, "write" | "delete") for the obvious forms: > >> tee sed -i mv cp rm touch.

    Relative paths follow `cd` inside the command; after a `cd` to a directory that cannot be
    resolved (a variable, a glob) relative paths are dropped rather than guessed. Deliberately
    incomplete: anything else a shell command does to a file is invisible here.
    """
    cwd: str | None = os.path.normpath(str(root))
    found: list[tuple[str, str]] = []
    for tokens in shell_segments(command):
        if not tokens:
            continue
        if os.path.basename(tokens[0]) == "cd":
            target = tokens[1] if len(tokens) > 1 and not tokens[1].startswith("-") else "~"
            if _NOT_A_PATH.search(target):
                cwd = None
            elif os.path.isabs(os.path.expanduser(target)):
                cwd = os.path.normpath(os.path.expanduser(target))
            elif cwd is not None:
                cwd = os.path.normpath(os.path.join(cwd, target))
            continue
        for path, kind in _segment_paths(tokens):
            if _NOT_A_PATH.search(path) or path in ("/dev/null", "-", "") or path.startswith("-"):
                continue
            expanded = os.path.expanduser(path)
            if not os.path.isabs(expanded):
                if cwd is None:
                    continue  # somewhere we cannot name
                expanded = os.path.join(cwd, expanded)
            rel = _relative(expanded, root)
            if (rel, kind) not in found:
                found.append((rel, kind))
    return found


def _segment_paths(tokens: list[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(tokens):
        if tokens[i] in (">", ">>", "&>", ">|") and i + 1 < len(tokens):
            out.append((tokens[i + 1], "write"))
            i += 2
            continue
        i += 1
    name = os.path.basename(tokens[0])
    args = []
    for j in range(1, len(tokens)):  # drop redirection operators, their descriptors (2>...) and targets (>&1)
        t, prev, nxt = tokens[j], tokens[j - 1], tokens[j + 1] if j + 1 < len(tokens) else ""
        if t in _REDIRECTS or (t in ("0", "1", "2") and nxt in _REDIRECTS) or prev in _REDIRECTS:
            continue
        args.append(t)
    plain = [a for a in args if not a.startswith("-") and a != ""]
    if name in ("tee", "touch"):
        out.extend((p, "write") for p in plain)
    elif name == "sed" and any(a == "-i" or a.startswith("-i") for a in args):
        script_given = "-e" in args
        files = plain[1:] if not script_given else [a for a in plain if a not in _sed_scripts(args)]
        out.extend((p, "write") for p in files)
    elif name in ("mv", "cp") and len(plain) >= 2:
        out.append((plain[-1], "write"))
        if name == "mv":
            out.extend((p, "delete") for p in plain[:-1])
    elif name == "rm":
        out.extend((p, "delete") for p in plain)
    return out


def _sed_scripts(args: list[str]) -> set[str]:
    return {args[i + 1] for i, a in enumerate(args) if a == "-e" and i + 1 < len(args)}


def _relative(path: str, root: Path) -> str:
    norm = os.path.normpath(path)
    base = os.path.normpath(str(root))
    if norm == base or norm.startswith(base + os.sep):
        rel = os.path.relpath(norm, base)
        return norm if nested_checkout(root, rel) else rel
    return norm


@lru_cache(maxsize=4096)
def _is_checkout(directory: str) -> bool:
    return os.path.exists(os.path.join(directory, ".git"))


def nested_checkout(root: Path, rel: str) -> bool:
    """True when a repo-relative path lies inside another git checkout below the root: a worktree
    under `.claude/worktrees/`, a vendored clone. Those files belong to that checkout, not this one,
    so they count as outside the repo (path only, no content)."""
    current = str(root)
    for part in rel.split("/")[:-1]:
        current = os.path.join(current, part)
        if _is_checkout(current):
            return True
    return False


def check_segments(command: str) -> list[str]:
    """The simple commands in a shell call that run a test or lint tool (pytest, npm test, cargo test,
    make, ...), as a shell would see them: a tool named inside a quoted string, such as a commit
    message that says which check passed, is text, not a command, and is never a check."""
    out: list[str] = []
    for tokens in shell_segments(command):
        words = list(tokens)
        while True:  # peel runner prefixes (`uv run`, `python -m`, ...) and their flags, in any order
            for prefix in RUNNER_PREFIXES:
                if tuple(words[: len(prefix)]) == prefix:
                    words = words[len(prefix) :]
                    break
            else:
                if words and words[0].startswith("-"):
                    words.pop(0)
                    continue
                break
        if words and _is_checker(os.path.basename(words[0]), words[1:]):
            out.append(" ".join(_without_redirections(tokens)))
    return out


def _without_redirections(tokens: list[str]) -> list[str]:
    """`pytest -q 2>&1` and `pytest -q > log` run the same check as `pytest -q`."""
    kept: list[str] = []
    skip = False
    for token in tokens:
        if skip:
            skip = False
        elif token in _REDIRECTS:
            skip = True
            if kept and kept[-1].isdigit():  # the file descriptor in front of the operator
                kept.pop()
        else:
            kept.append(token)
    return kept


def _is_checker(name: str, rest: list[str]) -> bool:
    if name in CHECKERS:
        return True
    if name in ("cargo", "go") and rest[:1] == ["test"]:
        return True
    if name in ("npm", "yarn", "pnpm"):
        scripts = ("test", "lint", "check", "typecheck")
        return rest[:1] == ["test"] or (rest[:1] == ["run"] and bool(rest[1:2]) and rest[1] in scripts)
    return name == "npx" and bool(rest[:1]) and rest[0] in ("jest", "vitest", "tsc", "eslint")
