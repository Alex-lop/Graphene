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
_UNKNOWABLE = re.compile(r"[*?$`{}\[\]]")  # a glob, a variable, a command substitution, a brace list
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_SEPARATORS = re.compile(r"&&|\|\||;|\||\n")
_VAR = re.compile(r"\$\{(\w+)\}|\$(\w+)")
_WRITE_OPS = (">", ">>", "&>", ">|", "&>>", "<>")  # the next token is a file this writes
_REDIRECTS = (">", ">>", "&>", ">|", "&>>", "<>", "<", "<<", "<&", ">&")  # any redirection operator
_WRAPPERS = ("sudo", "env", "time", "command", "builtin", "exec", "nohup", "nice")
_SEPARATOR_TOKENS = ("&&", "||", "|", "|&", ";", "&", ";;")
_PUNCT = re.compile(r"[();&|<>]+")  # a token that is only operator characters: shlex glues `);` into one
_OPERATORS = re.compile(r"&&|\|\||;;|\|&|&>>|&>|>>|>\||>&|<&|<<-?|<>|[();&|<>]")


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


def _is_assignment(token: str) -> bool:
    """A leading `NAME=value` word, which sets an environment variable rather than names a command."""
    name = token.partition("=")[0]
    return "=" in token and not token.startswith("-") and name.isidentifier()


def _strip_wrappers(tokens: list[str]) -> list[str]:
    while tokens and (_is_assignment(tokens[0]) or tokens[0] in _WRAPPERS):
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


def _split(command: str) -> list[list[str]]:
    """Token lists of each simple command, split on the separators, with quoted `<` and `>` still
    masked and the leading wrappers (`NAME=value`, sudo, command, …) still on: what reads a redirect,
    and what captures a `NAME=value` set in one command and used in the next."""
    text = _unquoted_newlines_to_semicolons(strip_heredocs(command))  # heredoc bodies first: an apostrophe
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)  # in one opens no quote
    lexer.whitespace_split = True
    lexer.commenters = ""  # comments went with their own lines, above
    segments: list[list[str]] = [[]]
    try:
        for glued in lexer:
            # shlex glues a run of operators into one token: `);` is `)` then `;`, `>>|` is `>>` then `|`
            for token in _OPERATORS.findall(glued) if _PUNCT.fullmatch(glued) else [glued]:
                if token in _SEPARATOR_TOKENS:
                    segments.append([])  # `|&` pipes stdout and stderr both: a separator, like `|`
                elif token in ("(", ")"):
                    segments.append([token])  # a subshell boundary: its own cd ends at its `)`
                    segments.append([])
                else:
                    segments[-1].append(token)
    except ValueError:  # unbalanced quotes: fall back to a crude split
        segments = [segment.split() for segment in _SEPARATORS.split(text)]
    return segments


def _segments(command: str) -> list[list[str]]:
    """``shell_segments`` with quoted `<` and `>` still masked: what the redirect reader needs."""
    return [_strip_wrappers(segment) for segment in _split(command) if segment]


def shell_segments(command: str) -> list[list[str]]:
    """Token lists of each simple command, split on && || | ; & ( ) and unquoted newlines.

    Quotes are respected, so a `|` or an `rm` inside a grep pattern is not shell syntax.
    """
    return [[token.translate(_UNMASK) for token in segment] for segment in _segments(command)]


def _resolve(token: str, cwd: str | None, assigns: dict[str, str]) -> str:
    """The expansions the hook can know before bash runs: `$PWD` (the cwd), `$HOME` (the home), and a
    variable this command set to a literal earlier. What is left — another variable, a glob, a command
    substitution (`$(…)`, which shlex splits on its parens, or a backtick) — stays, and
    ``bash_written_paths`` marks the write "unknown"."""

    def repl(m: re.Match) -> str:
        name = m.group(1) or m.group(2)
        if name == "PWD" and cwd:
            return cwd
        if name == "HOME":
            return os.path.expanduser("~")
        return assigns.get(name, m.group(0))

    return _VAR.sub(repl, token)


