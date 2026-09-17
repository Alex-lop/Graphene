"""Deterministic attribution: prompt -> file -> hunks, plus unrequested and abandoned detection.

No model is involved. Everything here is computed from the recorded tool events and, when a
payload does not carry file content, from git. docs/HOW_IT_WORKS.md describes the heuristics
and their failure modes in plain words.
"""

from __future__ import annotations

import difflib
import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .model import FileChange, Hunk, Prompt, Session, ToolEvent
from .store import Store

FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
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
_DEF = re.compile(
    r"^(\s*)(?:async\s+def|def|class|function|fn|pub fn|func|export\s+(?:default\s+)?(?:async\s+)?function|"
    r"export\s+class|export\s+const|impl|struct|enum|interface)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
_HUNK_HEADER = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_NOT_A_PATH = re.compile(r"[*?$`{}\[\]<>|]")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_SEPARATORS = re.compile(r"&&|\|\||;|\||\n")


# -- diffing ------------------------------------------------------------------------------------


def diff_hunks(before: str, after: str) -> list[Hunk]:
    """Unified-diff hunks between two texts, three lines of context."""
    hunks: list[Hunk] = []
    current: Hunk | None = None
    for line in difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True), n=3, lineterm=""
    ):
        header = _HUNK_HEADER.match(line)
        if header:
            old_start, old_lines, new_start, new_lines = header.groups()
            current = Hunk(int(old_start), int(old_lines or 1), int(new_start), int(new_lines or 1), [])
            hunks.append(current)
        elif current is not None and line[:1] in " +-":
            current.lines.append(line.rstrip("\n"))
    return hunks


def count_lines(hunks: list[Hunk]) -> tuple[int, int]:
    added = sum(1 for h in hunks for line in h.lines if line.startswith("+"))
    removed = sum(1 for h in hunks for line in h.lines if line.startswith("-"))
    return added, removed


def changed_symbols(before: str, after: str, hunks: list[Hunk]) -> list[str]:
    """Names of the definitions (def/class/function/fn...) that enclose the changed lines."""
    names: list[str] = []
    before_lines, after_lines = before.splitlines(), after.splitlines()
    for hunk in hunks:
        new_no, old_no = hunk.new_start, hunk.old_start
        for line in hunk.lines:
            if line.startswith("+"):
                found = _enclosing(after_lines, new_no - 1)
                new_no += 1
            elif line.startswith("-"):
                found = _enclosing(before_lines, old_no - 1)
                old_no += 1
            else:
                found = None
                new_no += 1
                old_no += 1
            if found and found not in names:
                names.append(found)
    return names


def _enclosing(lines: list[str], index: int) -> str | None:
    if not 0 <= index < len(lines) or not lines[index].strip():
        return None
    match = _DEF.match(lines[index])
    if match:
        return match.group(2)
    indent = len(lines[index]) - len(lines[index].lstrip())
    for i in range(index - 1, -1, -1):
        match = _DEF.match(lines[i])
        if match and len(match.group(1)) < indent:
            return match.group(2)
    return None


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


def _words(segment: str) -> list[str]:
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError:
        tokens = segment.split()
    while tokens and (
        ("=" in tokens[0] and not tokens[0].startswith("-")) or tokens[0] in ("sudo", "env", "time")
    ):
        tokens.pop(0)
    return tokens


def bash_written_paths(command: str, root: Path) -> list[tuple[str, str]]:
    """(repo-relative path, "write" | "delete") for the obvious forms: > >> tee sed -i mv cp rm touch.

    Relative paths follow `cd` segments inside the command. Deliberately incomplete: anything
    else a shell command does to a file is invisible here.
    """
    cwd = os.path.normpath(str(root))
    found: list[tuple[str, str]] = []
    for segment in _SEPARATORS.split(strip_heredocs(command)):
        tokens = _words(segment)
        if not tokens:
            continue
        if os.path.basename(tokens[0]) == "cd":
            target = tokens[1] if len(tokens) > 1 and not tokens[1].startswith("-") else "~"
            if not _NOT_A_PATH.search(target):
                cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(target)))
            continue
        for path, kind in _segment_paths(tokens):
            if _NOT_A_PATH.search(path) or path in ("/dev/null", "-", "") or path.startswith("-"):
                continue
            rel = _relative(os.path.join(cwd, os.path.expanduser(path)), root)
            if (rel, kind) not in found:
                found.append((rel, kind))
    return found


