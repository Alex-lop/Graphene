"""Deterministic shell-command classification, `classify.v1`.

Heuristic in one line: tokenize the command text, split it into simple
commands, look each program up in a fixed table, and keep the highest-priority
kind. In detail:

- Tokenizing: control characters are dropped, heredoc bodies are removed,
  backslash line continuations are joined, unquoted shell operators are marked
  so quoting survives, then ``shlex`` (POSIX) splits the words. On a shlex
  error (for example an unbalanced quote) the text is split on whitespace
  instead, with operators marked quote-blind.
- Splitting: ``&&``, ``||``, ``;``, ``|``, ``&``, parentheses, and newlines
  separate simple commands. A leading ``cd X``, ``env``, ``time``, ``sudo``,
  and ``VAR=value`` assignments are skipped when locating the program.
  ``python -m X``, ``uv run X``, ``poetry run X``, ``pipx run X``, ``npx X``,
  ``uvx X``, and ``pnpm exec X`` resolve to ``X``.
- Kinds: recognized runners give ``check_run`` with a check family; package
  installers give ``install_op``; network clients and ``git clone|fetch|pull``
  give ``network_op``; mutating ``git`` subcommands give ``vcs_op``; anything
  else is ``command_exec``. A compound command takes the highest-priority kind
  (check_run > install_op > network_op > vcs_op > command_exec) and the family
  of the first check found.
- File operations are inferred from ``rm``, ``mv``, ``cp``, ``touch``,
  ``sed -i``, ``tee``, and output redirections (``>``, ``>>``, ``1>``, ``2>``,
  ``&>``). Flags, globs, ``/dev/*``, empty words, file-descriptor duplications
  (``2>&1``), ``mv``/``cp`` targets with a trailing slash, and unexpanded ``$``
  or backtick substitutions are never taken as paths.

Everything here is inference over observed text; the caller labels it so.
"""

from __future__ import annotations

import re
import shlex
from typing import Literal, NamedTuple

CLASSIFY_VERSION = "classify.v1"

CommandKind = Literal["command_exec", "check_run", "vcs_op", "network_op", "install_op"]
FileOpKind = Literal["file_edit", "file_create", "file_delete"]


class FileOp(NamedTuple):
    kind: FileOpKind
    raw_path: str


class CommandClassification(NamedTuple):
    kind: CommandKind
    check_family: str | None
    file_ops: tuple[FileOp, ...]


_PRIORITY: dict[str, int] = {
    "command_exec": 0,
    "vcs_op": 1,
    "network_op": 2,
    "install_op": 3,
    "check_run": 4,
}

# -- tokenizing ---------------------------------------------------------------

# A private-use code point: not whitespace for shlex or str.split, never typed in
# a real command, and scrubbed from the input so it cannot be forged.
_SENTINEL = "\ue000"
_OPERATOR_CHARS = frozenset("();<>|&\n")
_DIGITS = frozenset("0123456789")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ue000]")
_CONTINUATION = re.compile(r"\\\r?\n")
_HEREDOC = re.compile(
    r"(?<!<)<<(?!<)-?[ \t]*(?:'([^'\n]+)'|\"([^\"\n]+)\"|([^\s'\"<>|&;()]+))"
)
_REDIRECT = re.compile(r"^&?>{1,2}[&|]?$")


def _strip_heredocs(text: str) -> str:
    """Drop heredoc bodies: they are content being written, not commands."""

    while (match := _HEREDOC.search(text)) is not None:
        delimiter = match.group(1) or match.group(2) or match.group(3)
        head = text[: match.start()] + " "
        line_end = text.find("\n", match.end())
        if line_end < 0:
            text = head + text[match.end() :]
            continue
        lines = text[line_end + 1 :].split("\n")
        tail = ""
        for count, line in enumerate(lines, start=1):
            if line.strip() == delimiter:
                tail = "\n".join(lines[count:])
                break
        text = head + text[match.end() : line_end + 1] + tail
    return text


