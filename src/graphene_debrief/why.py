"""Intent-blame: which prompts changed a file, and which one last wrote a given line."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .attribute import Attribution, GitState, attribute_session, credit_once
from .debrief import FileLine, template
from .model import FileChange, Prompt, Session
from .record import changes, seconds
from .store import Store


@dataclass
class WhyEntry:
    session_id: str
    prompt_id: str
    ordinal: int
    timestamp: str
    prompt_text: str
    effect: str
    added: int
    removed: int
    explanation: str
    change: FileChange = field(repr=False, compare=False)
    grade: str = ""  # edit | shell (the vendor's change list) | command (read from the recorded command)
    who: list[tuple[str | None, str | None]] = field(default_factory=list)  # (agent id, its task)

    def change_line(self):
        """The change as the renderers' file line, so `why` shows counts exactly as the card does."""
        return FileLine(
            self.change.path,
            self.effect,
            self.added,
            self.removed,
            self.change.unrequested,
            self.change.strategy,
            self.explanation,
            "none",
        )


@dataclass
class LineAnswer:
    path: str
    line: int
    content: str | None  # the line's current text, None when the file or line is missing
    commit: str | None  # git blame's commit, None when uncommitted or git is unavailable
    committed_at: str | None
    matches: list[WhyEntry]  # prompts whose edits added this exact line, newest first
    reason: str


def normalise(root: Path, path: str) -> str:
    full = os.path.normpath(path if os.path.isabs(path) else os.path.join(os.getcwd(), path))
    base = os.path.normpath(str(root))
    if full == base or full.startswith(base + os.sep):
        return os.path.relpath(full, base)
    return os.path.normpath(path)


def candidates(root: Path, path: str) -> list[str]:
    """The path as typed, relative to the current directory; then relative to the repo root when that
    is different, because the card prints root-relative paths and people paste them from anywhere."""
    first = normalise(root, path)
    if os.path.isabs(path):
        return [first]
    alt = os.path.normpath(path)
    return [first] if alt == first or alt.startswith("..") else [first, alt]


def why_path(store: Store, root: Path, path: str) -> list[WhyEntry]:
    """Every prompt that changed the file, newest first, each with what it did to the file."""
    for rel in candidates(root, path):
        entries = _why_rel(store, root, rel)
        if entries:
            return entries
    return []


def _why_rel(store: Store, root: Path, rel: str) -> list[WhyEntry]:
    name = os.path.basename(rel)
    git = GitState(root)
    entries: list[WhyEntry] = []
    done: list[tuple[Session, list[Prompt], Attribution]] = []
    for session in store.sessions():
        events = store.events(session.id)
        touched = any(
            e.file_path == rel or (e.tool == "Bash" and name in str(e.input.get("command", "")))
            for e in events
        )
        if not touched:
            continue
        prompts = store.prompts(session.id)
        done.append((session, prompts, attribute_session(session, prompts, events, root, git)))
    credit_once([(session, result) for session, _, result in done])
    for session, prompts, result in done:
        by_id = {p.id: p for p in prompts}
        events = store.events(session.id)
        agents = store.agents(session.id)
        task = {a.id: a.task for a in agents}
        under = {e.id: e for e in events}
        written = [w for w in changes(events, agents, session.repo)[0] if w.path == rel]
        for change in result.changes:
            if change.path != rel:
                continue
            prompt = by_id.get(change.prompt_id)
            mine = [w for w in written if under[w.event_id].prompt_id == change.prompt_id]
            grade = "edit" if any(w.grade == "edit" for w in mine) else "shell" if mine else "command"
            by = [w.agent_id for w in mine] or [  # no recorded write: whoever ran a command naming the file
                e.agent_id
                for e in events
                if e.tool == "Bash"
                and e.prompt_id == change.prompt_id
                and name in str(e.input.get("command"))
            ]
            entries.append(
                WhyEntry(
                    session.id,
                    prompt.id if prompt else "",
                    prompt.ordinal if prompt else 0,
                    min((w.timestamp for w in mine), default=None)  # when it was written, as the map says
                    or (prompt.timestamp if prompt else (session.started_at or "")),
                    prompt.text if prompt else "(changes recorded before the first prompt)",
                    change.effect,
                    change.added,
                    change.removed,
                    template(change),
                    change,
                    grade,
                    [(agent, task.get(agent)) for agent in dict.fromkeys(by)],
                )
            )
    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return entries


def why_line(store: Store, root: Path, path: str, line: int) -> LineAnswer:
    """Narrow to the prompt whose edit wrote this line; list candidates when more than one could have."""
    options = candidates(root, path)
    rel = next((c for c in options if (root / c).is_file()), options[0])
    content = _line(root / rel, line)
    if content is None:
        missing = (
            f"{rel} is not on disk in this checkout (it may live on another branch or in a worktree); "
            f"`graphene why {rel}` shows its history"
        )
        here = f"{rel} has no line {line} on disk"
        return LineAnswer(rel, line, None, None, None, [], here if (root / rel).is_file() else missing)
    commit, committed_at = blame(root, rel, line)
    entries = _why_rel(store, root, rel)
    wanted = content.strip()
    here = [e for e in entries if (line, wanted) in _added_lines(e.change)]
    anywhere = [e for e in entries if any(text == wanted for _, text in _added_lines(e.change))]
    matches = here or anywhere
    if committed_at:
        matches = [e for e in matches if e.timestamp <= committed_at]  # a later prompt cannot have written it
    if not matches:
        if commit and entries and committed_at and committed_at < min(e.timestamp for e in entries):
            reason = f"committed in {commit[:7]} before any recorded session; no recorded edit wrote it"
        elif commit and committed_at:
            reason = f"committed in {commit[:7]}; no recorded edit before that commit added this line"
        elif entries:
            reason = "prompts changed this file but none of their recorded edits added this exact line"
        else:
            reason = "no recorded session changed this file"
        return LineAnswer(rel, line, content, commit, committed_at, [], reason)
    if not here:
        reason = f"{len(matches)} recorded edit(s) added this text at a different line; newest first"
    elif len(matches) == 1:
        reason = "exactly one recorded edit added this line"
    else:
        reason = f"{len(matches)} recorded edits added an identical line; newest first"
    return LineAnswer(rel, line, content, commit, committed_at, matches, reason)