def _segment_paths(tokens: list[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in (">", ">>", "1>", "1>>", "&>", "2>") and i + 1 < len(tokens):
            out.append((tokens[i + 1], "write"))
            i += 2
            continue
        if t.startswith((">", ">>", "1>", "&>")) and len(t) > 2 and not t.startswith(">&"):
            out.append((t.lstrip(">1&"), "write"))
        i += 1
    name = os.path.basename(tokens[0])
    args = [a for a in tokens[1:] if a not in (">", ">>", "1>", "&>", "2>")]
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
    return os.path.relpath(norm, base) if norm == base or norm.startswith(base + os.sep) else norm


def check_segments(command: str) -> list[str]:
    """Normalised shell segments that run a test or lint tool (pytest, npm test, cargo test, make, ...)."""
    out: list[str] = []
    for segment in _SEPARATORS.split(strip_heredocs(command)):
        words = _words(segment)
        for prefix in RUNNER_PREFIXES:
            if tuple(words[: len(prefix)]) == prefix:
                words = [w for w in words[len(prefix) :] if not w.startswith("-")]
        if words and _is_checker(os.path.basename(words[0]), words[1:]):
            out.append(" ".join(segment.split()))
    return out


def _is_checker(name: str, rest: list[str]) -> bool:
    if name in CHECKERS:
        return True
    if name in ("cargo", "go") and rest[:1] == ["test"]:
        return True
    if name in ("npm", "yarn", "pnpm"):
        scripts = ("test", "lint", "check", "typecheck")
        return rest[:1] == ["test"] or (rest[:1] == ["run"] and bool(rest[1:2]) and rest[1] in scripts)
    return name == "npx" and bool(rest[:1]) and rest[0] in ("jest", "vitest", "tsc", "eslint")


def is_check_command(command: str) -> bool:
    return bool(check_segments(command))


# -- per-file timelines -------------------------------------------------------------------------


@dataclass
class Touch:
    """One tool call's effect on one file."""

    event: ToolEvent
    path: str
    old: str | None  # content before, when the payload carries it
    new: str | None  # content after, when it can be derived
    known: bool  # both sides known (a create counts as old=None known)
    deleted: bool = False


def _is_create(ev: ToolEvent) -> bool:
    return ev.tool == "Write" and isinstance(ev.response, dict) and ev.response.get("type") == "create"


def touches(events: list[ToolEvent], root: Path) -> list[Touch]:
    out: list[Touch] = []
    for ev in events:
        if ev.success is False:
            continue
        if ev.tool in FILE_TOOLS and ev.file_path:
            known = ev.new_content is not None and (ev.old_content is not None or _is_create(ev))
            out.append(Touch(ev, ev.file_path, ev.old_content, ev.new_content, known))
        elif ev.tool == "Bash":
            command = ev.input.get("command")
            if isinstance(command, str):
                for path, kind in bash_written_paths(command, root):
                    out.append(Touch(ev, path, None, None, False, deleted=kind == "delete"))
    return out


@dataclass
class GitState:
    """Git access for the fallback strategy. Missing git or no repo degrades to strategy 'none'."""

    root: Path
    available: bool = True

    def show(self, rev: str, path: str) -> str | None:
        return self._run("show", f"{rev}:{path}")

    def _run(self, *args: str) -> str | None:
        if not self.available:
            return None
        try:
            proc = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            self.available = False
            return None
        return proc.stdout if proc.returncode == 0 else None

    def head(self) -> str | None:
        out = self._run("rev-parse", "HEAD")
        return out.strip() if out else None


def _working_copy(root: Path, path: str) -> str | None:
    full = root / path
    if not full.is_file():
        return None
    try:
        return full.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


# -- attribution --------------------------------------------------------------------------------


def mentions(prompt_text: str, path: str) -> bool:
    """Does the prompt name the file: full path, basename, stem or parent directory name?"""
    text = prompt_text.lower()
    p = Path(path)
    names = {path.lower(), p.name.lower(), p.stem.lower()}
    if p.parent.name:
        names.add(p.parent.name.lower())
    return any(n and n in text for n in names)


@dataclass
class Attribution:
    changes: list[FileChange] = field(default_factory=list)
    reverted: list[FileChange] = field(default_factory=list)  # session-level revert, effect="reverted"
    failed: list[ToolEvent] = field(default_factory=list)
    reruns: list[tuple[ToolEvent, ToolEvent, str]] = field(
        default_factory=list
    )  # (failed, latest rerun, check)
    outside_repo: list[str] = field(default_factory=list)


def attribute_session(
    session: Session,
    prompts: list[Prompt],
    events: list[ToolEvent],
    root: Path,
    git: GitState | None = None,
) -> Attribution:
    """Everything the debrief needs for one session, computed deterministically."""
    git = git or GitState(root)
    result = Attribution()
    by_prompt = {p.id: p for p in prompts}
    order = {p.id: p.ordinal for p in prompts}
    per_path: dict[str, list[Touch]] = {}
    for touch in touches(events, root):
        if os.path.isabs(touch.path):
            if touch.path not in result.outside_repo:
                result.outside_repo.append(touch.path)
            continue
        per_path.setdefault(touch.path, []).append(touch)

    for path, timeline in per_path.items():
        touched_prompts: list[str] = []
        for t in timeline:
            pid = t.event.prompt_id or ""
            if pid not in touched_prompts:
                touched_prompts.append(pid)
        touched_prompts.sort(key=lambda pid: order.get(pid, 0))
        if all(t.known for t in timeline):
            start, final = timeline[0].old, timeline[-1].new
            for pid in touched_prompts:
                mine = [t for t in timeline if (t.event.prompt_id or "") == pid]
                result.changes.append(
                    _change(path, session.id, pid, mine[0].old, mine[-1].new, by_prompt, "payload")
                )
            if start == final and any(t.old != t.new for t in timeline):
                result.reverted.append(FileChange(path, session.id, touched_prompts[-1], "reverted"))
            continue
        # git fallback: whole-session diff, credited to the last prompt that touched the file
        if (root / path).is_dir():
            continue
        base = session.head_at_start or git.head()
        before = git.show(base, path) if base else None
        after = None if timeline[-1].deleted else _working_copy(root, path)
        strategy = "git" if git.available and base else "none"
        if before is None and after is None and (strategy == "git" or timeline[-1].deleted):
            continue  # nothing at the session start and nothing now: a glob, temp file, or unseen path
        last = touched_prompts[-1]
        for pid in touched_prompts[:-1]:
            result.changes.append(_placeholder(path, session.id, pid, by_prompt, strategy))
        if strategy == "git":
            result.changes.append(_change(path, session.id, last, before, after, by_prompt, "git"))
            if before is not None and before == after:
                result.reverted.append(FileChange(path, session.id, last, "reverted", strategy="git"))
        else:
            result.changes.append(_placeholder(path, session.id, last, by_prompt, strategy))

    result.failed = [e for e in events if e.success is False]
    result.reruns = _reruns(events)
    result.changes.sort(key=lambda c: (order.get(c.prompt_id, 0), c.path))
    return result


def _placeholder(
    path: str, session_id: str, prompt_id: str, by_prompt: dict[str, Prompt], strategy: str
) -> FileChange:
    prompt = by_prompt.get(prompt_id)
    return FileChange(
        path,
        session_id,
        prompt_id,
        "modified",
        strategy=strategy,
        unrequested=not mentions(prompt.text, path) if prompt else True,
    )


def _change(
    path: str,
    session_id: str,
    prompt_id: str,
    before: str | None,
    after: str | None,
    by_prompt: dict[str, Prompt],
    strategy: str,
) -> FileChange:
    if after is None and before is not None:
        effect, hunks = "deleted", diff_hunks(before, "")
    elif before is None and after is not None:
        effect, hunks = "created", diff_hunks("", after)
    elif before == after:
        effect, hunks = "reverted", []
    else:
        effect, hunks = "modified", diff_hunks(before or "", after or "")
    added, removed = count_lines(hunks)
    prompt = by_prompt.get(prompt_id)
    return FileChange(
        path=path,
        session_id=session_id,
        prompt_id=prompt_id,
        effect=effect,
        hunks=hunks,
        added=added,
        removed=removed,
        strategy=strategy,
        unrequested=not mentions(prompt.text, path) if prompt else True,
        symbols=changed_symbols(before or "", after or "", hunks)[:8],
    )


def _reruns(events: list[ToolEvent]) -> list[tuple[ToolEvent, ToolEvent, str]]:
    """A check that failed and was run again later, by check segment; paired with the latest rerun."""
    pending: dict[str, ToolEvent] = {}  # check segment -> first failed call still awaiting a rerun
    latest: dict[tuple[str, str], tuple[ToolEvent, ToolEvent, str]] = {}
    for ev in events:
        command = ev.input.get("command") if ev.tool == "Bash" else None
        if not isinstance(command, str):
            continue
        for segment in check_segments(command):
            if segment in pending and pending[segment].id != ev.id:
                failed = pending[segment]
                latest[(failed.id, segment)] = (failed, ev, segment)
            elif ev.success is False and segment not in pending:
                pending[segment] = ev
    return sorted(latest.values(), key=lambda item: (item[0].timestamp, item[2]))


def attribute(store: Store, session_ids: list[str], root: Path) -> dict[str, Attribution]:
    git = GitState(root)
    out: dict[str, Attribution] = {}
    for sid in session_ids:
        session = store.session(sid)
        if session is None:
            continue
        out[sid] = attribute_session(session, store.prompts(sid), store.events(sid), root, git)
    return out