def _mark_operators(text: str, *, quote_aware: bool) -> str:
    """Wrap unquoted operator runs in sentinels so quoting survives shlex.

    A single digit glued to a redirection (``2>``) is a file descriptor and is
    dropped so it is not mistaken for an argument.
    """

    out: list[str] = []
    quote: str | None = None
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if quote is not None:
            if quote == '"' and char == "\\" and index + 1 < length:
                out.append(text[index : index + 2])
                index += 2
                continue
            if char == quote:
                quote = None
            out.append(char)
            index += 1
            continue
        if quote_aware and char == "\\" and index + 1 < length:
            out.append(text[index : index + 2])
            index += 2
            continue
        if quote_aware and char in "'\"":
            quote = char
            out.append(char)
            index += 1
            continue
        if (
            char in _DIGITS
            and index + 1 < length
            and text[index + 1] in "<>"
            and (
                index == 0
                or text[index - 1] in " \t\r"
                or text[index - 1] in _OPERATOR_CHARS
            )
        ):
            index += 1
            continue
        if char in _OPERATOR_CHARS:
            end = index
            while end < length and text[end] in _OPERATOR_CHARS:
                end += 1
            # Newlines separate commands but are whitespace to shlex; `;` is not.
            run = text[index:end].replace("\n", ";")
            out.append(f" {_SENTINEL}{run}{_SENTINEL} ")
            index = end
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _tokenize(command: str) -> list[str]:
    text = _CONTINUATION.sub(" ", _strip_heredocs(_CONTROL.sub("", command)))
    try:
        return shlex.split(_mark_operators(text, quote_aware=True))
    except ValueError:
        return _mark_operators(text, quote_aware=False).split()


def _operator(token: str) -> str | None:
    if len(token) >= 3 and token[0] == _SENTINEL and token[-1] == _SENTINEL:
        return token[1:-1]
    return None


def _is_path(token: str) -> bool:
    if not token or token.startswith("-") or token.startswith("/dev/"):
        return False
    return not any(char in token for char in "*?[$`")


def _split_commands(tokens: list[str]) -> list[tuple[list[str], list[FileOp]]]:
    """Simple commands with the file operations implied by their redirections."""

    commands: list[tuple[list[str], list[FileOp]]] = []
    argv: list[str] = []
    redirects: list[FileOp] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        operator = _operator(token)
        if operator is None:
            argv.append(token)
            continue
        if _REDIRECT.match(operator) or operator.startswith("<"):
            if index < len(tokens) and _operator(tokens[index]) is None:
                target = tokens[index]
                index += 1
                if operator.startswith("<"):
                    continue
                if operator.endswith("&") and target.isdigit():
                    continue
                if _is_path(target):
                    appends = ">>" in operator
                    redirects.append(
                        FileOp("file_edit" if appends else "file_create", target)
                    )
            continue
        if argv or redirects:
            commands.append((argv, redirects))
            argv, redirects = [], []
    if argv or redirects:
        commands.append((argv, redirects))
    return commands


# -- program resolution ---------------------------------------------------------

_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_PYTHON = re.compile(r"^python(\d+(\.\d+)?)?$")
_WRAPPERS = frozenset({"env", "time", "sudo"})
_WRAPPER_VALUE_FLAGS = frozenset({"-u", "-g", "-C", "-f", "-o"})
_RUNNER_SUBCOMMANDS: dict[str, frozenset[str]] = {
    "uv": frozenset({"run"}),
    "poetry": frozenset({"run"}),
    "pipx": frozenset({"run"}),
    "pnpm": frozenset({"exec", "dlx"}),
}
_DIRECT_RUNNERS = frozenset({"npx", "uvx"})
_RUNNER_VALUE_FLAGS = frozenset(
    {
        "-p",
        "-c",
        "--python",
        "--with",
        "--with-editable",
        "--with-requirements",
        "--directory",
        "--project",
        "--package",
        "--group",
        "--only-group",
        "--no-group",
        "--extra",
        "--env-file",
        "--spec",
    }
)
_PYTHON_VALUE_FLAGS = frozenset({"-X", "-W"})


def _program_name(token: str) -> str:
    name = token.rsplit("/", 1)[-1]
    if _PYTHON.match(name):
        return "python"
    if name == "pip3":
        return "pip"
    if name == "py.test":
        return "pytest"
    return name


def _positionals(
    args: list[str], value_flags: frozenset[str] = frozenset()
) -> list[str]:
    """Non-flag arguments, skipping the values of known value-taking flags."""

    out: list[str] = []
    skip = False
    for token in args:
        if skip:
            skip = False
            continue
        if token in value_flags:
            skip = True
            continue
        if not token or token.startswith("-"):
            continue
        out.append(token)
    return out


def _skip_flags(args: list[str], value_flags: frozenset[str]) -> list[str]:
    index = 0
    while index < len(args) and args[index].startswith("-"):
        index += 2 if args[index] in value_flags else 1
    return args[index:]


def _strip_prefixes(argv: list[str]) -> list[str]:
    """Drop leading ``cd X``, ``env``, ``time``, ``sudo``, and assignments."""

    index = 0
    while index < len(argv):
        token = argv[index]
        if _ASSIGNMENT.match(token):
            index += 1
            continue
        name = _program_name(token)
        if name in _WRAPPERS:
            index += 1
            while index < len(argv) and argv[index].startswith("-"):
                index += 2 if argv[index] in _WRAPPER_VALUE_FLAGS else 1
            continue
        if name == "cd":
            index += 2
            continue
        break
    return argv[index:]


