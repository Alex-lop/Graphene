"""Claude Code's hooks: `graphene init` installs one command, `graphene ingest hook`, on eight
events; each event is recorded in the store and, with a plan in force, answered by the gate
(``gate.decide``). This is the hook's path: nothing it imports reaches Typer or Rich, it writes
nothing on stdout but the gate's answer, and it never fails the agent (docs/HOW_IT_WORKS.md, part
two).
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
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from ..model import Agent, Prompt, Session, ToolEvent
from ..shell import nested_checkout
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
_NOT_A_PROMPT = (
    "<command-name>",
    "<command-message>",
    "<local-command-stdout>",
    "<local-command-caveat>",
    "<task-notification>",
    "<system-reminder>",
    "[Request interrupted",
    "Another Claude session sent a message",  # a subagent's hand-back, delivered as a prompt
    "<agent-message",
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


def _map_path(path: str, root: Path) -> str:
    """Repo-relative for a path in the repo or in a worktree of it (a worktree copy maps to the path
    it copies), the path itself for anything else."""
    p = os.path.normpath(path)
    live = worktree_root(p, root)
    return os.path.relpath(p, live) if live is not None else relative_path(p, root)


def attach_file_content(event: ToolEvent, root: Path) -> None:
    """Fill file_path, and old/new content when the tool payload carries enough to derive them."""
    path = file_path_of(event.tool, event.input)
    if not path:
        return
    if not os.path.isabs(path) and event.cwd:
        path = os.path.join(event.cwd, path)  # a relative path means nothing without its directory
    event.file_path = _map_path(path, root)
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
            # is taught the text when it starts and told plan first at a prompt, and with plan first
            # on (with no node, only the person's setting makes it so) it writes nothing yet
            name = event.get("hook_event_name")
            first = store.meta("plan_first") == "on"
            planner = bool(os.environ.get("GRAPHENE_PLANNER"))  # refused a write, plan or no plan
            if store.node_count() or name in ("SessionStart", "UserPromptSubmit") or first or planner:
                from .. import gate

                answer = gate.decide(store, event, root)
        if answer is not None:
            (stdout or sys.stdout).write(json.dumps(answer))
    except StaleStore as stale:
        # An unreadable file is the CLI's to move aside; a newer store is nobody's.
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


def hooks_installed(root: Path) -> bool:
    """Our hook command appears in either settings file (earlier versions wrote settings.json)."""
    return any(_holds_hook(root / name) for name in (SETTINGS, TEAM_SETTINGS))