def _added_lines(change: FileChange) -> list[tuple[int, str]]:
    """(new-file line number, stripped text) for every line the change added."""
    out: list[tuple[int, str]] = []
    for hunk in change.hunks:
        new_no = hunk.new_start
        for line in hunk.lines:
            if line.startswith("+"):
                out.append((new_no, line[1:].strip()))
            if not line.startswith("-"):
                new_no += 1
    return out


def _line(full: Path, line: int) -> str | None:
    try:
        lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    return lines[line - 1] if 0 < line <= len(lines) else None


def blame(root: Path, rel: str, line: int) -> tuple[str | None, str | None]:
    """(commit, ISO time) for the line per git blame; (None, None) when uncommitted or git is unavailable."""
    try:
        proc = subprocess.run(
            ["git", "blame", "--porcelain", "-L", f"{line},{line}", "--", rel],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None, None
    if proc.returncode != 0 or not proc.stdout:
        return None, None
    head, *rest = proc.stdout.splitlines()
    sha = head.split()[0]
    if set(sha) == {"0"}:
        return None, None
    seconds = next((r.split()[1] for r in rest if r.startswith("committer-time ")), None)
    when = datetime.fromtimestamp(int(seconds), UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z") if seconds else None
    return sha, when


def commits_of(store: Store, rel: str) -> dict[str | None, list[str]]:
    """The commits that changed a path, by the session whose window holds them, newest session
    first; None gathers the commits made outside every recorded session."""
    rows = store.conn.execute(
        "SELECT c.sha, c.committed_at, c.session_id FROM commit_files f JOIN commits c USING (sha) "
        "WHERE f.path = ?",
        (rel,),
    ).fetchall()
    windows = [
        (s.id, seconds(s.started_at), seconds(s.ended_at) if s.ended_at else float("inf"))
        for s in reversed(store.sessions())
        if s.started_at
    ]
    held: dict[str | None, list[str]] = {sid: [] for sid, _, _ in windows} | {None: []}
    for sha, committed_at, credited in rows:
        at = seconds(committed_at)
        # the session recorded making a commit holds it, whatever other window it also falls in
        inside = next((sid for sid, start, end in windows if start <= at <= end), None)
        held[credited if credited and credited in held else inside].append(sha)
    return {sid: shas for sid, shas in held.items() if shas}


def path_coverage(store: Store, rel: str) -> str:
    """One file's share of law 7: of the commits that changed it, how many trace to a recorded
    write, only to an agent's commit, or to nothing. Empty when git never committed the path."""
    from .graph import run_records

    held = commits_of(store, rel)
    inside = [sid for sid in held if sid]
    if not held:
        return ""
    pairs = run_records(store, inside).coverage.pairs if inside else {}
    grades = [grade for (_sha, path), grade in pairs.items() if path == rel]
    write = sum(g in ("edit", "shell") for g in grades)
    n = len(grades)
    line = (  # these are commits of one file; the card's line counts files, so the words differ
        f"{n} commit{'s' if n != 1 else ''} of this file in recorded sessions · {write} with a write "
        f"recorded before it · {grades.count('commit')} made by an agent with no write recorded · "
        f"{grades.count('window')} by no identifiable agent"
    )
    outside = len(held.get(None, []))
    return line + (f" · {outside} more outside any recorded session" if outside else "")


def recorded_writes(store: Store, rel: str) -> list[tuple[str, str, str | None, str | None, str]]:
    """Every recorded write to a path, newest first: (time, session, agent, its task, grade). This
    is what `why` shows for a file Claude Code lists as changed by a shell command but whose diff no
    payload carries, so the file is never called unrecorded while its coverage says it is."""
    rows = []
    for session in store.sessions():
        agents = store.agents(session.id)
        task = {a.id: a.task for a in agents}
        for change in changes(store.events(session.id), agents, session.repo)[0]:
            if change.path == rel:
                rows.append(
                    (change.timestamp, session.id, change.agent_id, task.get(change.agent_id), change.grade)
                )
    return sorted(rows, reverse=True)


def last_commit(root: Path, rel: str) -> tuple[str, str] | None:
    """(short sha, committer date) of the last commit on any ref that changed the path, if git has one."""
    try:
        out = subprocess.run(
            ["git", "log", "--all", "-1", "--format=%h %cI", "--", rel],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha, _, when = out.stdout.strip().partition(" ")
    return (sha, when) if out.returncode == 0 and sha else None
