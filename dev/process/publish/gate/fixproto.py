# ruff: noqa  (a reviewer's prototype, kept as evidence for a follow-up: not the product's code)
"""A prototype of the smallest fixes for findings 1, 5 and 6, applied by monkeypatching graphene_map.shell
(the repo is not touched): quoted or escaped `<`, `>` and `#` are masked before the heredoc scan and the
lexer and unmasked only when a token is taken as a path; an unquoted `#` is a comment to the end of ITS
line; a subshell's cd ends at `)`; cd's flags, `--` and `-` are read as bash reads them. Then the
parser's own cases (tests/test_shell.py) and the probes run again."""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

from graphene_map import shell

MASK = {"<": "", ">": "", "#": ""}
UNMASK = str.maketrans({v: k for k, v in MASK.items()})


def _mask_quoted(text: str) -> str:
    """`<`, `>` and `#` inside quotes, or escaped, are text, not syntax: masked so no later step reads them."""
    out, quote, escaped = [], None, False
    for ch in text:
        if escaped:
            escaped = False
            out.append(MASK.get(ch, ch))
        elif ch == "\\" and quote != "'":
            escaped = True
            out.append(ch)
        elif quote:
            if ch == quote:
                quote = None
                out.append(ch)
            else:
                out.append(MASK.get(ch, ch))
        elif ch in ("'", '"'):
            quote = ch
            out.append(ch)
        else:
            out.append(ch)
    return "".join(out)


_COMMENT = re.compile(r"(?:^|(?<=[\s;|&(]))#[^\n]*")
_PUNCT = re.compile(r"[();&|<>]+")
_OPERATORS = re.compile(r"&&|\|\||;;|\|&|&>>|&>|>>|>\||>&|<&|<<-?|<>|[();&|<>]")


def strip_comments(text: str) -> str:
    """An unquoted `#` that starts a word comments out the rest of its line, as bash reads it."""
    return _COMMENT.sub("", text)


def shell_segments(command: str) -> list[list[str]]:
    """As before, but tokens keep the mask: a quoted `>` is never a redirect. Paths are unmasked by the caller."""
    masked = strip_comments(_mask_quoted(command))
    text = shell._unquoted_newlines_to_semicolons(shell.strip_heredocs(masked))
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""  # comments were stripped above, with their lines, not the whole command
    segments: list[list[str]] = [[]]
    try:
        for glued in lexer:
            # shlex glues a run of punctuation into one token: `);` is `)` then `;`, `>>|` is `>>` then `|`
            pieces = _OPERATORS.findall(glued) if _PUNCT.fullmatch(glued) else [glued]
            for token in pieces:
                if token in ("&&", "||", "|", ";", "&", ";;", "|&"):
                    segments.append([])
                elif token in ("(", ")"):
                    segments.append([token])  # kept: a subshell's cd ends at its `)`
                    segments.append([])
                else:
                    segments[-1].append(token)
    except ValueError:
        segments = [segment.split() for segment in shell._SEPARATORS.split(text)]
    return [shell._strip_wrappers(segment) for segment in segments if segment]


def bash_written_paths(command: str, root: Path) -> list[tuple[str, str]]:
    cwd: str | None = os.path.normpath(str(root))
    stack: list[str | None] = []  # the cwd outside each open subshell
    previous: str | None = cwd  # what `cd -` goes back to
    found: list[tuple[str, str]] = []
    for tokens in shell_segments(command):
        if not tokens:
            continue
        if tokens == ["("]:
            stack.append(cwd)
            continue
        if tokens == [")"]:
            cwd = stack.pop() if stack else cwd
            continue
        if os.path.basename(tokens[0]) in ("cd", "pushd"):
            words = [t for t in tokens[1:] if t == "-" or not t.startswith("-")]  # flags and `--` are not the target
            target = words[0].translate(UNMASK) if words else "~"
            was = cwd
            if target == "-":
                cwd = previous
            else:
                if target.startswith(("$PWD", "$(pwd)")) and was is not None:
                    target = was + target.removeprefix("$PWD").removeprefix("$(pwd)")
                if shell._NOT_A_PATH.search(target):
                    cwd = None
                elif os.path.isabs(os.path.expanduser(target)):
                    cwd = os.path.normpath(os.path.expanduser(target))
                elif cwd is not None:
                    cwd = os.path.normpath(os.path.join(cwd, target))
            previous = was
            continue
        for path, kind in shell._segment_paths(tokens):
            path = path.translate(UNMASK)
            if shell._NOT_A_PATH.search(path) or path in ("/dev/null", "-", "") or path.startswith("-"):
                continue
            expanded = os.path.expanduser(path)
            if not os.path.isabs(expanded):
                if cwd is None:
                    continue
                expanded = os.path.join(cwd, expanded)
            rel = shell._relative(expanded, root)
            if (rel, kind) not in found:
                found.append((rel, kind))
    return found


_before: dict = {}


def install():
    shell.shell_segments = shell_segments
    shell.bash_written_paths = bash_written_paths


