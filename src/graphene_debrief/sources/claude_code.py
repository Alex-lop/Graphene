"""Claude Code source: live hook ingestion and retroactive transcript backfill.

What this relies on, as observed on Claude Code 2.1.2xx transcripts (see docs/HOW_IT_WORKS.md):

- A transcript is JSONL, one record per line, with a ``type`` of ``user``, ``assistant`` or one
  of many bookkeeping types (``attachment``, ``system``, ``file-history-snapshot``, ...). Types
  this parser does not understand are skipped and counted.
- A user prompt is a ``user`` record whose ``message.content`` is a string (or text blocks) and
  which is not ``isMeta``, not ``isSidechain`` and carries no ``tool_result`` block. Slash-command
  echoes arrive wrapped in ``<command-name>`` / ``<local-command-stdout>`` tags and are skipped.
- A tool call is a ``tool_use`` block in an ``assistant`` record. Its result is a ``tool_result``
  block in a later ``user`` record (``is_error`` marks failure) whose top-level ``toolUseResult``
  holds the structured result: Edit -> ``originalFile``/``oldString``/``newString``,
  Write -> ``type``/``content``/``originalFile``, Bash -> ``stdout``/``stderr``; failures are a
  string starting with ``Error:``. That ``user`` record also carries ``promptId``, the prompt
  whose turn the call ran in.
- Subagent transcripts live in ``<dir>/<session id>/subagents/**/*.jsonl``, one file per agent.
  They share the session id, carry ``agentId``, and their records carry the parent ``promptId``.
  The file is the agent's identity: beside it sits ``agent-<id>.meta.json`` (``toolUseId``,
  ``agentType``, ``description``, ``spawnDepth``, ``workflowPhase``, ``worktreePath``; every field
  is optional, and a Workflow agent has no ``toolUseId``), and a Workflow run's agents sit in a
  ``wf_<id>`` directory named after the parent ``Workflow`` call's ``runId``, beside a
  ``journal.jsonl`` of that run's starts and results.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
import traceback
import uuid
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from ..attribute import nested_checkout
from ..model import Agent, Prompt, Session, ToolEvent
from ..store import StaleStore, Store

# SubagentStart and SubagentStop carry agent_id, agent_type and the common cwd, per the official
# page (code.claude.com/docs/en/hooks.md, "SubagentStart input" and "SubagentStop input"). Nothing
# here reads SubagentStop's last_assistant_message: that page says it is the agent's closing text,
# not the report it hands back, which arrives as the SubagentHandback call's tool_input.message.
HOOK_EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",  # never recorded: it is where the plan refuses a write before it happens (gate.py)
    "PostToolUse",
    "PostToolUseFailure",
    "SubagentStart",
    "SubagentStop",
    "Stop",
)
HOOK_COMMAND = "graphene ingest hook"
SETTINGS = ".claude/settings.local.json"  # personal; the team's settings.json is the committed one
TEAM_SETTINGS = ".claude/settings.json"
FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
JOURNAL = "journal.jsonl"
PROMPT_CAP = 4000
_NOT_A_PROMPT = (
    "<command-name>",
    "<command-message>",
    "<local-command-stdout>",
    "<local-command-caveat>",
    "<task-notification>",
    "<system-reminder>",
    "[Request interrupted",
)
_SLASH_COMMAND = re.compile(r"/[A-Za-z][\w:-]*(?:[\s;]|$)")  # /model, /help, /plugin:skill args


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def repo_root(start: Path) -> Path:
    """Nearest ancestor containing .git, else ``start`` itself; inside a linked worktree, the main
    repo's root, so a worktree agent's events land in the repo's own store."""
    for candidate in (start, *start.parents):
        main = _worktree_main(str(candidate))
        if main is not None:
            return Path(main) if main else candidate
    return start


@lru_cache(maxsize=4096)
def _worktree_main(directory: str) -> str | None:
    """The main repo root of the checkout rooted at ``directory``: in a linked worktree ``.git`` is a
    file naming the admin directory, whose ``commondir`` names the common ``.git``, whose parent is
    that root. ``""`` when the checkout is its own repo (a clone, or a submodule, whose admin
    directory has no ``commondir``), None when the directory is no checkout at all. Stdlib only: the
    hook path must not spawn git."""
    dot = os.path.join(directory, ".git")
    if not os.path.exists(dot):
        return None
    if os.path.isdir(dot):
        return ""
    try:
        with open(dot, encoding="utf-8") as f:
            gitdir = f.read().partition("gitdir:")[2].strip()
        admin = gitdir if os.path.isabs(gitdir) else os.path.join(directory, gitdir)
        with open(os.path.join(admin, "commondir"), encoding="utf-8") as f:
            return os.path.dirname(os.path.normpath(os.path.join(admin, f.read().strip())))
    except OSError:
        return ""