def _python_module(args: list[str]) -> tuple[str, list[str]] | None:
    index = 0
    while index < len(args):
        token = args[index]
        if token == "-m":
            if index + 1 < len(args):
                return args[index + 1], args[index + 2 :]
            return None
        if token.startswith("-m") and len(token) > 2:
            return token[2:], args[index + 1 :]
        if token in _PYTHON_VALUE_FLAGS:
            index += 2
            continue
        if token == "-c" or not token.startswith("-"):
            return None
        index += 1
    return None


def _resolve(program: str, args: list[str]) -> tuple[str, list[str]]:
    """Follow ``python -m`` and runner prefixes to the effective program."""

    for _ in range(4):
        if program == "python":
            module = _python_module(args)
            if module is None:
                return program, args
            program, args = _program_name(module[0]), module[1]
            continue
        rest = args
        subcommands = _RUNNER_SUBCOMMANDS.get(program)
        if subcommands is not None:
            if not args or args[0] not in subcommands:
                return program, args
            rest = args[1:]
        elif program not in _DIRECT_RUNNERS:
            return program, args
        rest = _skip_flags(rest, _RUNNER_VALUE_FLAGS)
        if not rest:
            return program, args
        program, args = _program_name(rest[0]), rest[1:]
    return program, args


# -- kinds ----------------------------------------------------------------------

_SIMPLE_FAMILIES: dict[str, str] = {
    "pytest": "pytest",
    "unittest": "python-unittest",
    "compileall": "compileall",
    "jest": "jest",
    "vitest": "vitest",
    "mypy": "mypy",
    "pyright": "pyright",
    "eslint": "eslint",
    "tsc": "tsc",
    "flake8": "flake8",
}
_SCRIPT_RUNNERS: dict[str, str] = {
    "npm": "npm-test",
    "yarn": "yarn-test",
    "pnpm": "pnpm-test",
}
_INSTALL_SUBCOMMANDS: dict[str, frozenset[str]] = {
    "pip": frozenset({"install"}),
    "pipx": frozenset({"install"}),
    "poetry": frozenset({"add", "install"}),
    "npm": frozenset({"install", "i", "ci", "add"}),
    "yarn": frozenset({"add", "install"}),
    "pnpm": frozenset({"add", "install", "i"}),
    "brew": frozenset({"install"}),
    "apt": frozenset({"install"}),
    "apt-get": frozenset({"install"}),
    "cargo": frozenset({"add", "install"}),
    "go": frozenset({"get", "install"}),
    "gem": frozenset({"install"}),
    "conda": frozenset({"install"}),
}
_NETWORK_PROGRAMS = frozenset(
    {
        "curl",
        "wget",
        "http",
        "https",
        "httpie",
        "ssh",
        "scp",
        "sftp",
        "rsync",
        "nc",
        "ncat",
        "telnet",
        "ping",
        "dig",
        "nslookup",
        "gh",
    }
)
_GIT_VALUE_FLAGS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})
_GIT_NETWORK = frozenset({"clone", "fetch", "pull"})
_GIT_VCS = frozenset(
    {
        "commit",
        "push",
        "checkout",
        "switch",
        "reset",
        "rebase",
        "stash",
        "merge",
        "cherry-pick",
        "tag",
        "am",
        "restore",
        "clean",
        "rm",
        "mv",
        "add",
    }
)
_GIT_BRANCH_DELETE = frozenset({"-d", "-D", "--delete"})


def _is_test_script(name: str | None) -> bool:
    return name is not None and (name == "test" or name.startswith("test:"))


def _check_family(program: str, args: list[str]) -> str | None:
    family = _SIMPLE_FAMILIES.get(program)
    if family is not None:
        return family
    positional = _positionals(args)
    head = positional[0] if positional else None
    second = positional[1] if len(positional) > 1 else None
    if program in _SCRIPT_RUNNERS:
        if head in {"test", "t", "tst"}:
            return _SCRIPT_RUNNERS[program]
        if head in {"run", "run-script"} and _is_test_script(second):
            return _SCRIPT_RUNNERS[program]
        return None
    if program == "node":
        return "node-test" if "--test" in args else None
    if program == "go":
        return "go-test" if head == "test" else None
    if program == "cargo":
        return "cargo-test" if head == "test" else None
    if program == "make":
        targets = {"test", "check"}
        return "make-test" if any(target in targets for target in positional) else None
    if program == "ruff":
        if head == "check" or (head == "format" and "--check" in args):
            return "ruff"
        return None
    if program == "black":
        return "black" if "--check" in args else None
    return None


def _is_install(program: str, args: list[str]) -> bool:
    positional = _positionals(args)
    head = positional[0] if positional else None
    if program == "uv":
        if head in {"add", "sync"}:
            return True
        second = positional[1] if len(positional) > 1 else None
        return head in {"pip", "tool"} and second == "install"
    subcommands = _INSTALL_SUBCOMMANDS.get(program)
    return subcommands is not None and head in subcommands