def main():
    root = Path("/tmp/probe-root")
    before = {}
    cases = [
        # tests/test_shell.py's own cases
        ("echo hi > notes.txt", [("notes.txt", "write")]),
        ("cat <<'EOF' >> log/out.txt\nx\nEOF", [("log/out.txt", "write")]),
        ("sed -i '' 's/a/b/' src/x.py", [("src/x.py", "write")]),
        ("sed -i -e 's/a/b/' one.py two.py", [("one.py", "write"), ("two.py", "write")]),
        ("mv old.py new.py", [("new.py", "write"), ("old.py", "delete")]),
        ("rm -rf build dist/", [("build", "delete"), ("dist", "delete")]),
        ("tee -a a.log", [("a.log", "write")]),
        ("cp a.txt b.txt && touch c.txt", [("b.txt", "write"), ("c.txt", "write")]),
        ("ls 2>/dev/null > /dev/null", []),
        ("git status", []),
        (f"echo x > {root}/abs.txt", [("abs.txt", "write")]),
        ("echo x > /elsewhere/abs.txt", [("/elsewhere/abs.txt", "write")]),
        ("echo x > $HOME/y.txt", []),
        ("cat > out.py <<'EOF'\nif len(v) > 4096:\n    x = a > CONTENT_CAP\nEOF\necho done", [("out.py", "write")]),
        ("python - <<EOF\nprint(1 > 0)\nEOF", []),
        ("cd sub && echo hi > a.txt", [("sub/a.txt", "write")]),
        ("cd /elsewhere && echo x > a.txt", [("/elsewhere/a.txt", "write")]),
        ("cd sub && cd .. && echo x > b.txt", [("b.txt", "write")]),
        ('grep -n "directory\\|rm -rf" docs/x.md | head -40', []),
        ("echo 'a; rm -rf b' > note.txt", [("note.txt", "write")]),
        ('cd "$T" && echo x > f.txt && rm g.txt', []),
        ('cd "$T" && echo x > /abs/f.txt', [("/abs/f.txt", "write")]),
        ("echo hi >notes.txt 2>/dev/null", [("notes.txt", "write")]),
        ("echo hi > a.txt\necho yo > b.txt", [("a.txt", "write"), ("b.txt", "write")]),
        ("printf 'x\\ny' > c.txt", [("c.txt", "write")]),
        ("cd sub; cd ..; echo > d.txt", [("d.txt", "write")]),
        ("(cd sub && echo > e.txt)", [("sub/e.txt", "write")]),
        ("rm -f x.txt 2>/dev/null", [("x.txt", "delete")]),
        ("rm -f y.txt 2>&1", [("y.txt", "delete")]),
        ("mv a.txt b.txt 1>log.txt", [("log.txt", "write"), ("b.txt", "write"), ("a.txt", "delete")]),
        # finding 1: comments and quoted markers
        ("# update the schema\necho x > src/db/schema.py", [("src/db/schema.py", "write")]),
        ("ls # list first\necho x > src/db/schema.py", [("src/db/schema.py", "write")]),
        ("# write it\ncat > src/db/schema.py <<'EOF'\nTABLES = ['x']\nEOF", [("src/db/schema.py", "write")]),
        ("echo https://example.com/#top\necho x > src/db/schema.py", [("src/db/schema.py", "write")]),
        ("x=abc; echo ${#x} > src/db/schema.py", [("src/db/schema.py", "write")]),
        ("echo '<<EOF'\necho x > src/db/schema.py", [("src/db/schema.py", "write")]),
        ("echo x > src/db/schema.py # a comment > src/api/users.py", [("src/db/schema.py", "write")]),
        ("echo 'it#s' > src/db/schema.py", [("src/db/schema.py", "write")]),
        ("echo x > 'src/db/#1.py'", [("src/db/#1.py", "write")]),
        # finding 6: a quoted `>` is text
        ("grep -n '>' src/db/schema.py", []),
        ("rg -n '>>' src", []),
        ("grep -rn '>' .", []),
        ("git grep -n '>' src/db", []),
        ("echo '>' > src/api/users.py", [("src/api/users.py", "write")]),
        ("echo a \\> b > src/api/users.py", [("src/api/users.py", "write")]),
        # finding 5: cd
        ("cd -P src/db && echo x > schema.py", [("src/db/schema.py", "write")]),
        ("cd -- src/db && echo x > schema.py", [("src/db/schema.py", "write")]),
        ("cd src/api && cd - >/dev/null && echo x > src/db/schema.py", [("src/db/schema.py", "write")]),
        ("cd $PWD/src/db && echo x > schema.py", [("src/db/schema.py", "write")]),
        ("(cd src/api); echo x > src/db/schema.py", [("src/db/schema.py", "write")]),
        ("(cd src/api && pwd >/dev/null) && echo x > src/db/schema.py", [("src/db/schema.py", "write")]),
        ("(cd src && ls >/dev/null) && echo x > src/api/users.py", [("src/api/users.py", "write")]),
        ("pushd src/api >/dev/null && echo x > users.py", [("src/api/users.py", "write")]),
    ]
    for command, _ in cases:
        before[command] = shell.bash_written_paths(command, root)
    install()
    bad = 0
    for command, expected in cases:
        after = shell.bash_written_paths(command, root)
        mark = "ok " if after == expected else "BAD"
        bad += after != expected
        flag = "" if before[command] == after else f"   (was {before[command]})"
        print(f"{mark} {command!r:75.75} -> {after}{flag}")
    print(f"\n{len(cases)} cases, {bad} wrong after the prototype")


if __name__ == "__main__":
    main()
