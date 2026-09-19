"""Dataclasses shared by the store, the sources, attribution and rendering."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Session:
    id: str
    repo: str
    started_at: str | None = None
    ended_at: str | None = None
    head_at_start: str | None = None  # git HEAD when the session started; None when unknown
    source: str = "hook"  # "hook" | "backfill"
    transcript_path: str | None = None


@dataclass(slots=True)
class Prompt:
    """One user message. The unit of intent: everything is grouped under prompts."""

    id: str
    session_id: str
    ordinal: int
    timestamp: str
    text: str


@dataclass(slots=True)
class ToolEvent:
    id: str
    session_id: str
    prompt_id: str | None
    timestamp: str
    tool: str
    input: dict
    response: object = None  # dict | str | None; capped at 256 KB in the store
    success: bool | None = True  # None when no result was recorded
    agent_id: str | None = None
    file_path: str | None = None  # repo-relative when inside the repo, else absolute
    old_content: str | None = None  # file content before this call, when the payload carries it
    new_content: str | None = None  # file content after this call, when it can be derived
    cwd: str | None = None  # the working directory the call ran in, as recorded


@dataclass(slots=True)
class Agent:
    """One subagent, from the records about it. The main agent has no row: it is the session."""

    id: str
    session_id: str
    parent_tool_use_id: str | None = None  # the parent's Agent call; a Workflow agent has none
    parent_agent_id: str | None = None  # who made that call; None when the main agent did
    type: str | None = None
    task: str | None = None  # the short description it was given
    prompt: str | None = None  # what it was told, capped
    cwd: str | None = None
    worktree: str | None = None  # the worktree root it worked in, when recorded
    workflow_run: str | None = None  # wf_<id>: the parent Workflow call's runId
    phase: str | None = None
    label: str | None = None
    depth: int | None = None
    started_at: str | None = None
    ended_at: str | None = None
    closing: str | None = None  # its closing message
    source: str = "claude-code"


@dataclass(slots=True)
class Commit:
    """A commit from git, and the recorded call that made it when there is one."""

    sha: str
    committed_at: str
    subject: str
    session_id: str | None = None  # None: no recorded call names this commit
    agent_id: str | None = None  # None with a session_id: the main agent
    event_id: str | None = None  # the Bash call whose response names the SHA
    origin_sha: str | None = None  # the commit a recorded cherry-pick copied
    files: list[tuple[str, str | None]] = field(default_factory=list)  # (repo-relative path, status)


@dataclass(slots=True)
class Hunk:
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[str]  # unified-diff body lines, each starting with ' ', '+' or '-'


@dataclass(slots=True)
class FileChange:
    """Derived: what one prompt did to one file."""

    path: str
    session_id: str
    prompt_id: str
    effect: str  # created | modified | deleted | reverted
    hunks: list[Hunk] = field(default_factory=list)
    added: int = 0
    removed: int = 0
    unrequested: bool = False
    strategy: str = "payload"  # payload | git | none
    symbols: list[str] = field(default_factory=list)  # definitions enclosing the changed lines


@dataclass(slots=True)
class DebriefRun:
    id: int
    session_ids: list[str]
    timestamp: str
