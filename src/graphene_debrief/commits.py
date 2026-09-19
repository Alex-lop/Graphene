"""Commits as records: what git holds in a session's window, and which recorded call made each one.

A commit belongs to the agent whose recorded Bash call ran ``git commit`` and is the earliest such
call whose response prints a prefix of the SHA; a recorded ``git cherry-pick`` ties the new commit
to its origin's agent (docs/PRODUCT_THESIS.md, section 9, item 5). Nothing is matched by patch-id
or by subject: patch-id was tested and fails on exactly the conflicted picks.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from .attribute import shell_segments
from .model import Commit, ToolEvent
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
    ``--name-status`` lists for it (a rename contributes its new path). One ``git log`` call."""
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
                    _claim(made, e, None)
            elif verb == "cherry-pick":
                origin = next(iter(named(" ".join(segment[1:]), by_prefix)), None)
                if origin is None or origin.session_id is None:
                    continue  # the origin is outside the window, or no record says who made it
                for made in named(e.response, by_prefix):
                    if made is not origin:
                        _claim(made, e, origin)


def named(response: object, by_prefix: dict[str, Commit]) -> list[Commit]:
    """The commits a response names, by a 7-to-40 character prefix of the SHA in any field
    (``stdout`` and ``content`` both occur, in transcripts and hook events; so does a bare string)."""
    text = response if isinstance(response, str) else json.dumps(response, default=str)
    found: dict[str, Commit] = {}
    for token in HEX.findall(text):
        commit = by_prefix.get(token[:7])
        if commit is not None and commit.sha.startswith(token):
            found[commit.sha] = commit
    return list(found.values())


def _claim(commit: Commit, e: ToolEvent, origin: Commit | None) -> None:
    """The first call to name a commit keeps it. A cherry-pick's commit belongs to its origin's
    agent: the pick copies that agent's work, and the call that ran it is the record."""
    if commit.session_id is not None:
        return
    commit.session_id = e.session_id
    commit.agent_id = origin.agent_id if origin else e.agent_id
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
