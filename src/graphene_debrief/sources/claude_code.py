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
- Subagent transcripts live in ``<dir>/<session id>/subagents/**/*.jsonl``. They share the
  session id, carry ``agentId``, and their records carry the parent ``promptId``.
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
from pathlib import Path

from ..model import Prompt, Session, ToolEvent
from ..store import Store

HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "PostToolUse", "PostToolUseFailure", "Stop")
HOOK_COMMAND = "graphene ingest hook"
FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
_NOT_A_PROMPT = (
    "<command-name>",
    "<command-message>",
    "<local-command-stdout>",
    "<local-command-caveat>",
    "<task-notification>",
    "<system-reminder>",
    "[Request interrupted",
)


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def repo_root(start: Path) -> Path:
    """Nearest ancestor containing .git, else ``start`` itself."""
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


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


def is_within(path: str, root: Path) -> bool:
    """Lexically inside the repo, or inside it once symlinks are resolved (/tmp vs /private/tmp)."""
    p, r = os.path.normpath(path), os.path.normpath(str(root))
    return _inside(p, r) or _inside(os.path.realpath(p), os.path.realpath(r))


def relative_path(path: str, root: Path) -> str:
    """Repo-relative when inside the repo, otherwise the path unchanged."""
    p, r = os.path.normpath(path), os.path.normpath(str(root))
    if _inside(p, r):
        return os.path.relpath(p, r)
    rp, rr = os.path.realpath(p), os.path.realpath(r)
    return os.path.relpath(rp, rr) if _inside(rp, rr) else path


def file_path_of(tool: str, tool_input: dict) -> str | None:
    if tool not in FILE_TOOLS:
        return None
    value = tool_input.get("file_path") or tool_input.get("notebook_path")
    return value if isinstance(value, str) and value else None


def apply_edits(text: str, edits: list[tuple[str, str, bool]]) -> str:
    for old, new, replace_all in edits:
        if old:
            text = text.replace(old, new) if replace_all else text.replace(old, new, 1)
    return text


def attach_file_content(event: ToolEvent, root: Path) -> None:
    """Fill file_path, and old/new content when the tool payload carries enough to derive them."""
    path = file_path_of(event.tool, event.input)
    if not path:
        return
    event.file_path = relative_path(path, root)
    if os.path.isabs(event.file_path):
        return  # outside the repo: keep the path, never the contents (they may be credentials)
    resp = event.response if isinstance(event.response, dict) else {}
    tin = event.input
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
    if not isinstance(sid, str) or not sid or name not in HOOK_EVENTS:
        return False
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
        prompt_id = event.get("prompt_id") or str(uuid.uuid4())
        store.add_prompt(
            Prompt(
                id=str(prompt_id),
                session_id=sid,
                ordinal=store.next_ordinal(sid),
                timestamp=ts,
                text=str(event.get("prompt") or ""),
            )
        )
        return True
    if name == "Stop":
        store.end_session(sid, ts)
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
    ev = ToolEvent(
        id=str(event.get("tool_use_id") or uuid.uuid4()),
        session_id=sid,
        prompt_id=prompt_id,
        timestamp=ts,
        tool=tool,
        input=tool_input,
        response=response,
        success=ok,
        agent_id=event.get("agent_id"),
    )
    attach_file_content(ev, root)
    store.add_event(ev)
    return True


def hook_main(stdin=None, cwd: Path | None = None) -> int:
    """``graphene ingest hook``: never raises, never writes stdout, always returns 0."""
    root = Path(cwd or os.getcwd())
    try:
        raw = (stdin or sys.stdin).read()
        event = json.loads(raw) if raw.strip() else {}
        if not isinstance(event, dict):
            raise ValueError("hook input is not a JSON object")
        root = repo_root(Path(event.get("cwd") or root))
        with Store.open(root, quick=True) as store:
            ingest_hook_event(store, event, root)
    except Exception:
        _log_error(root)
    return 0


def _log_error(root: Path) -> None:
    try:
        directory = root / ".graphene"
        directory.mkdir(exist_ok=True)
        with open(directory / "ingest.log", "a", encoding="utf-8") as log:
            log.write(f"{now_iso()} {traceback.format_exc()}\n")
    except Exception:
        pass