def _worktree_of(directory: str, root: str) -> bool:
    main = _worktree_main(directory)
    return bool(main) and _same_dir(main, root)


def worktree_root(path: str, root: Path) -> str | None:
    """The root of the worktree of ``root`` that holds ``path``, when one holds it: the nearest
    checkout above it, asked from git's own files. A checkout that is its own repo ends the walk."""
    current = os.path.dirname(os.path.normpath(path))
    while True:
        main = _worktree_main(current)
        if main is not None:
            return current if main and _same_dir(main, str(root)) else None
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


@lru_cache(maxsize=1024)
def _in_history(root: str, rel: str) -> bool:
    """Does any commit of this repo hold this path? ``git log`` stops at the first one that does."""
    log = ["git", "log", "--all", "--format=%H", "-1", "--", rel]
    try:
        out = subprocess.run(log, cwd=root, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and bool(out.stdout.strip())


class Worktrees:
    """The worktree roots of one repo, as one run learns them. While a worktree exists git's own
    files say it is one (``worktree_root``), and a directory that is still there and is a checkout
    of its own is another repo whatever a record calls it; once it is gone only the records are
    left: the ``worktreePath`` of an agent's ``meta.json``, and a bare recorded working directory,
    which is taken, one path at a time, only for a path this repo's history holds."""

    def __init__(self, root: Path) -> None:
        self.root = os.path.normpath(str(root))
        self.roots: list[str] = []
        self.copied: set[str] = set()  # gone directories a path of ours was written in

    def add(self, path: str | None) -> None:
        p = os.path.normpath(path) if path else ""
        if os.path.isdir(p) and not _worktree_of(p, self.root):
            return  # still there and a checkout of its own: another repo, whatever a record calls it
        if p and p != self.root and p not in self.roots:
            self.roots.append(p)
            self.roots.sort(key=len, reverse=True)  # .claude/worktrees/ is inside the repo root

    def known(self, path: str) -> bool:
        """Is this directory a worktree root of the repo: one an agent recorded, or one git says is."""
        p = os.path.normpath(path)
        return p in self.roots or p in self.copied or _worktree_of(p, self.root)

    def relative(self, path: str) -> str | None:
        for root in self.roots:  # longest first: the copy is the path it copies, not the copy's own
            if _inside(path, root) and path != root:
                return os.path.relpath(path, root)
        return None

    def copies(self, cwd: str, path: str) -> bool:
        """Was this path, written in a working directory that is gone, a copy of a path this repo
        holds? Asked of every path, never once of the directory: the file beside a copy is its own."""
        rel = os.path.relpath(path, cwd)
        if rel.startswith("..") or not _in_history(self.root, rel):
            return False
        here = relative_path(path, Path(self.root))
        if not os.path.isabs(here) and _in_history(self.root, here):
            return False  # the repo holds this path where it sits: a deleted subdirectory, no copy
        self.copied.add(cwd)  # for finding this repo's sessions, never for rewriting another path
        return True


def git_head(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return (out.stdout.strip() or None) if out.returncode == 0 else None


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


@lru_cache(maxsize=4096)
def _real_dir(directory: str) -> str:
    """realpath of a directory, cached: on macOS an lstat under /home (an automounter mount) costs
    about 12 ms, and a session that writes outside the repo would pay it for every call."""
    return os.path.realpath(directory)


def _real(path: str) -> str:
    head, tail = os.path.split(path)
    return os.path.join(_real_dir(head), tail) if head and tail else _real_dir(path)


def _same_dir(a: str, b: str) -> bool:
    return os.path.normpath(a) == os.path.normpath(b) or _real_dir(a) == _real_dir(b)


def is_within(path: str, root: Path, worktrees: Worktrees | None = None) -> bool:
    """Lexically inside the repo, or inside it once symlinks are resolved (/tmp vs /private/tmp), or
    a worktree of it: a session run in a worktree is a session of the repo it is a worktree of."""
    p, r = os.path.normpath(path), os.path.normpath(str(root))
    if _inside(p, r) or _inside(_real_dir(p), _real_dir(r)):
        return True
    return worktrees is not None and worktrees.known(p)


def relative_path(path: str, root: Path) -> str:
    """Repo-relative when inside the repo (and not inside a nested checkout), else the path unchanged."""
    p, r = os.path.normpath(path), os.path.normpath(str(root))
    rel = None
    if _inside(p, r):
        rel = os.path.relpath(p, r)
    else:
        rp, rr = _real(p), _real_dir(r)
        if _inside(rp, rr):
            rel = os.path.relpath(rp, rr)
    return path if rel is None or nested_checkout(root, rel) else rel


def _text(value: object) -> str | None:
    """A recorded field as text, or None: every field of a hook event and a meta.json is optional,
    and some hold a shape this does not read."""
    return value if isinstance(value, str) and value else None


def file_path_of(tool: str, tool_input: dict) -> str | None:
    if tool not in FILE_TOOLS:
        return None
    return _text(tool_input.get("file_path") or tool_input.get("notebook_path"))


def apply_edits(text: str, edits: list[tuple[str, str, bool]]) -> str:
    for old, new, replace_all in edits:
        if old:
            text = text.replace(old, new) if replace_all else text.replace(old, new, 1)
    return text


def _map_path(path: str, root: Path, cwd: str | None, worktrees: Worktrees | None) -> str:
    """Repo-relative for a path in the repo or in a worktree of it (a worktree copy maps to the path
    it copies), the path itself for anything else."""
    p = os.path.normpath(path)
    recorded = worktrees.relative(p) if worktrees else None
    if recorded is not None:
        return recorded
    live = worktree_root(p, root)
    if live is not None:
        if worktrees is not None:
            worktrees.add(live)
        return os.path.relpath(p, live)
    # A worktree that is gone leaves only the directory its agent recorded working in, and a
    # directory that is no longer there is the only one worth testing that way: a directory that
    # still exists and is no worktree is an ordinary directory, whatever its files are called.
    here = os.path.normpath(cwd) if cwd else ""
    if worktrees is not None and here and not os.path.isdir(here) and worktrees.copies(here, p):
        return os.path.relpath(p, here)
    return relative_path(p, root)


def attach_file_content(event: ToolEvent, root: Path, worktrees: Worktrees | None = None) -> None:
    """Fill file_path, and old/new content when the tool payload carries enough to derive them."""
    path = file_path_of(event.tool, event.input)
    if not path:
        return
    if not os.path.isabs(path) and event.cwd:
        path = os.path.join(event.cwd, path)  # a relative path means nothing without its directory
    event.file_path = _map_path(path, root, event.cwd, worktrees)
    tin = event.input
    if os.path.isabs(event.file_path):
        # outside the repo: keep the path, never the contents (they may be credentials), not even
        # inside the raw payload the store keeps for every call
        event.input = {k: v for k, v in tin.items() if k in ("file_path", "notebook_path")}
        if isinstance(event.response, dict) and "error" not in event.response:
            event.response = None
        return
    resp = event.response if isinstance(event.response, dict) else {}
    if event.tool == "Write":
        original = resp.get("originalFile")
        event.old_content = original if isinstance(original, str) else None
        content = resp.get("content", tin.get("content"))
        event.new_content = content if isinstance(content, str) else None
    elif event.tool == "Edit" and isinstance(resp.get("originalFile"), str):
        event.old_content = resp["originalFile"]
        event.new_content = apply_edits(
            event.old_content,
            [
                (
                    str(resp.get("oldString", tin.get("old_string", ""))),
                    str(resp.get("newString", tin.get("new_string", ""))),
                    bool(resp.get("replaceAll", tin.get("replace_all", False))),
                )
            ],
        )
    elif event.tool == "MultiEdit" and isinstance(resp.get("originalFile"), str):
        event.old_content = resp["originalFile"]
        edits = [e for e in tin.get("edits", []) if isinstance(e, dict)]
        event.new_content = apply_edits(
            event.old_content,
            [
                (
                    str(e.get("old_string", "")),
                    str(e.get("new_string", "")),
                    bool(e.get("replace_all", False)),
                )
                for e in edits
            ],
        )
    # NotebookEdit: path only; git supplies the diff at attribution time.


# -- live hooks ---------------------------------------------------------------------------------


def ingest_hook_event(store: Store, event: dict, root: Path, timestamp: str | None = None) -> bool:
    """Apply one hook event to the store. Returns True when something was recorded."""
    ts = timestamp or now_iso()
    name = event.get("hook_event_name")
    sid = event.get("session_id")
    if not isinstance(sid, str) or not sid or name not in HOOK_EVENTS or name == "PreToolUse":
        return False  # a call that has not happened yet is not a record; PostToolUse is
    if name == "SessionStart" or store.session(sid) is None:
        # A missing row on any other event means the hooks were installed mid-session: the
        # session started earlier, so its start HEAD is unknown (git resolves it by time later).
        store.upsert_session(
            Session(
                id=sid,
                repo=str(root),
                started_at=ts,
                head_at_start=git_head(root) if name == "SessionStart" else None,
                source="hook",
                transcript_path=event.get("transcript_path"),
            )
        )
        if name == "SessionStart":
            return True
    if name == "UserPromptSubmit":
        text = str(event.get("prompt") or "")
        if _SLASH_COMMAND.match(text.strip()):
            return False  # a slash command is not a request; the transcript parser skips them too
        prompt_id = event.get("prompt_id") or str(uuid.uuid4())
        store.add_prompt(
            Prompt(
                id=str(prompt_id),
                session_id=sid,
                ordinal=store.next_ordinal(sid),
                timestamp=ts,
                text=text,
            )
        )
        return True
    if name == "Stop":
        store.end_session(sid, ts)
        return True
    if name in ("SubagentStart", "SubagentStop"):
        agent_id = _text(event.get("agent_id"))
        if agent_id is None:
            return False
        started = ts if name == "SubagentStart" else None
        agent = Agent(agent_id, sid, type=_text(event.get("agent_type")), cwd=_text(event.get("cwd")))
        agent.started_at, agent.ended_at = started, None if started else ts
        store.upsert_agent(agent)
        return True
    ok = name == "PostToolUse"
    tool = str(event.get("tool_name") or "unknown")
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    response = (
        event.get("tool_response")
        if ok
        else {
            "error": event.get("error"),
            "is_interrupt": event.get("is_interrupt"),
        }
    )
    prompt_id = event.get("prompt_id")
    if not isinstance(prompt_id, str) or store.prompt(sid, prompt_id) is None:
        prompt_id = store.latest_prompt_id(sid)
    agent = event.get("agent_id")
    ev = ToolEvent(
        id=str(event.get("tool_use_id") or uuid.uuid4()),
        session_id=sid,
        prompt_id=prompt_id,
        timestamp=ts,
        tool=tool,
        input=tool_input,
        response=response,
        success=ok,
        # an agent id in a shape this does not know is kept as written: dropping the call loses a
        # record, and reading it as "no agent" would hand a subagent's call to the main agent
        agent_id=_text(agent) or (None if agent in (None, "") else json.dumps(agent)),
        cwd=_text(event.get("cwd")),
    )
    attach_file_content(ev, root)
    store.add_event(ev)
    return True


def hook_main(stdin=None, cwd: Path | None = None, stdout=None) -> int:
    """``graphene ingest hook``: never raises, always returns 0, and writes stdout only when a plan in
    force has something to say (a write refused, a stop refused: ``gate.decide``). Recording and
    deciding fail apart: an event that cannot be recorded is still decided, and a decision that
    cannot be made lets the call through and says so in the log, because ``plan.finish`` holds at
    the boundary with or without this hook."""
    root = Path(cwd or os.getcwd())
    try:
        root = repo_root(root)  # before anything can fail: a log written from a worktree goes to the repo
        raw = (stdin or sys.stdin).read()
        event = json.loads(raw) if raw.strip() else {}
        if not isinstance(event, dict):
            raise ValueError("hook input is not a JSON object")
        root = repo_root(Path(event.get("cwd") or root))
        with Store.open(root, quick=True) as store:
            try:
                ingest_hook_event(store, event, root)
            except Exception:
                _log_error(root)
            answer = None
            # no plan, nearly nothing to decide: a repo without one pays one read an event. A session
            # is taught the tree when it starts, a paragraph becomes one when it is typed, and a
            # write waits while this session's paragraph has no tree yet
            name = event.get("hook_event_name")
            sid = event.get("session_id")
            waiting = isinstance(sid, str) and bool(store.meta(f"tree:{sid}"))
            planner = bool(os.environ.get("GRAPHENE_PLANNER"))  # refused a write, plan or no plan
            if store.node_count() or name in ("SessionStart", "UserPromptSubmit") or waiting or planner:
                from .. import gate

                answer = gate.decide(store, event, root)
        if answer is not None:
            (stdout or sys.stdout).write(json.dumps(answer))
    except StaleStore as stale:
        # An unreadable file is the CLI's to move aside and backfill; a newer store is nobody's.
        _log(root, f"store is {stale.tag}: event skipped, run graphene")
    except Exception:
        _log_error(root)
    return 0


def _log(root: Path, message: str) -> None:
    try:
        directory = root / ".graphene"
        directory.mkdir(exist_ok=True)
        with open(directory / "ingest.log", "a", encoding="utf-8") as log:
            log.write(f"{now_iso()} {message}\n")
    except Exception:
        pass


def _log_error(root: Path) -> None:
    _log(root, traceback.format_exc())


def _holds_hook(path: Path) -> bool:
    try:
        return HOOK_COMMAND in path.read_text(encoding="utf-8")
    except OSError:
        return False


def hooks_file(root: Path) -> Path:
    """The settings file our hooks live in: whichever one already holds them, never both. A repo set
    up before there were seven events has them in the file it was set up in, and its two new events
    are added there; a repo with none gets them in the personal file."""
    return next((root / n for n in (SETTINGS, TEAM_SETTINGS) if _holds_hook(root / n)), root / SETTINGS)


def install_hooks(root: Path) -> list[str]:
    """Merge our hook into the repo's settings file, keeping everything else. Returns events added.

    The local file when the repo has no hooks of ours yet, not settings.json: the hooks call a tool
    installed on this machine, and the team's settings.json is the one people commit.
    """
    path = hooks_file(root)
    settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(settings, dict):
        raise ValueError(f"{path} is not a JSON object")
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError(f"{path}: 'hooks' is not an object")
    added: list[str] = []
    for event in HOOK_EVENTS:
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise ValueError(f"{path}: hooks.{event} is not a list")
        if any(_is_ours(h) for g in groups if isinstance(g, dict) for h in _handlers(g)):
            continue
        groups.append({"hooks": [{"type": "command", "command": HOOK_COMMAND, "timeout": 5}]})
        added.append(event)
    if added:
        path.parent.mkdir(exist_ok=True)
        _write_atomically(path, json.dumps(settings, indent=2) + "\n")
        if path.name == Path(SETTINGS).name:
            _exclude_locally(root, SETTINGS)
    return added


def _exclude_locally(root: Path, rel: str) -> None:
    """Keep the personal settings file out of `git add -A` through .git/info/exclude, which is this
    clone's own and never committed, so the repo's .gitignore is still never edited."""
    info = root / ".git" / "info"
    if not info.is_dir():
        return  # a worktree's .git is a file; its main checkout's exclude already covers it
    exclude = info / "exclude"
    with contextlib.suppress(OSError):
        text = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        if rel not in text.splitlines():
            exclude.write_text(
                text + ("" if not text or text.endswith("\n") else "\n") + rel + "\n", encoding="utf-8"
            )


def _write_atomically(path: Path, text: str) -> None:
    """Write via a temp file and os.replace (a crash leaves the old file), through a symlink to its target."""
    target = path.resolve() if path.exists() else path
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _handlers(group: dict) -> list:
    handlers = group.get("hooks")
    return handlers if isinstance(handlers, list) else []


def _is_ours(handler: object) -> bool:
    return isinstance(handler, dict) and handler.get("command") == HOOK_COMMAND


# -- transcript backfill ------------------------------------------------------------------------


def default_projects_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"


def project_dir_name(root: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(root))


def project_dirs(root: Path, projects: Path | None = None) -> tuple[list[Path], list[Path]]:
    """Claude's project directories: those named after ``root`` or a directory under it, and the rest."""
    projects = projects or default_projects_dir()
    names = {project_dir_name(root), project_dir_name(Path(os.path.realpath(root)))}
    mine: list[Path] = []
    others: list[Path] = []
    for directory in sorted(projects.iterdir()) if projects.is_dir() else []:
        if not directory.is_dir():
            continue
        named = any(directory.name == n or directory.name.startswith(n + "-") for n in names)
        (mine if named else others).append(directory)
    return mine, others


def worktree_transcripts(directories: list[Path], worktrees: Worktrees) -> list[Path]:
    """Transcripts of sessions run in a worktree of this repo: the project directory is named after
    the worktree wherever it sits, so only its own first recorded working directory ties it back to
    us. One read per directory, and never ``gitBranch``: concurrent agents contaminate it."""
    found: list[Path] = []
    for directory in directories:
        files = sorted(directory.glob("*.jsonl"))
        cwd = transcript_cwd(files[0]) if files else None
        if cwd and worktrees.known(cwd):
            worktrees.add(cwd)
            found.extend(files)
    return found


def orphan_subagents(directories: list[Path]) -> dict[str, list[Path]]:
    """Session id -> subagent transcripts sitting in a project directory that holds no transcript of
    that session: they are the session's all the same."""
    out: dict[str, list[Path]] = {}
    for directory in directories:
        for subagents in sorted(directory.glob("*/subagents")):
            session_id = subagents.parent.name
            if not (directory / f"{session_id}.jsonl").exists():
                out.setdefault(session_id, []).extend(sorted(subagents.rglob("*.jsonl")))
    return out


def transcripts_for(root: Path, projects: Path | None = None) -> list[Path]:
    """Transcript files whose project directory was launched at or under ``root``, or in a worktree
    of it."""
    mine, others = project_dirs(root, projects)
    found = [f for d in mine for f in sorted(d.glob("*.jsonl"))]
    return found + worktree_transcripts(others, Worktrees(root))


def looked_in(root: Path, projects: Path | None = None) -> str:
    """Where ``transcripts_for`` looks, as one path pattern to show when it found nothing."""
    pattern = str((projects or default_projects_dir()) / project_dir_name(root)) + "*"
    home = str(Path.home())
    return "~" + pattern[len(home) :] if pattern.startswith(home + os.sep) else pattern


def iter_records(path: Path) -> Iterator[dict]:
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                yield {"type": "<unparseable>"}
                continue
            yield record if isinstance(record, dict) else {"type": "<not-an-object>"}


def subagent_files(path: Path) -> list[Path]:
    directory = path.parent / path.stem / "subagents"
    return sorted(directory.rglob("*.jsonl")) if directory.is_dir() else []


def transcript_cwd(path: Path) -> str | None:
    for record in iter_records(path):
        if isinstance(record.get("cwd"), str):
            return record["cwd"]
    return None


_INJECTED = re.compile(r"<system-reminder>[\s\S]*?</system-reminder>")


def _human_text(block: str) -> str:
    """A text block minus injected context; empty when the block is not the user's own words
    (a slash-command echo, a tool notification) or is a slash command itself."""
    text = _INJECTED.sub("", block).strip()
    return "" if text.startswith(_NOT_A_PROMPT) or _SLASH_COMMAND.match(text) else text


def _text_of(content: object) -> str | None:
    """The user's text in a message, or None when the message is a tool result or carries none."""
    if isinstance(content, str):
        return _human_text(content) or None
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        parts = [
            _human_text(b["text"]) for b in content if isinstance(b, dict) and isinstance(b.get("text"), str)
        ]
        parts = [part for part in parts if part]
        return "\n".join(parts) if parts else None
    return None


def _result_text(content: object) -> str:
    if isinstance(content, str):
        return content[:4096]
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))[:4096]
    return ""


