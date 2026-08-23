"""The ``claude-code`` adapter: a Claude Code session JSONL file -> shadow drafts.

Built against one real Claude Code 2.1.x session file (the JSONL under
``~/.claude/projects/<project>/<session>.jsonl``) and versioned against the
record shapes observed there. Records are taken in file order, which was the
``parentUuid`` chain order of the observed transcript; a ``parentUuid`` that
names a later record in the same file fails closed.

Mapping, one line per source shape:

- ``user`` with string ``message.content``: a ``message`` by ``user``
  (``system`` when ``isMeta`` is true). ``user`` with a block list: each
  ``text`` block is a ``message``; each ``tool_result`` block is the result of
  the earlier ``tool_use`` with the same id (``check_result`` or
  ``command_result`` for ``Bash``, ``tool_result`` for every other tool) and an
  ``unknown`` event when no earlier ``tool_use`` carries that id.
- ``assistant``: each ``text`` block is an agent ``message`` whose full text
  feeds ``claims.v1`` while only a bounded excerpt and a digest are kept;
  ``thinking`` blocks are hidden reasoning, never ingested and counted as
  skipped; each ``tool_use`` block maps by tool name: ``Bash`` through
  ``classify.v1`` (``command_exec``/``check_run``/``vcs_op``/``network_op``/
  ``install_op`` plus inferred ``file_*`` drafts for ``rm``/``mv``/``cp``/
  ``touch``/``sed -i``/``tee``/redirections), ``Read`` to ``file_read``,
  ``Edit``/``MultiEdit``/``NotebookEdit`` to ``file_edit``, ``Write`` to
  ``file_create``, ``WebFetch``/``WebSearch`` to ``network_op``, and every
  other tool (``Glob``, ``Grep``, ``TodoWrite``, ``Task``, ``AskUserQuestion``,
  MCP tools, ...) to ``tool_call``, with ``input.path`` recorded when usable.
- ``system`` with subtype ``turn_duration`` is bookkeeping (skipped); any other
  subtype is an ``unknown`` event with ``raw_type`` ``system:<subtype>``.
- ``attachment`` (context the harness injected), ``file-history-snapshot``,
  ``file-history-delta``, ``queue-operation``, ``mode``, ``permission-mode``,
  ``ai-title``, ``last-prompt``, ``atis-latch``, and ``summary`` carry no agent
  action: skipped and counted by type in ``ParsedSession.skipped``.
- Any other ``type`` is an ``unknown`` event whose ``source.raw_type`` is the
  type value. Nothing is dropped silently.

Paths in tool inputs are absolute. They are classified against ``--repo`` when
given, else against the record's ``cwd``, so a path under the repository is
repository-relative and anything else lands in ``outside_paths`` with the home
directory collapsed to ``~``. Exit codes: ``0`` when ``is_error`` is false,
the ``Exit code N`` line of an error result when present (else ``1``), and
``null`` when the source says nothing. File contents, command output, prompts,
and tool inputs are never stored: a write keeps the SHA-256 of the text it
wrote, a result keeps the SHA-256 of its text, a command keeps its digest and
a bounded excerpt, and ingest redacts every excerpt before persistence.

Fail-closed, naming the line and the field: a BOM, invalid UTF-8, a blank
line, a CR line ending, a line that is not a JSON object, a line longer than
``MAX_LINE_CHARS``, nesting deeper than ``MAX_NESTING``, a missing or
non-string ``type``, a ``sessionId`` that is not a session identifier or
changes mid-file, a ``parentUuid`` that refers to a later record, a ``user``
or ``assistant`` record without an object ``message`` or whose ``content`` is
neither a string nor a list of blocks, a block without a string ``type``, a
``tool_use`` without string ``id``/``name`` and object ``input``, a ``Bash``
call without a string ``command``, a file tool whose path is missing or
unusable (NUL, over-long), a ``tool_result`` without ``tool_use_id``, a
``timestamp`` that is not RFC 3339 UTC, a file with no ``sessionId`` at all,
and any remaining value ``ShadowEvent`` refuses (reported with the record
locator).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

from ...hashing import canonical_json_bytes, sha256_hex
from ..classify import classify_command
from ..redaction import classify_path, collapse_home_in_text
from . import AdapterError, Draft, ParsedSession
from .ndjson import _decode, _record

CLAUDE_CODE_ADAPTER = "claude-code"
CLAUDE_CODE_ADAPTER_VERSION = "1.0.0"
# record > message > content[] > block > input > edits[] > edit leaves six
# levels; structured tool inputs may go deeper, so the bound is generous.
MAX_NESTING = 24
MAX_LINE_CHARS = 16 * 1024 * 1024

_SESSION_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?Z$")
_EXIT_CODE = re.compile(r"^Exit code (\d{1,3})\b", re.MULTILINE)
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")

_SKIPPED_TYPES = frozenset(
    {
        "attachment",
        "file-history-snapshot",
        "file-history-delta",
        "queue-operation",
        "mode",
        "permission-mode",
        "ai-title",
        "last-prompt",
        "atis-latch",
        "summary",
    }
)
_SKIPPED_SYSTEM_SUBTYPES = frozenset({"turn_duration"})
# tool name -> (kind, input key holding the path, input key holding written text)
_FILE_TOOLS: dict[str, tuple[str, str, str | None]] = {
    "Read": ("file_read", "file_path", None),
    "Edit": ("file_edit", "file_path", "new_string"),
    "MultiEdit": ("file_edit", "file_path", "edits"),
    "Write": ("file_create", "file_path", "content"),
    "NotebookEdit": ("file_edit", "notebook_path", "new_source"),
}
_NETWORK_TOOLS = frozenset({"WebFetch", "WebSearch"})


class _Call(NamedTuple):
    index: int
    tool: str
    kind: str
    check_family: str | None
    argv_digest: str | None


class _State:
    def __init__(self, uuids: frozenset[str]) -> None:
        self.session_id: str | None = None
        self.drafts: list[Draft] = []
        self.pending: dict[str, _Call] = {}
        self.skipped: Counter[str] = Counter()
        self.unknown_count = 0
        self.uuids = uuids
        self.seen: set[str] = set()

    def add(self, draft: Draft) -> int:
        self.drafts.append(draft)
        if draft.fields.get("kind") == "unknown":
            self.unknown_count += 1
        return len(self.drafts) - 1


def _draft(
    kind: str,
    actor: str,
    *,
    ref: str,
    raw_type: str,
    ts: str | None,
    provenance: str = "observed",
    derived_from: tuple[int, ...] = (),
    **fields: object,
) -> Draft:
    return Draft(
        fields={
            "kind": kind,
            "actor": actor,
            "ts": ts,
            "source": {
                "adapter": CLAUDE_CODE_ADAPTER,
                "adapter_version": CLAUDE_CODE_ADAPTER_VERSION,
                "record_ref": ref,
                "raw_type": raw_type,
            },
            **fields,
        },
        provenance=provenance,  # type: ignore[arg-type]
        derived_from=derived_from,
    )


def _short_text(value: object, where: str, limit: int = 128) -> str:
    if not isinstance(value, str):
        raise AdapterError(f"{where} must be a string")
    if not value or len(value) > limit or _CONTROL.search(value):
        raise AdapterError(f"{where} must be 1-{limit} printable characters")
    return value


def _timestamp(line: int, record: Mapping[str, object]) -> str | None:
    value = record.get("timestamp")
    if value is None:
        return None
    if not isinstance(value, str) or not _TIMESTAMP.match(value):
        raise AdapterError(
            f'line {line}: field "timestamp" must be an RFC 3339 UTC timestamp'
        )
    return value


def _result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block["text"]
            for block in content
            if isinstance(block, Mapping)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        )
    return ""


def _digest(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return sha256_hex(value.encode("utf-8"))
    return sha256_hex(canonical_json_bytes(value))


class ClaudeCodeAdapter:
    """Parser for Claude Code session JSONL files; see the module docstring."""

    name = CLAUDE_CODE_ADAPTER
    version = CLAUDE_CODE_ADAPTER_VERSION

    def __init__(self, *, home: Path | None = None) -> None:
        # ``home`` is injectable so tests can collapse an invented home path.
        self._home = home

    def parse(self, data: bytes, *, repo: Path | None) -> ParsedSession:
        if not isinstance(data, bytes):
            raise AdapterError("claude-code input must be bytes")
        if repo is not None and not isinstance(repo, Path):
            raise AdapterError("repo must be a Path or None")
        self._home_now = Path.home() if self._home is None else self._home
        records: list[tuple[int, dict[str, object]]] = []
        for line_number, line in enumerate(_decode(data), start=1):
            if len(line) > MAX_LINE_CHARS:
                raise AdapterError(
                    f"line {line_number}: line exceeds {MAX_LINE_CHARS} characters"
                )
            records.append(
                (line_number, _record(line_number, line, max_nesting=MAX_NESTING))
            )
        state = _State(
            frozenset(
                record["uuid"]
                for _, record in records
                if isinstance(record.get("uuid"), str)
            )
        )
        for line_number, record in records:
            self._ingest_record(line_number, record, state, repo)
        if state.session_id is None:
            raise AdapterError("no record carries a sessionId")
        return ParsedSession(
            session_id=state.session_id,
            drafts=tuple(state.drafts),
            has_claims=False,
            raw_record_count=len(records),
            unknown_count=state.unknown_count,
            adapter=self.name,
            adapter_version=self.version,
            skipped=tuple(sorted(state.skipped.items())),
        )

    # -- records ---------------------------------------------------------------

    def _ingest_record(
        self,
        line: int,
        record: Mapping[str, object],
        state: _State,
        repo: Path | None,
    ) -> None:
        if "type" not in record:
            raise AdapterError(f'line {line}: missing field "type"')
        raw_type = _short_text(record["type"], f'line {line}: field "type"')
        session_id = record.get("sessionId")
        if session_id is not None:
            if not isinstance(session_id, str) or not _SESSION_ID.match(session_id):
                raise AdapterError(
                    f'line {line}: field "sessionId" must match [A-Za-z0-9._-]{{1,128}}'
                )
            if state.session_id is None:
                state.session_id = session_id
            elif session_id != state.session_id:
                raise AdapterError(
                    f'line {line}: sessionId changed from "{state.session_id}" '
                    f'to "{session_id}"'
                )
        parent = record.get("parentUuid")
        if (
            isinstance(parent, str)
            and parent in state.uuids
            and parent not in state.seen
        ):
            raise AdapterError(
                f'line {line}: field "parentUuid" refers to a later record'
            )
        uuid = record.get("uuid")
        if isinstance(uuid, str):
            state.seen.add(uuid)
        if raw_type in _SKIPPED_TYPES:
            state.skipped[raw_type] += 1
            return
        ts = _timestamp(line, record)
        ref = f"line:{line}"
        if raw_type == "system":
            subtype = record.get("subtype")
            label = (
                f"system:{subtype}"
                if isinstance(subtype, str) and subtype
                else "system"
            )
            if subtype in _SKIPPED_SYSTEM_SUBTYPES:
                state.skipped[label] += 1
                return
            label = _short_text(label, f'line {line}: field "subtype"')
            state.add(_draft("unknown", "system", ref=ref, raw_type=label, ts=ts))
            return
        if raw_type in ("user", "assistant"):
            self._message_record(line, record, raw_type, ts, state, repo)
            return
        state.add(_draft("unknown", "system", ref=ref, raw_type=raw_type, ts=ts))

    def _message_record(
        self,
        line: int,
        record: Mapping[str, object],
        raw_type: str,
        ts: str | None,
        state: _State,
        repo: Path | None,
    ) -> None:
        message = record.get("message")
        if not isinstance(message, Mapping):
            raise AdapterError(f'line {line}: field "message" must be an object')
        content = message.get("content")
        if raw_type == "assistant":
            actor = "agent"
        else:
            actor = "system" if record.get("isMeta") is True else "user"
        message_type = f"{raw_type}_message"
        if isinstance(content, str):
            self._text(f"line:{line}", content, actor, message_type, ts, state)
            return
        if not isinstance(content, list):
            raise AdapterError(
                f'line {line}: field "message.content" must be a string or an '
                "array of blocks"
            )
        cwd = record.get("cwd")
        cwd_path = Path(cwd) if isinstance(cwd, str) and cwd.startswith("/") else None
        repo_root = repo if repo is not None else cwd_path
        for index, block in enumerate(content):
            where = f"line {line}: block {index}"
            ref = f"line:{line}#{index}"
            if not isinstance(block, Mapping):
                raise AdapterError(f"{where} is not an object")
            block_type = _short_text(block.get("type"), f'{where} field "type"')
            if block_type == "text":
                text = block.get("text")
                if not isinstance(text, str):
                    raise AdapterError(f'{where} field "text" must be a string')
                self._text(ref, text, actor, message_type, ts, state)
            elif block_type == "thinking" and actor == "agent":
                state.skipped["thinking"] += 1
            elif block_type == "tool_use" and actor == "agent":
                self._tool_use(where, ref, block, ts, state, repo_root, cwd_path)
            elif block_type == "tool_result" and raw_type == "user":
                self._tool_result(where, ref, block, ts, state)
            else:
                state.add(
                    _draft(
                        "unknown",
                        "system",
                        ref=ref,
                        raw_type=f"{raw_type}.{block_type}"[:128],
                        ts=ts,
                    )
                )

    # -- blocks ----------------------------------------------------------------

    def _text(
        self,
        ref: str,
        text: str,
        actor: str,
        raw_type: str,
        ts: str | None,
        state: _State,
    ) -> None:
        collapsed = collapse_home_in_text(text, self._home_now)
        fields: dict[str, object] = {
            "excerpt": collapsed,
            "content_digest": sha256_hex(text.encode("utf-8")),
        }
        if actor == "agent":
            fields["_full_text"] = collapsed
        state.add(_draft("message", actor, ref=ref, raw_type=raw_type, ts=ts, **fields))

    def _tool_use(
        self,
        where: str,
        ref: str,
        block: Mapping[str, object],
        ts: str | None,
        state: _State,
        repo_root: Path | None,
        cwd: Path | None,
    ) -> None:
        call_id = _short_text(block.get("id"), f'{where} field "id"')
        name = _short_text(block.get("name"), f'{where} field "name"', limit=64)
        inputs = block.get("input")
        if not isinstance(inputs, Mapping):
            raise AdapterError(f'{where} field "input" must be an object')
        common: dict[str, object] = {"ref": ref, "raw_type": "tool_use", "ts": ts}
        if name == "Bash":
            command = inputs.get("command")
            if not isinstance(command, str):
                raise AdapterError(f'{where} field "input.command" must be a string')
            classified = classify_command(command)
            family = classified.check_family if classified.kind == "check_run" else None
            argv_digest = sha256_hex(command.encode("utf-8"))
            index = state.add(
                _draft(
                    classified.kind,
                    "agent",
                    tool=name,
                    call_id=call_id,
                    argv_digest=argv_digest,
                    argv_excerpt=collapse_home_in_text(command, self._home_now),
                    check_family=family,
                    **common,
                )
            )
            state.pending[call_id] = _Call(
                index, name, classified.kind, family, argv_digest
            )
            for op in classified.file_ops:
                paths, outside = self._paths(op.raw_path, repo_root, cwd)
                if not paths and not outside:
                    continue  # unexpressible shell operand; the command itself is kept
                state.add(
                    _draft(
                        op.kind,
                        "agent",
                        tool=name,
                        call_id=call_id,
                        paths=paths,
                        outside_paths=outside,
                        provenance="inferred",
                        derived_from=(index,),
                        **common,
                    )
                )
            return
        file_tool = _FILE_TOOLS.get(name)
        if file_tool is not None:
            kind, path_key, content_key = file_tool
            raw = inputs.get(path_key)
            if not isinstance(raw, str):
                raise AdapterError(f'{where} field "input.{path_key}" must be a string')
            paths, outside = self._paths(raw, repo_root, cwd)
            if not paths and not outside:
                raise AdapterError(
                    f'{where} field "input.{path_key}" is not a usable path'
                )
            digest = _digest(inputs.get(content_key)) if content_key else None
        elif name in _NETWORK_TOOLS:
            kind, paths, outside, digest = "network_op", (), (), None
        else:
            kind, digest = "tool_call", None
            raw = inputs.get("path")
            paths, outside = (
                self._paths(raw, repo_root, cwd) if isinstance(raw, str) else ((), ())
            )
        index = state.add(
            _draft(
                kind,
                "agent",
                tool=name,
                call_id=call_id,
                paths=paths,
                outside_paths=outside,
                content_digest=digest,
                **common,
            )
        )
        state.pending[call_id] = _Call(index, name, kind, None, None)

    def _tool_result(
        self,
        where: str,
        ref: str,
        block: Mapping[str, object],
        ts: str | None,
        state: _State,
    ) -> None:
        call_id = _short_text(block.get("tool_use_id"), f'{where} field "tool_use_id"')
        text = _result_text(block.get("content"))
        is_error = block.get("is_error")
        exit_code: int | None = None
        if is_error is False:
            exit_code = 0
        elif is_error is True:
            match = _EXIT_CODE.search(text)
            exit_code = int(match.group(1)) if match else 1
        digest = sha256_hex(text.encode("utf-8")) if text else None
        call = state.pending.pop(call_id, None)
        common: dict[str, object] = {
            "ref": ref,
            "raw_type": "tool_result",
            "ts": ts,
            "call_id": call_id,
            "exit_code": exit_code,
            "content_digest": digest,
        }
        if call is None:
            state.add(_draft("unknown", "tool", **common))
            return
        if call.kind == "check_run":
            kind = "check_result"
        elif call.tool == "Bash":
            kind = "command_result"
        else:
            kind = "tool_result"
        state.add(
            _draft(
                kind,
                "tool",
                tool=call.tool,
                argv_digest=call.argv_digest,
                check_family=call.check_family if kind == "check_result" else None,
                **common,
            )
        )

    def _paths(
        self, raw: str, repo_root: Path | None, cwd: Path | None
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        relative, outside = classify_path(
            raw, repo_root=repo_root, cwd=cwd, home=self._home_now
        )
        return (relative,) if relative else (), (outside,) if outside else ()


__all__ = [
    "CLAUDE_CODE_ADAPTER",
    "CLAUDE_CODE_ADAPTER_VERSION",
    "MAX_LINE_CHARS",
    "MAX_NESTING",
    "ClaudeCodeAdapter",
]