def _git_kind(args: list[str]) -> CommandKind:
    positional = _positionals(args, _GIT_VALUE_FLAGS)
    subcommand = positional[0] if positional else None
    if subcommand in _GIT_NETWORK:
        return "network_op"
    if subcommand in _GIT_VCS:
        return "vcs_op"
    if subcommand == "branch" and any(flag in _GIT_BRANCH_DELETE for flag in args):
        return "vcs_op"
    return "command_exec"


def _simple_kind(argv: list[str]) -> tuple[CommandKind, str | None]:
    if not argv:
        return "command_exec", None
    program, args = _resolve(_program_name(argv[0]), argv[1:])
    family = _check_family(program, args)
    if family is not None:
        return "check_run", family
    if _is_install(program, args):
        return "install_op", None
    if program == "git":
        return _git_kind(args), None
    if program in _NETWORK_PROGRAMS:
        return "network_op", None
    return "command_exec", None


# -- inferred file operations ---------------------------------------------------

_TARGET_DIR_FLAGS = frozenset({"-t", "--target-directory"})
_SED_VALUE_FLAGS = frozenset(
    {"-e", "--expression", "-f", "--file", "-l", "--line-length"}
)
_SED_SCRIPT_FLAGS = frozenset({"-e", "--expression", "-f", "--file"})
_SED_IN_PLACE = re.compile(r"^-[A-Za-z]*i")
_SED_SCRIPT_CLUSTER = re.compile(r"^-[A-Za-z]*[ef]$")


def _paths(args: list[str], value_flags: frozenset[str] = frozenset()) -> list[str]:
    return [token for token in _positionals(args, value_flags) if _is_path(token)]


def _move_or_copy_ops(program: str, args: list[str]) -> list[FileOp]:
    positional = _positionals(args, _TARGET_DIR_FLAGS)
    targeted = any(
        token in _TARGET_DIR_FLAGS or token.startswith("--target-directory=")
        for token in args
    )
    if targeted:
        sources, destination = positional, None
    elif len(positional) >= 2:
        sources, destination = positional[:-1], positional[-1]
    else:
        return []
    ops: list[FileOp] = []
    if program == "mv":
        ops.extend(
            FileOp("file_delete", source) for source in sources if _is_path(source)
        )
    if destination is None or destination.endswith("/"):
        return ops
    if _is_path(destination):
        ops.append(FileOp("file_create", destination))
    return ops


def _sed_targets(args: list[str]) -> list[str]:
    in_place = False
    script_given = False
    positional: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        index += 1
        if not token.startswith("-"):
            if token:
                positional.append(token)
            continue
        if token.startswith("--in-place") or _SED_IN_PLACE.match(token):
            in_place = True
        if token.startswith(("--expression=", "--file=")):
            script_given = True
            continue
        if token in _SED_SCRIPT_FLAGS or _SED_SCRIPT_CLUSTER.match(token):
            script_given = True
            index += 1
        elif token in _SED_VALUE_FLAGS:
            index += 1
    if not in_place:
        return []
    files = positional if script_given else positional[1:]
    return [token for token in files if _is_path(token)]


def _argv_file_ops(argv: list[str]) -> list[FileOp]:
    if not argv:
        return []
    program, args = _program_name(argv[0]), argv[1:]
    if program == "rm":
        return [FileOp("file_delete", path) for path in _paths(args)]
    if program == "touch":
        return [FileOp("file_create", path) for path in _paths(args)]
    if program == "tee":
        return [FileOp("file_edit", path) for path in _paths(args)]
    if program in {"mv", "cp"}:
        return _move_or_copy_ops(program, args)
    if program == "sed":
        return [FileOp("file_edit", path) for path in _sed_targets(args)]
    return []


# -- entry point ----------------------------------------------------------------


def classify_command(command: str) -> CommandClassification:
    """Classify one shell command text; see the module docstring for the rules."""

    kind: CommandKind = "command_exec"
    family: str | None = None
    file_ops: list[FileOp] = []
    for argv, redirects in _split_commands(_tokenize(command)):
        stripped = _strip_prefixes(argv)
        simple_kind, simple_family = _simple_kind(stripped)
        if _PRIORITY[simple_kind] > _PRIORITY[kind]:
            kind = simple_kind
        if family is None and simple_family is not None:
            family = simple_family
        file_ops.extend(_argv_file_ops(stripped))
        file_ops.extend(redirects)
    return CommandClassification(kind, family, tuple(file_ops))


__all__ = [
    "CLASSIFY_VERSION",
    "CommandClassification",
    "CommandKind",
    "FileOp",
    "FileOpKind",
    "classify_command",
]
