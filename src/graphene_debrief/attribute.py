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


# -- bash commands that visibly write files -------------------------------------------------------


def bash_written_paths(command: str, root: Path) -> list[tuple[str, str]]:
    """(repo-relative path, "write" | "delete") for the obvious forms: > >> tee sed -i mv cp rm touch.

    Deliberately incomplete: anything else a shell command does to a file is invisible here.
    """
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    found: list[tuple[str, str]] = []
    segment: list[str] = []
    for token in tokens + ["\n"]:
        if token in (";", "&&", "||", "|", "\n") or token.endswith((";", "&&")):
            if token not in (";", "&&", "||", "|", "\n"):
                segment.append(token.rstrip(";&"))
            found.extend(_segment_paths(segment))
            segment = []
        else:
            segment.append(token)
    out: list[tuple[str, str]] = []
    for path, kind in found:
        if _NOT_A_PATH.search(path) or path in ("/dev/null", "-", "") or path.startswith("-"):
            continue
        rel = _relative(path, root)
        if (rel, kind) not in out:
            out.append((rel, kind))
    return out


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
    if not tokens:
        return out
    # skip leading VAR=value assignments and sudo/env wrappers
    start = 0
    while start < len(tokens) and ("=" in tokens[start] and not tokens[start].startswith("-")):
        start += 1
    cmd = tokens[start:]
    if not cmd:
        return out
    name = os.path.basename(cmd[0])
    args = [a for a in cmd[1:] if a not in (">", ">>", "1>", "&>", "2>")]
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
    if os.path.isabs(path):
        norm = os.path.normpath(path)
        base = os.path.normpath(str(root))
        return os.path.relpath(norm, base) if norm == base or norm.startswith(base + os.sep) else norm
    return os.path.normpath(path)


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
        out = self._run("show", f"{rev}:{path}")
        return out if out is not None else None

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
    reruns: list[tuple[ToolEvent, ToolEvent]] = field(default_factory=list)  # (failed check, later rerun)
    outside_repo: list[str] = field(default_factory=list)


def attribute_session(
    session: Session, prompts: list[Prompt], events: list[ToolEvent], root: Path, git: GitState | None = None
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
        all_known = all(t.known for t in timeline)
        start = timeline[0].old if timeline[0].known else None
        touched_prompts: list[str] = []
        for t in timeline:
            pid = t.event.prompt_id or ""
            if pid not in touched_prompts:
                touched_prompts.append(pid)
        touched_prompts.sort(key=lambda pid: order.get(pid, 0))
        if all_known:
            final = timeline[-1].new
            for pid in touched_prompts:
                mine = [t for t in timeline if (t.event.prompt_id or "") == pid]
                before, after = mine[0].old, mine[-1].new
                result.changes.append(_change(path, session.id, pid, before, after, by_prompt, "payload"))
            if start == final and any(t.old != t.new for t in timeline):
                result.reverted.append(FileChange(path, session.id, touched_prompts[-1], "reverted"))
            continue
        # git fallback: whole-session diff, credited to the last prompt that touched the file
        base = session.head_at_start or git.head()
        before = git.show(base, path) if base else None
        after = None if timeline[-1].deleted else _working_copy(root, path)
        strategy = "git" if git.available and base else "none"
        for pid in touched_prompts[:-1]:
            result.changes.append(
                FileChange(
                    path,
                    session.id,
                    pid,
                    "modified",
                    strategy=strategy,
                    unrequested=not mentions(by_prompt[pid].text, path) if pid in by_prompt else True,
                )
            )
        last = touched_prompts[-1]
        if strategy == "git":
            result.changes.append(_change(path, session.id, last, before, after, by_prompt, "git"))
            if before is not None and before == after:
                result.reverted.append(FileChange(path, session.id, last, "reverted", strategy="git"))
        else:
            result.changes.append(
                FileChange(
                    path,
                    session.id,
                    last,
                    "modified",
                    strategy="none",
                    unrequested=not mentions(by_prompt[last].text, path) if last in by_prompt else True,
                )
            )

    result.failed = [e for e in events if e.success is False]
    result.reruns = _reruns(events)
    result.changes.sort(key=lambda c: (order.get(c.prompt_id, 0), c.path))
    return result


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


def is_check_command(command: str) -> bool:
    """Is any shell segment a test or lint runner (pytest, npm test, cargo test, make, ruff, ...)?"""
    for segment in re.split(r"&&|\|\||;|\||\n", command):
        words = segment.split()
        while words and (
            ("=" in words[0] and not words[0].startswith("-")) or words[0] in ("sudo", "env", "time")
        ):
            words.pop(0)
        for prefix in RUNNER_PREFIXES:
            if tuple(words[: len(prefix)]) == prefix:
                words = [w for w in words[len(prefix) :] if not w.startswith("-")]
        if not words:
            continue
        name = os.path.basename(words[0])
        rest = words[1:]
        if name in CHECKERS:
            return True
        if name in ("cargo", "go") and rest[:1] == ["test"]:
            return True
        if name in ("npm", "yarn", "pnpm") and (
            rest[:1] == ["test"]
            or (rest[:1] == ["run"] and rest[1:2] and rest[1] in ("test", "lint", "check", "typecheck"))
        ):
            return True
        if name == "npx" and rest[:1] and rest[0] in ("jest", "vitest", "tsc", "eslint"):
            return True
    return False


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


def _reruns(events: list[ToolEvent]) -> list[tuple[ToolEvent, ToolEvent]]:
    """A check command that failed and was run again later (whatever the rerun's outcome)."""
    groups: dict[str, list[ToolEvent]] = {}
    for ev in events:
        command = ev.input.get("command") if ev.tool == "Bash" else None
        if isinstance(command, str) and is_check_command(command):
            groups.setdefault(" ".join(command.split()), []).append(ev)
    out: list[tuple[ToolEvent, ToolEvent]] = []
    for runs in groups.values():
        for i, ev in enumerate(runs):
            if ev.success is False and i + 1 < len(runs):
                out.append((ev, runs[-1]))
                break
    return out


def attribute(store: Store, session_ids: list[str], root: Path) -> dict[str, Attribution]:
    git = GitState(root)
    out: dict[str, Attribution] = {}
    for sid in session_ids:
        session = store.session(sid)
        if session is None:
            continue
        out[sid] = attribute_session(session, store.prompts(sid), store.events(sid), root, git)
    return out