def is_prompt(record: dict) -> bool:
    if record.get("type") != "user" or record.get("isMeta") or record.get("isSidechain"):
        return False
    if record.get("isCompactSummary") or not isinstance(record.get("message"), dict):
        return False
    return bool(_text_of(record["message"].get("content")))


def _prompt_before(prompts: list[Prompt], timestamp: str) -> str | None:
    chosen = None
    for p in prompts:
        if p.timestamp <= timestamp:
            chosen = p.id
    return chosen


@dataclass
class ParsedSession:
    session: Session
    prompts: list[Prompt]
    events: list[ToolEvent]
    skipped: Counter = field(default_factory=Counter)
    agents: list[Agent] = field(default_factory=list)


def _message(record: dict) -> object:
    message = record.get("message")
    return message.get("content") if isinstance(message, dict) else None


def _fold(
    records: list[dict], session_id: str, agent_id: str | None, calls: dict, known: set, skipped: Counter
) -> list[str]:
    """Fold one file's records into ``calls``: its tool calls, their results, the working directory
    each call ran in, and a count of the record types this parser does not read. Returns the
    timestamps it saw."""
    stamps: list[str] = []
    for record in records:
        if isinstance(record.get("timestamp"), str):
            stamps.append(record["timestamp"])
        kind = record.get("type")
        if kind == "assistant":
            for block in _message(record) or []:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and isinstance(block.get("id"), str)
                    and block["id"] not in calls
                ):
                    calls[block["id"]] = ToolEvent(
                        id=block["id"],
                        session_id=session_id,
                        prompt_id=None,
                        timestamp=str(record.get("timestamp") or ""),
                        tool=str(block.get("name") or "unknown"),
                        input=block["input"] if isinstance(block.get("input"), dict) else {},
                        response=None,
                        success=None,
                        agent_id=_text(record.get("agentId")) or agent_id,
                        cwd=_text(record.get("cwd")),
                    )
        elif kind == "user":
            content = _message(record)
            if not isinstance(content, list):
                continue
            for block in content:
                if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                    continue
                ev = calls.get(block.get("tool_use_id"))
                if ev is None:
                    continue
                ev.success = not block.get("is_error")
                ev.response = record.get("toolUseResult")
                if ev.response is None:
                    ev.response = {"content": _result_text(block.get("content"))}
                if record.get("promptId") in known:
                    ev.prompt_id = record["promptId"]
        else:
            skipped[str(kind or "<untyped>")] += 1
    return stamps


