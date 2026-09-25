"""Commits as records: what git holds in a session's window, and which recorded call made each one.

A commit belongs to the agent whose recorded Bash call ran ``git commit`` and is the earliest such
call whose response prints a prefix of the SHA; a recorded ``git cherry-pick`` ties the new commit
to its origin's agent (docs/PRODUCT_THESIS.md, section 9, item 5). Nothing is matched by patch-id
or by subject: patch-id was tested and fails on exactly the conflicted picks.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .model import Commit, ToolEvent
from .record import seconds
from .shell import shell_segments
from .store import Store

STAMP = "%Y-%m-%dT%H:%M:%S.000Z"
RECORD, FIELD = "\x00", "\x1f"  # separators no subject or path can hold; git writes them as %x00/%x1f
FORMAT = "%x00%H%x1f%cI%x1f%s"
# A hex run standing as a whole word, so a longer hex word and a `git commit` inside a quoted string
# credit nothing. The residual risk: a 7-digit decimal (a line count, a port) is also a hex prefix,
# so one such number in ~2^28 names a commit of this very window and credits it to the call that
# printed it. Nothing shorter than 7 characters is read.
HEX = re.compile(r"\b[0-9a-f]{7,40}\b")
GIT_FLAGS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}


def sync_commits(store: Store, root: Path | str, session_ids: list[str]) -> None:
    """Fill ``commits`` and ``commit_files`` from git for each session's window: every ref, the
    agents' worktree branches included, every path with no exclusions. Idempotent, because
    ``Store.add_commit`` keeps the first credit."""
    found: dict[str, Commit] = {}
    events: list[ToolEvent] = []
    for sid in session_ids:
        session = store.session(sid)
        if session is None or not session.started_at:
            continue
        end = session.ended_at or datetime.now(UTC).strftime(STAMP)  # still running: up to now
        for commit in window(Path(root), session.started_at, end):
            found.setdefault(commit.sha, commit)
        events += [e for e in store.events(sid) if e.tool == "Bash"]
    if not found:
        return
    credit(list(found.values()), events)
    with store.transaction():
        for commit in found.values():
            store.add_commit(commit)


def window(root: Path, start: str, end: str) -> list[Commit]:
    """Every commit git holds whose committer date lies in the window, newest first, with the paths
    ``--name-status`` lists for it (a rename contributes its new path), and for a merge the ``--cc``
    paths ``git show`` prints, so a conflict resolution counts. One ``git log`` call."""
    try:
        proc = subprocess.run(
            [
                "git",
                "-c",
                "core.quotePath=false",
                "log",
                "--all",
                f"--since={start[:19]}Z",
                f"--until={end[:19]}Z",
                "--cc",
                "--name-status",
                f"--format={FORMAT}",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    out: list[Commit] = []
    for block in proc.stdout.split(RECORD)[1:]:
        head, *lines = block.splitlines()
        sha, committed, subject = head.split(FIELD, 2)
        files = [(parts[-1], parts[0]) for parts in (line.split("\t") for line in lines) if len(parts) > 1]
        out.append(Commit(sha, _utc(committed), subject, files=files))
    return out


def credit(commits: list[Commit], events: list[ToolEvent]) -> None:
    """Credit each commit in place to the earliest recorded call that made it."""
    by_prefix = {c.sha[:7]: c for c in commits}
    for e in sorted(events, key=lambda e: (e.timestamp, e.id)):
        command = e.input.get("command") if isinstance(e.input, dict) else None
        if not isinstance(command, str) or "git" not in command:
            continue
        for segment in shell_segments(command):
            verb = _verb(segment)
            if verb == "commit":
                for made in named(e.response, by_prefix):
                    if _during(made, e):
                        _claim(made, e, None)
            elif verb == "cherry-pick":
                origin = next(iter(named(" ".join(segment[1:]), by_prefix)), None)
                if origin is None:
                    continue  # the origin is outside the window: nothing here says what was copied
                for made in named(e.response, by_prefix):
                    if made is not origin and _during(made, e):
                        _claim(made, e, origin)


def _during(commit: Commit, e: ToolEvent) -> bool:
    """A call can only have made a commit that did not exist when it started. Agents print
    `git log --oneline -3` after committing, and that names older commits too: made by a person, a
    merge, another tool. Naming one is not making it. One second covers git's whole-second stamps."""
    return seconds(commit.committed_at) >= seconds(e.timestamp) - 1


def named(response: object, by_prefix: dict[str, Commit]) -> list[Commit]:
    """The commits a response names, by a 7-to-40 character prefix of the SHA in any field
    (``stdout`` and ``content`` both occur, in transcripts and hook events; so does a bare string).
    Each string is read as it stands, not as a dump of the response: JSON writes a newline as
    backslash-n, and that letter swallows the word boundary before a SHA that begins a line."""
    found: dict[str, Commit] = {}
    for text in _strings(response):
        for token in HEX.findall(text):
            commit = by_prefix.get(token[:7])
            if commit is not None and commit.sha.startswith(token):
                found[commit.sha] = commit
    return list(found.values())


def _strings(value: object) -> Iterator[str]:
    """Every string a response holds, at any depth: a bare one, a field, a list of content blocks."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _claim(commit: Commit, e: ToolEvent, origin: Commit | None) -> None:
    """The first call to name a commit keeps it. A cherry-pick's commit belongs to its origin's
    agent: the pick copies that agent's work, and the call that ran it is the record."""
    if commit.session_id is not None:
        return
    commit.session_id = e.session_id
    # a pick of a commit nobody is recorded making is still this call's commit, with its origin kept
    commit.agent_id = origin.agent_id if origin and origin.session_id else e.agent_id
    commit.event_id = e.id
    commit.origin_sha = origin.sha if origin else None


def _verb(segment: list[str]) -> str | None:
    """A segment's git subcommand, past git's own options: ``git -C dir commit`` -> ``commit``."""
    if not segment or os.path.basename(segment[0]) != "git":
        return None
    rest = iter(segment[1:])
    for token in rest:
        if token in GIT_FLAGS_WITH_VALUE:
            next(rest, None)
        elif not token.startswith("-"):
            return token
    return None


def _utc(committed: str) -> str:
    """git's committer date as the store's stamp."""
    return datetime.fromisoformat(committed).astimezone(UTC).strftime(STAMP)


def refresh_commits(store: Store, root: Path | str, fresh: list[str]) -> None:
    """Keep ``commits`` current without asking git about every session on every command: all of them
    the first time, afterwards the sessions just loaded and any still running or ended within a day."""
    sessions = store.sessions()
    if store.conn.execute("SELECT 1 FROM commits LIMIT 1").fetchone() is None:
        ids = [s.id for s in sessions]
    else:
        recent = (datetime.now(UTC) - timedelta(days=1)).strftime(STAMP)
        ids = [s.id for s in sessions if s.id in fresh or s.ended_at is None or s.ended_at >= recent]
    sync_commits(store, root, ids)