def bash_written_paths(command: str, root: Path) -> list[tuple[str, str]]:
    """(repo-relative path, kind) for the obvious forms: > >> >| &> &>> <> >& tee dd mv cp install
    rm touch sed -i. ``kind`` is "write", "delete", or "unknown" for a write target the hook cannot
    know before bash runs (a variable it was not given, a glob, a command substitution): the gate
    refuses that one while a leaf is held, since it cannot be checked against the scope.

    Relative paths follow `cd` inside the command; after a `cd` to a directory that cannot be
    resolved (a variable, a glob) relative paths are dropped rather than guessed. Deliberately
    incomplete: anything else a shell command does to a file is invisible here.
    """
    cwd: str | None = os.path.normpath(str(root))
    stack: list[str | None] = []  # the cwd outside each open subshell: its `cd` ends at its `)`
    previous: str | None = cwd  # where `cd -` goes back to
    assigns: dict[str, str] = {}
    found: list[tuple[str, str]] = []
    for raw in _split(command):  # a quoted `>` stays masked: text, never a redirect
        if raw == ["("]:
            stack.append(cwd)
            continue
        if raw == [")"]:
            cwd = stack.pop() if stack else cwd  # the subshell's cd is undone
            continue
        tokens = list(raw)
        while tokens and _is_assignment(tokens[0].translate(_UNMASK)):
            name, _, value = tokens.pop(0).translate(_UNMASK).partition("=")
            assigns[name] = value  # used by a later command: `F=path; echo x > $F`
        tokens = _strip_wrappers(tokens)
        if not tokens:
            continue
        if os.path.basename(tokens[0].translate(_UNMASK)) in ("cd", "pushd", "popd"):
            cwd, previous = _follow_cd(tokens, cwd, previous, assigns)
            continue
        for path, kind in _segment_paths(tokens):
            resolved = _resolve(path.translate(_UNMASK), cwd, assigns)
            if _UNKNOWABLE.search(resolved):  # a glob, a variable or a substitution still in it
                if kind == "write" and (path.translate(_UNMASK), "unknown") not in found:
                    found.append((path.translate(_UNMASK), "unknown"))
                continue  # a delete of one is dropped, as a target that cannot be named always was
            if resolved in ("/dev/null", "-", "") or resolved.startswith("-"):
                continue
            expanded = os.path.expanduser(resolved)
            if not os.path.isabs(expanded):
                if cwd is None:
                    continue  # somewhere we cannot name
                expanded = os.path.join(cwd, expanded)
            rel = _relative(expanded, root)
            if (rel, kind) not in found:
                found.append((rel, kind))
    return found


def _args(tokens: list[str]) -> list[str]:
    """A command's arguments with the redirections dropped: an operator, a fd before one (`2>`), and
    the target after one are not arguments of the command itself."""
    args = []
    for j in range(1, len(tokens)):
        t, prev, nxt = tokens[j], tokens[j - 1], tokens[j + 1] if j + 1 < len(tokens) else ""
        if t in _REDIRECTS or (t.isdigit() and nxt in _REDIRECTS) or prev in _REDIRECTS:
            continue
        args.append(t)
    return args


def _follow_cd(
    tokens: list[str], cwd: str | None, previous: str | None, assigns: dict[str, str]
) -> tuple[str | None, str | None]:
    """Where a `cd`, `pushd` or `popd` leaves the cwd, and the directory a later `cd -` returns to.
    Flags (`-P`, `--`) are skipped; `cd -`, `popd` and a bare `pushd` go back to the previous
    directory; `$PWD` and a variable the command set resolve; a target that cannot be resolved loses
    the cwd (None), so relative paths after it are dropped rather than guessed."""
    verb = os.path.basename(tokens[0].translate(_UNMASK))
    words = [a.translate(_UNMASK) for a in _args(tokens) if a == "-" or not a.startswith("-")]
    target = words[0] if words else ("~" if verb == "cd" else "-")
    if target == "-":
        return previous, cwd  # swap: the previous directory, and this one becomes the new previous
    target = _resolve(target, cwd, assigns)
    was = cwd
    if _NOT_A_PATH.search(target):
        cwd = None
    elif os.path.isabs(os.path.expanduser(target)):
        cwd = os.path.normpath(os.path.expanduser(target))
    elif cwd is not None:
        cwd = os.path.normpath(os.path.join(cwd, target))
    return cwd, was


def _segment_paths(tokens: list[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        # `>&word` writes word, the same as `&>word`; `>&1`, `>&2`, `>&-` duplicate or close a fd
        if nxt and (t in _WRITE_OPS or (t == ">&" and not (nxt == "-" or nxt.isdigit()))):
            out.append((nxt, "write"))
            i += 2
            continue
        i += 1
    name = os.path.basename(tokens[0])
    args = _args(tokens)
    plain = [a for a in args if not a.startswith("-") and a != ""]
    if name in ("tee", "touch"):
        out.extend((p, "write") for p in plain)
    elif name == "dd":
        out.extend((a[3:], "write") for a in args if a.startswith("of="))
    elif name == "sed" and any(a == "-i" or a.startswith("-i") for a in args):
        script_given = "-e" in args
        files = plain[1:] if not script_given else [a for a in plain if a not in _sed_scripts(args)]
        out.extend((p, "write") for p in files)
    elif name in ("mv", "cp", "install") and len(plain) >= 2:
        out.append((plain[-1], "write"))  # the destination, last; install copies, it does not delete
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