def _meta_of(file: Path) -> dict:
    """The ``agent-<id>.meta.json`` sibling. Many real ones hold two fields, so nothing is required."""
    try:
        meta = json.loads(file.with_suffix(".meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return meta if isinstance(meta, dict) else {}


def _journal_labels(files: list[Path]) -> dict[str, str]:
    """A Workflow run's ``journal.jsonl`` is that run's own log, not a transcript. Some of its records
    carry a ``label`` for an agent and many carry none, so an agent's label is often empty."""
    labels: dict[str, str] = {}
    for file in files:
        for record in iter_records(file):
            agent_id, label = _text(record.get("agentId")), _text(record.get("label"))
            if agent_id and label:
                labels[agent_id] = label
    return labels


def _parse_agent(
    file: Path, session_id: str, worktrees: Worktrees, calls: dict, known: set, skipped: Counter
) -> tuple[Agent, list[str]]:
    """One subagent transcript, read as a unit: the file is the agent's identity, and its meta.json
    sibling, its ``wf_`` directory and its own first records say the rest."""
    records = list(iter_records(file))
    meta = _meta_of(file)
    named = (r["agentId"] for r in records if _text(r.get("agentId")))
    agent_id = next(named, file.stem.removeprefix("agent-"))
    stamps = _fold(records, session_id, agent_id, calls, known, skipped)
    prompt = next((t for r in records if r.get("type") == "user" and (t := _text_of(_message(r)))), None)
    worktrees.add(_text(meta.get("worktreePath")))
    agent = Agent(
        id=agent_id,
        session_id=session_id,
        parent_tool_use_id=_text(meta.get("toolUseId")),
        type=_text(meta.get("agentType")),
        task=_text(meta.get("description")),
        prompt=prompt[:PROMPT_CAP] if prompt else None,
        cwd=next((r["cwd"] for r in records if _text(r.get("cwd"))), None),
        worktree=_text(meta.get("worktreePath")),
        # the wf_ directory is named after the parent Workflow call's runId
        workflow_run=next(
            (
                run
                for above, run in zip(file.parts, file.parts[1:], strict=False)
                if above == "workflows" and run.startswith("wf_")
            ),
            None,
        ),
        phase=_text(meta.get("workflowPhase")),
        depth=meta.get("spawnDepth") if isinstance(meta.get("spawnDepth"), int) else None,
        started_at=min(stamps) if stamps else None,
        ended_at=max(stamps) if stamps else None,
    )
    return agent, stamps


def _finish_agent(agent: Agent, calls: dict, labels: dict[str, str], worktrees: Worktrees) -> None:
    """What only the other records say: who made the call that spawned it, what it was asked when its
    meta.json does not carry the description, its label, its closing message, its worktree."""
    parent = calls.get(agent.parent_tool_use_id or "")
    if parent is not None:
        agent.parent_agent_id = parent.agent_id  # None: the session's main agent made the call
        agent.task = agent.task or _text(parent.input.get("description"))
    agent.label = labels.get(agent.id)
    handback = (e for e in calls.values() if e.tool == "SubagentHandback" and e.agent_id == agent.id)
    agent.closing = next((_text(e.input.get("message")) for e in handback), None)
    if not agent.worktree and agent.cwd and worktrees.known(agent.cwd):
        agent.worktree = agent.cwd


def parse_transcript(
    path: Path, root: Path, worktrees: Worktrees | None = None, extra: list[Path] | None = None
) -> ParsedSession:
    main = list(iter_records(path))
    session_id = path.stem
    worktrees = worktrees if worktrees is not None else Worktrees(root)
    skipped: Counter = Counter()
    prompts: list[Prompt] = []
    for record in main:
        if is_prompt(record):
            prompts.append(
                Prompt(
                    id=str(record.get("promptId") or uuid.uuid4()),
                    session_id=session_id,
                    ordinal=len(prompts) + 1,
                    timestamp=str(record.get("timestamp") or ""),
                    text=_text_of(record["message"]["content"]) or "",
                )
            )
    known = {p.id for p in prompts}
    calls: dict[str, ToolEvent] = {}
    stamps = _fold(main, session_id, None, calls, known, skipped)
    files = [*subagent_files(path), *(extra or [])]
    labels = _journal_labels([f for f in files if f.name == JOURNAL])
    agents: list[Agent] = []
    for file in files:
        if file.name == JOURNAL:
            continue
        agent, agent_stamps = _parse_agent(file, session_id, worktrees, calls, known, skipped)
        agents.append(agent)
        stamps += agent_stamps
    events = sorted(calls.values(), key=lambda e: e.timestamp)
    for ev in events:
        if ev.prompt_id is None:
            ev.prompt_id = _prompt_before(prompts, ev.timestamp)
        attach_file_content(ev, root, worktrees)
    for agent in agents:  # after the events: mapping them is what accepts a worktree that is gone
        _finish_agent(agent, calls, labels, worktrees)
    session = Session(
        id=session_id,
        repo=str(root),
        started_at=min(stamps) if stamps else None,
        ended_at=max(stamps) if stamps else None,
        head_at_start=None,
        source="backfill",
        transcript_path=str(path),
    )
    return ParsedSession(session, prompts, events, skipped, agents)


@dataclass
class BackfillReport:
    added: list[str] = field(default_factory=list)
    refreshed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    other_repo: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (transcript path, error)
    skipped_records: Counter = field(default_factory=Counter)


def backfill(
    store: Store,
    root: Path,
    projects: Path | None = None,
    transcripts: list[Path] | None = None,
    replace: bool = False,
) -> BackfillReport:
    """Load sessions not already in the store.

    A transcript whose size and modification time are unchanged since it was last read is skipped
    without being parsed again; one that grew is reloaded. A session the hooks recorded is left
    alone unless ``replace`` is set, or unless the hooks are installed here and the transcript
    holds more tool calls than the hooks captured (they were installed mid-session): then its
    prompts and tool calls are rebuilt from the transcript and its git HEAD and start are kept.
    """
    report = BackfillReport()
    hooks = hooks_installed(root)
    worktrees = Worktrees(root)
    others: list[Path] = []
    extra: dict[str, list[Path]] = {}
    if transcripts is None:
        mine, others = project_dirs(root, projects)
        transcripts = [f for d in mine for f in sorted(d.glob("*.jsonl"))]
        extra = orphan_subagents(mine + others)

    def load(paths: list[Path]) -> None:
        for path in paths:
            try:
                _backfill_one(store, root, path, replace, report, hooks, worktrees, extra.get(path.stem, []))
            except Exception as exc:  # one unreadable transcript must not stop the others
                report.failed.append((str(path), f"{exc.__class__.__name__}: {exc}"))

    load(transcripts)
    # A session run in a worktree can only be found now: once the worktree itself is gone, what ties
    # its project directory back to this repo is the worktrees this repo's own agents recorded.
    load(worktree_transcripts(others, worktrees))
    return report


def hooks_installed(root: Path) -> bool:
    """Our hook command appears in either settings file (earlier versions wrote settings.json)."""
    return any(_holds_hook(root / name) for name in (SETTINGS, TEAM_SETTINGS))


def _stat(path: Path) -> tuple[int, float]:
    st = path.stat()
    return st.st_size, st.st_mtime


def _backfill_one(
    store: Store,
    root: Path,
    path: Path,
    replace: bool,
    report: BackfillReport,
    hooks: bool = False,
    worktrees: Worktrees | None = None,
    extra: list[Path] | None = None,
) -> None:
    session_id = path.stem
    worktrees = worktrees if worktrees is not None else Worktrees(root)
    existing = store.session(session_id)
    stat = _stat(path)
    if existing is not None and not replace and store.transcript_stat(session_id) == stat:
        report.skipped.append(session_id)  # same bytes, same mtime: nothing new to read
        return
    cwd = transcript_cwd(path)
    if cwd is None or not is_within(cwd, root, worktrees):
        report.other_repo.append(path.stem)
        return
    parsed = None
    if existing is not None:
        if existing.source == "backfill" and store.transcript_stat(session_id) is None:
            replace = True  # read by a version that kept less (the migration forgot the read): read again
        if existing.source != "backfill" and not replace:
            parsed = parse_transcript(path, root, worktrees, extra) if hooks else None
            if parsed is None or len(parsed.events) <= store.event_count(session_id):
                if parsed is not None:
                    with (
                        store.transaction()
                    ):  # what a hook cannot see: the task, the parent call, the closing
                        for agent in parsed.agents:
                            store.upsert_agent(agent)
                    store.set_transcript_stat(session_id, stat)
                report.skipped.append(session_id)
                return
            replace = True  # the hooks missed calls this transcript has: rebuild from it
        parsed = parsed or parse_transcript(path, root, worktrees, extra)
        if not replace and (parsed.session.ended_at or "") <= (existing.ended_at or ""):
            store.set_transcript_stat(session_id, stat)
            report.skipped.append(session_id)
            return
        parsed.session.head_at_start = existing.head_at_start
        parsed.session.source = existing.source
        starts = [t for t in (existing.started_at, parsed.session.started_at) if t]
        parsed.session.started_at = min(starts) if starts else None
        report.refreshed.append(session_id)
    else:
        report.added.append(session_id)
    parsed = parsed or parse_transcript(path, root, worktrees, extra)
    with store.transaction():  # one transaction per session: atomic, and 10x faster than autocommit
        if existing is not None:
            store.delete_session_data(session_id)
        store.upsert_session(parsed.session)
        store.set_transcript_stat(session_id, stat)
        for prompt in parsed.prompts:
            store.add_prompt(prompt)
        for agent in parsed.agents:
            store.upsert_agent(agent)
        for event in parsed.events:
            store.add_event(event)
    report.skipped_records.update(parsed.skipped)
