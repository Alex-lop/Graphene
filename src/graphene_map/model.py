"""The records shared by the store, the hooks, the map and a node's record.

The hook loads this module on every agent event, and ``dataclasses`` imports ``inspect`` (and
``ast``, ``dis`` and ``tokenize`` with it): that import and the five classes it built cost the hook
more than opening the store and writing the row. ``@record`` gives each class what
``@dataclass(slots=True)`` gave it, and nothing else (tests/test_hook_budget.py, WORK).
"""

from __future__ import annotations


class Record:
    """Built by ``@record``: slots in the order the fields are written, an __init__ that takes them
    by position or name with their defaults, and equality and a repr over the same fields."""

    __slots__ = ()
    _defaults: dict[str, object] = {}

    def __init__(self, *args: object, **kwargs: object) -> None:
        names, kind = self.__slots__, type(self).__qualname__
        if len(args) > len(names):
            raise TypeError(f"{kind}() takes {len(names)} arguments but {len(args)} were given")
        values = {n: list(v) if isinstance(v, list) else v for n, v in self._defaults.items()}
        values.update(zip(names, args, strict=False))  # the rest keep their defaults
        for name, value in kwargs.items():
            if name not in names or names.index(name) < len(args):
                raise TypeError(f"{kind}() got an unexpected or repeated argument {name!r}")
            values[name] = value
        missing = [n for n in names if n not in values]
        if missing:
            raise TypeError(f"{kind}() missing {', '.join(repr(n) for n in missing)}")
        for name in names:
            setattr(self, name, values[name])

    def _fields(self) -> tuple:
        return tuple(getattr(self, n) for n in self.__slots__)

    def __eq__(self, other: object) -> bool:
        if other.__class__ is not self.__class__:
            return NotImplemented
        return self._fields() == other._fields()  # type: ignore[attr-defined]

    def __repr__(self) -> str:
        said = ", ".join(f"{n}={getattr(self, n)!r}" for n in self.__slots__)
        return f"{type(self).__qualname__}({said})"


def record(cls: type) -> type:
    """The class again, as a Record: its annotated names are its slots and fields, in order, and a
    value written beside one is its default (a list default is copied for each record)."""
    names = tuple(cls.__annotations__)
    body = {k: v for k, v in vars(cls).items() if k not in (*names, "__dict__", "__weakref__")}
    defaults = {n: vars(cls)[n] for n in names if n in vars(cls)}
    return type(cls.__name__, (Record,), {**body, "__slots__": names, "_defaults": defaults})


@record
class Session:
    id: str
    repo: str
    started_at: str | None = None
    ended_at: str | None = None
    head_at_start: str | None = None  # git HEAD when the session started; None when unknown
    source: str = "hook"  # "hook"; "backfill" in a store an earlier version filled from transcripts
    transcript_path: str | None = None


@record
class Prompt:
    """One user message. The unit of intent: everything is grouped under prompts."""

    id: str
    session_id: str
    ordinal: int
    timestamp: str
    text: str


@record
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


@record
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


@record
class Commit:
    """A commit from git, and the recorded call that made it when there is one."""

    sha: str
    committed_at: str
    subject: str
    session_id: str | None = None  # None: no recorded call names this commit
    agent_id: str | None = None  # None with a session_id: the main agent
    event_id: str | None = None  # the Bash call whose response names the SHA
    origin_sha: str | None = None  # the commit a recorded cherry-pick copied
    files: list[tuple[str, str | None]] = []  # (repo-relative path, status); copied for each record
