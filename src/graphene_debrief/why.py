"""Intent-blame: which prompts changed a file, and which one last wrote a given line."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .attribute import GitState, attribute_session
from .explain import template
from .model import FileChange
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
    explained_by: str
    change: FileChange = field(repr=False, compare=False)


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


def why_path(store: Store, root: Path, path: str) -> list[WhyEntry]:
    """Every prompt that changed the file, newest first, with the stored explanation when there is one."""
    rel = normalise(root, path)
    name = os.path.basename(rel)
    git = GitState(root)
    entries: list[WhyEntry] = []
    for session in store.sessions():
        events = store.events(session.id)
        touched = any(
            e.file_path == rel or (e.tool == "Bash" and name in str(e.input.get("command", "")))
            for e in events
        )
        if not touched:
            continue
        prompts = store.prompts(session.id)
        by_id = {p.id: p for p in prompts}
        result = attribute_session(session, prompts, events, root, git)
        for change in result.changes:
            if change.path != rel:
                continue
            prompt = by_id.get(change.prompt_id)
            stored = store.explanation(change.prompt_id, rel) if prompt else None
            text, by = stored if stored else (template(change), "none")
            entries.append(
                WhyEntry(
                    session.id,
                    prompt.id if prompt else "",
                    prompt.ordinal if prompt else 0,
                    prompt.timestamp if prompt else (session.started_at or ""),
                    prompt.text if prompt else "(changes recorded before the first prompt)",
                    change.effect,
                    change.added,
                    change.removed,
                    text,
                    by,
                    change,
                )
            )
    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return entries


def why_line(store: Store, root: Path, path: str, line: int) -> LineAnswer:
    """Narrow to the prompt whose edit wrote this line; list candidates when more than one could have."""
    rel = normalise(root, path)
    content = _line(root / rel, line)
    if content is None:
        return LineAnswer(rel, line, None, None, None, [], f"{rel} has no line {line} on disk")
    commit, committed_at = blame(root, rel, line)
    entries = why_path(store, root, rel)
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