def install_hooks(root: Path) -> list[str]:
    """Merge our hook into .claude/settings.json, keeping everything else. Returns events added."""
    path = root / ".claude" / "settings.json"
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
    return added


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


def transcripts_for(root: Path, projects: Path | None = None) -> list[Path]:
    """Transcript files whose project directory was launched at or under ``root``."""
    projects = projects or default_projects_dir()
    names = {project_dir_name(root), project_dir_name(Path(os.path.realpath(root)))}
    if not projects.is_dir():
        return []
    found: list[Path] = []
    for directory in sorted(projects.iterdir()):
        if directory.is_dir() and any(
            directory.name == n or directory.name.startswith(n + "-") for n in names
        ):
            found.extend(sorted(directory.glob("*.jsonl")))
    return found


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
    """A text block minus injected context; empty when the block is not the user's own words."""
    text = _INJECTED.sub("", block).strip()
    return "" if text.startswith(_NOT_A_PROMPT) else text


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


def parse_transcript(path: Path, root: Path) -> ParsedSession:
    main = list(iter_records(path))
    subs = [r for f in subagent_files(path) for r in iter_records(f)]
    session_id = path.stem
    skipped: Counter = Counter()
    stamps = [r["timestamp"] for r in main + subs if isinstance(r.get("timestamp"), str)]
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
    for record in main + subs:
        kind = record.get("type")
        if kind == "assistant":
            message = record.get("message")
            for block in (message.get("content") if isinstance(message, dict) else None) or []:
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
                        agent_id=record.get("agentId"),
                    )
        elif kind == "user":
            message = record.get("message")
            content = message.get("content") if isinstance(message, dict) else None
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
    events = sorted(calls.values(), key=lambda e: e.timestamp)
    for ev in events:
        if ev.prompt_id is None:
            ev.prompt_id = _prompt_before(prompts, ev.timestamp)
        attach_file_content(ev, root)
    session = Session(
        id=session_id,
        repo=str(root),
        started_at=min(stamps) if stamps else None,
        ended_at=max(stamps) if stamps else None,
        head_at_start=None,
        source="backfill",
        transcript_path=str(path),
    )
    return ParsedSession(session, prompts, events, skipped)


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

    A backfilled session whose transcript grew since is reloaded. A session the hooks recorded is
    left alone unless ``replace`` is set: then its prompts and tool calls are rebuilt from the
    transcript (the hooks may have been installed mid-session) and its git HEAD is kept.
    """
    report = BackfillReport()
    for path in transcripts if transcripts is not None else transcripts_for(root, projects):
        try:
            _backfill_one(store, root, path, replace, report)
        except Exception as exc:  # one unreadable transcript must not stop the others
            report.failed.append((str(path), f"{exc.__class__.__name__}: {exc}"))
    return report


def _backfill_one(store: Store, root: Path, path: Path, replace: bool, report: BackfillReport) -> None:
    cwd = transcript_cwd(path)
    if cwd is None or not is_within(cwd, root):
        report.other_repo.append(path.stem)
        return
    session_id = path.stem
    existing = store.session(session_id)
    parsed = None
    if existing is not None:
        if existing.source != "backfill" and not replace:
            report.skipped.append(session_id)
            return
        parsed = parse_transcript(path, root)
        if not replace and (parsed.session.ended_at or "") <= (existing.ended_at or ""):
            report.skipped.append(session_id)
            return
        store.delete_session_data(session_id)
        parsed.session.head_at_start = existing.head_at_start
        parsed.session.source = existing.source
        starts = [t for t in (existing.started_at, parsed.session.started_at) if t]
        parsed.session.started_at = min(starts) if starts else None
        report.refreshed.append(session_id)
    else:
        report.added.append(session_id)
    parsed = parsed or parse_transcript(path, root)
    store.upsert_session(parsed.session)
    for prompt in parsed.prompts:
        store.add_prompt(prompt)
    for event in parsed.events:
        store.add_event(event)
    report.skipped_records.update(parsed.skipped)
