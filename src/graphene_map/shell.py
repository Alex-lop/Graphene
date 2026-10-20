"""Reading a shell command: which files it writes.

No model is involved and nothing here needs a vendor: it is text a shell would parse.
``bash_written_paths`` is what the hook refuses a write with, before the write happens
(``gate.py``); ``shell_segments`` is what ``commits.py`` reads a `git commit` out of.
Deliberately incomplete: a script that opens a file itself is invisible here and is caught later, at
the boundary, by git.
"""

from __future__ import annotations

import os
import re
import shlex
from functools import lru_cache
from pathlib import Path

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


# a `<` or `>` that is text (inside quotes, or escaped), kept apart from a redirect until a token is a path
_MASK = {"<": "\ue000", ">": "\ue001"}
_UNMASK = str.maketrans({v: k for k, v in _MASK.items()})


def _unquoted_newlines_to_semicolons(text: str) -> str:
    """As bash reads it, outside quotes: each newline ends a command (`;`), and a `#` that starts a word is a
    comment to the end of its own line. shlex read a comment to the end of the whole command once the newlines
    were gone, so `# note\necho x > f` hid the write. A `<` or `>` inside quotes, or escaped, is masked
    (``_MASK``): `grep '>' f` writes nothing."""
    out: list[str] = []
    quote: str | None = None
    escaped = comment = False
    for ch in text:
        if comment:
            if ch == "\n":
                comment = False
                out.append(";")
            continue
        if escaped:
            escaped = False
            ch = _MASK.get(ch, ch)
        elif ch == "\\" and quote != "'":
            escaped = True
        elif quote:
            if ch == quote:
                quote = None
            else:
                ch = _MASK.get(ch, ch)
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#" and (not out or out[-1] in " \t;|&()"):
            comment = True
            continue
        elif ch == "\n":
            out.append(";")
            continue
        out.append(ch)
    return "".join(out)


def _segments(command: str) -> list[list[str]]:
    """``shell_segments`` with quoted `<` and `>` still masked: what the redirect reader needs."""
    text = _unquoted_newlines_to_semicolons(strip_heredocs(command))  # heredoc bodies first: an apostrophe
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)  # in one opens no quote
    lexer.whitespace_split = True
    lexer.commenters = ""  # comments went with their own lines, above
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


def shell_segments(command: str) -> list[list[str]]:
    """Token lists of each simple command, split on && || | ; & ( ) and unquoted newlines.

    Quotes are respected, so a `|` or an `rm` inside a grep pattern is not shell syntax.
    """
    return [[token.translate(_UNMASK) for token in segment] for segment in _segments(command)]


def bash_written_paths(command: str, root: Path) -> list[tuple[str, str]]:
    """(repo-relative path, "write" | "delete") for the obvious forms: > >> tee sed -i mv cp rm touch.

    Relative paths follow `cd` inside the command; after a `cd` to a directory that cannot be
    resolved (a variable, a glob) relative paths are dropped rather than guessed. Deliberately
    incomplete: anything else a shell command does to a file is invisible here.
    """
    cwd: str | None = os.path.normpath(str(root))
    found: list[tuple[str, str]] = []
    for tokens in _segments(command):  # a quoted `>` stays masked: text, never a redirect
        if not tokens:
            continue
        if os.path.basename(tokens[0]) == "cd":
            given = len(tokens) > 1 and not tokens[1].startswith("-")
            target = tokens[1].translate(_UNMASK) if given else "~"
            if _NOT_A_PATH.search(target):
                cwd = None
            elif os.path.isabs(os.path.expanduser(target)):
                cwd = os.path.normpath(os.path.expanduser(target))
            elif cwd is not None:
                cwd = os.path.normpath(os.path.join(cwd, target))
            continue
        for path, kind in _segment_paths(tokens):
            path = path.translate(_UNMASK)
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
