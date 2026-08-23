"""The ``claude-code`` adapter against the synthetic fixture and hand-built records.

The fixture under ``tests/fixtures/shadow/claude-code/`` is invented: no agent
produced it, no path or session id in it exists. It mirrors the record shapes
of a real Claude Code 2.1.x session file (the same keys and nesting) so the
mapping, the redaction, the reconstruction, the lint, and the capsule can be
exercised without any private transcript. Every fail-closed rule in the
adapter docstring has one test here, and each asserts that the error names
the line and the field and that nothing was persisted.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path

import pytest

from graphene.cli.main import main
from graphene.shadow.adapters import ADAPTERS, AdapterError, materialize
from graphene.shadow.adapters.claude_code import (
    CLAUDE_CODE_ADAPTER_VERSION,
    ClaudeCodeAdapter,
)
from graphene.shadow.events import ShadowEvent, session_sha256
from graphene.shadow.export import export_capsule
from graphene.shadow.ingest import _prepare_drafts, ingest_file
from graphene.shadow.lint import lint
from graphene.shadow.reconstruct import reconstruct
from graphene.shadow.redaction import REDACTED
from graphene.shadow.store import SHADOW_DB_FILENAME, ShadowStore
from graphene.shadow.verify import verify_capsule

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "shadow" / "claude-code" / "session_v1.jsonl"
HOME = Path("/home/dev")
SESSION = "11111111-2222-4333-8444-555555555555"
# The fixture's event stream, in seq order, after claims.v1 ran at ingest.
EXPECTED_KINDS = (
    "message",  # 1 user prompt
    "message",  # 2 agent text
    "file_read",  # 3 Read app/greet.py
    "tool_result",  # 4
    "file_edit",  # 5 Edit app/greet.py
    "tool_result",  # 6
    "message",  # 7 "I fixed the bug in the greeting."
    "claim",  # 8 inferred from 7, no check since the edit at 5
    "check_run",  # 9 pytest -q
    "check_result",  # 10 exit 0
    "message",  # 11 second user prompt (segment boundary)
    "network_op",  # 12 gh pr list with a fake token in the environment
    "command_result",  # 13 exit 1 parsed from "Exit code 1"
    "command_exec",  # 14 rm && sed -i && echo > outside
    "file_delete",  # 15 inferred notes/old.txt
    "file_edit",  # 16 inferred app/greet.py
    "file_create",  # 17 inferred ~/scratch/log.txt (outside the repository)
    "command_result",  # 18 exit 0
    "file_create",  # 19 Write tests/test_greet.py
    "tool_result",  # 20
    "tool_call",  # 21 TodoWrite (plan marker, segment boundary)
    "tool_result",  # 22
    "file_read",  # 23 Read tests/test_greet.py (read after write)
    "tool_result",  # 24
    "check_run",  # 25 uv run pytest
    "check_result",  # 26 exit 0
    "message",  # 27 "Done. All tests pass. ..."
    "claim",  # 28 inferred from 27, backed by 26
    "message",  # 29 isMeta user record -> system actor
    "unknown",  # 30 a record type the adapter has never seen
)
EXPECTED_SKIPPED = {
    "ai-title": 1,
    "atis-latch": 1,
    "attachment": 1,
    "file-history-snapshot": 1,
    "last-prompt": 1,
    "mode": 1,
    "permission-mode": 1,
    "queue-operation": 1,
    "system:turn_duration": 1,
    "thinking": 1,
}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _lines(*records: object) -> bytes:
    return b"".join(json.dumps(record).encode("utf-8") + b"\n" for record in records)


def _envelope(kind: str, uuid: str, parent: str | None, **extra: object) -> dict:
    record: dict[str, object] = {
        "parentUuid": parent,
        "isSidechain": False,
        "userType": "external",
        "cwd": "/home/dev/proj",
        "sessionId": SESSION,
        "version": "2.1.241",
        "gitBranch": "main",
        "entrypoint": "cli",
        "type": kind,
        "uuid": uuid,
        "timestamp": "2026-08-23T10:00:00.000Z",
    }
    record.update(extra)
    return record


def _user(text: object, uuid: str = "u1", parent: str | None = None, **extra: object):
    return _envelope(
        "user", uuid, parent, message={"role": "user", "content": text}, **extra
    )


def _assistant(blocks: object, uuid: str = "a1", parent: str | None = "u1", **extra):
    message = {"role": "assistant", "type": "message", "content": blocks}
    return _envelope("assistant", uuid, parent, message=message, **extra)


def _tool_use(call: str, name: str, inputs: dict) -> dict:
    return {"type": "tool_use", "id": call, "name": name, "input": inputs}


def _tool_result(call: str, content: object = "ok", **extra: object) -> dict:
    block: dict[str, object] = {
        "type": "tool_result",
        "tool_use_id": call,
        "content": content,
    }
    block.update(extra)
    return _user([block], uuid="r1", parent="a1")


def _parse(data: bytes, repo: Path | None = None):
    return ClaudeCodeAdapter(home=HOME).parse(data, repo=repo)


def _events(data: bytes, repo: Path | None = None) -> tuple[ShadowEvent, ...]:
    parsed = _parse(data, repo)
    return materialize(parsed.session_id, _prepare_drafts(parsed))


def _rejects(data: bytes, message: str) -> None:
    with pytest.raises(AdapterError, match=re.escape(message)):
        _parse(data)


@pytest.fixture
def store(tmp_path: Path) -> ShadowStore:
    return ShadowStore(tmp_path / SHADOW_DB_FILENAME)


@pytest.fixture
def fixture_events() -> tuple[ShadowEvent, ...]:
    return _events(FIXTURE.read_bytes())


# -- registry and fixture ----------------------------------------------------


def test_adapter_is_registered_with_its_version() -> None:
    adapter = ADAPTERS["claude-code"]
    assert isinstance(adapter, ClaudeCodeAdapter)
    assert (adapter.name, adapter.version) == (
        "claude-code",
        CLAUDE_CODE_ADAPTER_VERSION,
    )


def test_fixture_is_synthetic_and_lf_terminated() -> None:
    data = FIXTURE.read_bytes()
    assert data.endswith(b"\n") and b"\r" not in data
    assert b"/Users/" not in data and b"alexlopez" not in data
    assert data.count(b"\n") == 35


def test_fixture_yields_the_expected_kinds_in_order(
    fixture_events: tuple[ShadowEvent, ...],
) -> None:
    assert tuple(event.kind for event in fixture_events) == EXPECTED_KINDS
    assert [event.seq for event in fixture_events] == list(range(1, 31))
    assert {event.session_id for event in fixture_events} == {SESSION}
    assert all(
        (event.source.adapter, event.source.adapter_version)
        == ("claude-code", CLAUDE_CODE_ADAPTER_VERSION)
        for event in fixture_events
    )


def test_fixture_parse_counts_every_record(tmp_path: Path) -> None:
    parsed = _parse(FIXTURE.read_bytes())
    assert parsed.session_id == SESSION
    assert parsed.raw_record_count == 35
    assert parsed.unknown_count == 1
    assert parsed.has_claims is False
    assert dict(parsed.skipped) == EXPECTED_SKIPPED
    # every record is one observed draft or one counted skip; the three
    # inferred drafts come from the shell command at line 22
    observed = sum(1 for draft in parsed.drafts if draft.provenance == "observed")
    assert observed + sum(EXPECTED_SKIPPED.values()) == 35
    assert len(parsed.drafts) - observed == 3


def test_tool_calls_carry_paths_digests_and_results_but_never_content(
    fixture_events: tuple[ShadowEvent, ...],
) -> None:
    by_seq = {event.seq: event for event in fixture_events}
    assert (by_seq[3].tool, by_seq[3].call_id, by_seq[3].paths) == (
        "Read",
        "toolu_01AAAA",
        ("app/greet.py",),
    )
    assert by_seq[3].content_digest is None
    assert by_seq[5].content_digest == _sha256("return greeting")
    assert by_seq[19].content_digest == _sha256("def test_greet():\n    assert True\n")
    assert (by_seq[4].actor, by_seq[4].call_id, by_seq[4].exit_code) == (
        "tool",
        "toolu_01AAAA",
        None,
    )
    assert by_seq[4].content_digest == _sha256(
        "     1\tdef greet():\n     2\t    return 'hi'\n"
    )
    assert (by_seq[9].check_family, by_seq[9].argv_excerpt) == (
        "pytest",
        "cd ~/proj && pytest -q",
    )
    assert by_seq[9].argv_digest == _sha256("cd /home/dev/proj && pytest -q")
    assert (by_seq[10].exit_code, by_seq[10].check_family, by_seq[10].argv_digest) == (
        0,
        "pytest",
        by_seq[9].argv_digest,
    )
    assert (by_seq[13].kind, by_seq[13].exit_code) == ("command_result", 1)
    assert by_seq[18].content_digest is None  # empty result text has no digest
    assert by_seq[21].tool == "TodoWrite"
    assert by_seq[29].actor == "system"
    assert (by_seq[30].actor, by_seq[30].source.raw_type) == ("system", "future-record")
    serialized = json.dumps([event.to_record() for event in fixture_events])
    for content in (
        "return greeting",
        "assert True",
        "return 'hi'",
        "hidden reasoning",
    ):
        assert content not in serialized


def test_inferred_file_operations_cite_the_observed_command(
    fixture_events: tuple[ShadowEvent, ...],
) -> None:
    by_seq = {event.seq: event for event in fixture_events}
    command = by_seq[14]
    assert command.provenance == "observed" and command.derived_from == ()
    assert [(e.kind, e.paths, e.outside_paths) for e in fixture_events[14:17]] == [
        ("file_delete", ("notes/old.txt",), ()),
        ("file_edit", ("app/greet.py",), ()),
        ("file_create", (), ("~/scratch/log.txt",)),
    ]
    for inferred in fixture_events[14:17]:
        assert inferred.provenance == "inferred"
        assert inferred.derived_from == (command.event_id,)
        assert inferred.call_id == command.call_id == "toolu_01EEEE"


def test_redaction_scrubs_the_fake_token_and_collapses_the_fake_home(
    fixture_events: tuple[ShadowEvent, ...],
) -> None:
    serialized = json.dumps([event.to_record() for event in fixture_events])
    assert "ghp_" not in serialized and "FAKEFAKE" not in serialized
    assert "/home/dev" not in serialized
    by_seq = {event.seq: event for event in fixture_events}
    assert by_seq[12].argv_excerpt == f"{REDACTED} gh pr list --repo example/proj"
    assert (
        by_seq[27].excerpt
        == "Done. All tests pass. I left the log at ~/scratch/log.txt."
    )
    assert by_seq[27].content_digest == _sha256(
        "Done. All tests pass. I left the log at /home/dev/scratch/log.txt."
    )


def test_read_after_write_edges_and_segments(
    fixture_events: tuple[ShadowEvent, ...],
) -> None:
    graph = reconstruct(fixture_events)
    assert [
        (s.segment_id, s.boundary, s.start_seq, s.end_seq) for s in graph.segments
    ] == [
        ("seg_0001", "session_start", 1, 10),
        ("seg_0002", "user_message", 11, 20),
        ("seg_0003", "plan_marker", 21, 30),
    ]
    assert [(e.src, e.dst, e.paths) for e in graph.edges] == [
        ("seg_0001", "seg_0002", ("app/greet.py",)),
        ("seg_0002", "seg_0003", ("tests/test_greet.py",)),
    ]
    assert graph.unknown_count == 1


def test_claims_are_extracted_and_linted_against_checks(
    fixture_events: tuple[ShadowEvent, ...],
) -> None:
    claims = [event for event in fixture_events if event.kind == "claim"]
    assert [(c.seq, c.claim.category, c.excerpt) for c in claims if c.claim] == [
        (8, "fixed", "I fixed the bug in the greeting"),
        (28, "checks_pass", "All tests pass"),
    ]
    report = lint(fixture_events, reconstruct(fixture_events))
    ratios = {
        ratio.key: (ratio.numerator, ratio.denominator) for ratio in report.ratios
    }
    assert ratios == {
        "covered_files": (2, 2),
        "backed_claims": (1, 2),
        "overlap_segments": (2, 3),
    }
    findings = {(finding.rule, finding.seqs) for finding in report.findings}
    assert findings == {
        ("claimed-without-evidence", (7, 8)),
        ("scope-drift", (17,)),
        ("write-overlap", (5, 16)),
        ("network-or-install", (12,)),
    }
    assert report.rule_counts["destructive-unverified"] == 0
    assert report.rule_counts["edit-without-check"] == 0


def test_repo_flag_overrides_the_record_cwd(tmp_path: Path) -> None:
    events = _events(FIXTURE.read_bytes(), repo=tmp_path)
    assert not any(event.paths for event in events)
    read = next(event for event in events if event.kind == "file_read")
    assert read.outside_paths == ("~/proj/app/greet.py",)


def test_adapter_home_defaults_to_the_current_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: HOME))
    events = materialize(
        SESSION,
        _prepare_drafts(ClaudeCodeAdapter().parse(FIXTURE.read_bytes(), repo=None)),
    )
    assert events[8].argv_excerpt == "cd ~/proj && pytest -q"


# -- mapping of hand-built records --------------------------------------------


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ({"is_error": False}, 0),
        ({"is_error": True}, 1),
        ({"is_error": True, "content": "Exit code 2\nboom"}, 2),
        ({"is_error": True, "content": [{"type": "text", "text": "Exit code 3"}]}, 3),
        ({}, None),
    ],
)
def test_exit_codes_follow_is_error_and_the_exit_code_line(
    extra: dict, expected: int | None
) -> None:
    data = _lines(
        _user("go"),
        _assistant([_tool_use("c1", "Bash", {"command": "make build"})]),
        _tool_result("c1", **extra),
    )
    result = _events(data)[-1]
    assert (result.kind, result.tool, result.exit_code) == (
        "command_result",
        "Bash",
        expected,
    )


def test_results_for_non_bash_tools_are_tool_results() -> None:
    data = _lines(
        _user("go"),
        _assistant(
            [_tool_use("c1", "Grep", {"pattern": "x", "path": "/home/dev/proj/src"})]
        ),
        _tool_result("c1", is_error=False),
    )
    call, result = _events(data)[1:]
    assert (call.kind, call.tool, call.paths) == ("tool_call", "Grep", ("src",))
    assert (result.kind, result.tool, result.exit_code) == ("tool_result", "Grep", 0)


@pytest.mark.parametrize(
    ("name", "inputs", "kind", "paths", "digest_of"),
    [
        (
            "Write",
            {"file_path": "/home/dev/proj/a.py", "content": "x"},
            "file_create",
            ("a.py",),
            "x",
        ),
        (
            "MultiEdit",
            {
                "file_path": "/home/dev/proj/a.py",
                "edits": [{"old_string": "a", "new_string": "b"}],
            },
            "file_edit",
            ("a.py",),
            None,
        ),
        (
            "NotebookEdit",
            {"notebook_path": "/home/dev/proj/n.ipynb", "new_source": "y"},
            "file_edit",
            ("n.ipynb",),
            "y",
        ),
        ("WebFetch", {"url": "https://example.test"}, "network_op", (), None),
        ("WebSearch", {"query": "q"}, "network_op", (), None),
        ("AskUserQuestion", {"questions": []}, "tool_call", (), None),
        ("mcp__server__tool", {"arg": 1}, "tool_call", (), None),
    ],
)
def test_tool_names_map_to_kinds(
    name: str, inputs: dict, kind: str, paths: tuple[str, ...], digest_of: str | None
) -> None:
    call = _events(_lines(_user("go"), _assistant([_tool_use("c1", name, inputs)])))[-1]
    assert (call.kind, call.tool, call.paths, call.call_id) == (kind, name, paths, "c1")
    if digest_of is not None:
        assert call.content_digest == _sha256(digest_of)
    elif name == "MultiEdit":
        assert call.content_digest is not None
    else:
        assert call.content_digest is None


def test_bash_kinds_follow_classify_v1() -> None:
    commands = {
        "pip install requests": ("install_op", None),
        "git commit -m x": ("vcs_op", None),
        "curl https://example.test": ("network_op", None),
        "npm test": ("check_run", "npm-test"),
        "ls -la": ("command_exec", None),
    }
    for command, (kind, family) in commands.items():
        data = _lines(
            _user("go"), _assistant([_tool_use("c1", "Bash", {"command": command})])
        )
        call = _events(data)[-1]
        assert (call.kind, call.check_family) == (kind, family), command
        assert call.argv_digest == _sha256(command)


def test_unclassifiable_records_become_unknown_events_not_drops() -> None:
    data = _lines(
        _user("go"),
        _envelope("system", "s1", "u1", subtype="compact_boundary"),
        _user([{"type": "image", "source": {}}], uuid="u2", parent="s1"),
        _tool_result("dangling", is_error=True),
        {"type": "brand-new", "sessionId": SESSION},
    )
    parsed = _parse(data)
    events = _events(data)
    assert parsed.unknown_count == 4 and parsed.raw_record_count == 5
    assert [(e.kind, e.actor, e.source.raw_type) for e in events[1:]] == [
        ("unknown", "system", "system:compact_boundary"),
        ("unknown", "system", "user.image"),
        ("unknown", "tool", "tool_result"),
        ("unknown", "system", "brand-new"),
    ]
    assert (events[3].call_id, events[3].exit_code) == ("dangling", 1)


def test_thinking_and_bookkeeping_are_counted_not_ingested() -> None:
    data = _lines(
        {"type": "summary", "summary": "t", "leafUuid": "x"},
        _user("go"),
        _assistant([{"type": "thinking", "thinking": "secret plan", "signature": "s"}]),
        _assistant([{"type": "text", "text": "hello"}], uuid="a2", parent="a1"),
    )
    parsed = _parse(data)
    assert dict(parsed.skipped) == {"summary": 1, "thinking": 1}
    assert "secret plan" not in json.dumps([e.to_record() for e in _events(data)])


def test_missing_timestamp_and_sidechain_records_are_accepted() -> None:
    record = _user("go")
    del record["timestamp"]
    events = _events(_lines(record))
    assert events[0].ts is None


def test_resumed_session_parent_outside_the_file_is_accepted() -> None:
    events = _events(_lines(_user("go", parent="not-in-this-file")))
    assert events[0].kind == "message"


# -- fail-closed rules ---------------------------------------------------------


def test_bom_invalid_utf8_blank_line_and_cr_are_rejected() -> None:
    good = _lines(_user("go"))
    _rejects(b"\xef\xbb\xbf" + good, "line 1: UTF-8 BOM is not allowed")
    _rejects(good + b"\xff\n", "line 2: invalid UTF-8")
    _rejects(good + b"\n" + good, "line 2: blank line")
    _rejects(good[:-1] + b"\r\n", "line 1: CR line ending")
    _rejects(b"", "line 1: empty input")


def test_malformed_and_non_object_json_are_rejected() -> None:
    _rejects(b"{not json}\n", "line 1: invalid JSON")
    _rejects(b"[1, 2]\n", "line 1: record is not a JSON object")
    _rejects(b'"text"\n', "line 1: record is not a JSON object")


def test_oversized_line_and_deep_nesting_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graphene.shadow.adapters import claude_code

    monkeypatch.setattr(claude_code, "MAX_LINE_CHARS", 64)
    _rejects(_lines(_user("x" * 100)), "line 1: line exceeds 64 characters")
    monkeypatch.setattr(claude_code, "MAX_LINE_CHARS", 16 * 1024 * 1024)
    deep = _user("go")
    deep["extra"] = json.loads("[" * 30 + "]" * 30)
    _rejects(_lines(deep), "line 1: record nests containers deeper than 24 levels")
    _rejects(b"[" * 100_000 + b"]" * 100_000 + b"\n", "line 1: invalid JSON")


def test_type_field_is_required_and_must_be_a_short_string() -> None:
    record = _user("go")
    del record["type"]
    _rejects(_lines(record), 'line 1: missing field "type"')
    _rejects(
        _lines({**_user("go"), "type": 7}), 'line 1: field "type" must be a string'
    )
    _rejects(
        _lines({**_user("go"), "type": "a\x1bb"}),
        'line 1: field "type" must be 1-128 printable characters',
    )


def test_session_id_rules() -> None:
    _rejects(
        _lines({**_user("go"), "sessionId": "bad id!"}),
        'line 1: field "sessionId" must match [A-Za-z0-9._-]{1,128}',
    )
    _rejects(
        _lines(
            _user("go"), {**_user("more", uuid="u2", parent="u1"), "sessionId": "other"}
        ),
        f'line 2: sessionId changed from "{SESSION}" to "other"',
    )
    record = _user("go")
    del record["sessionId"]
    _rejects(_lines(record), "no record carries a sessionId")


def test_parent_uuid_may_not_refer_to_a_later_record() -> None:
    first = _user("go", uuid="u1", parent="u2")
    second = _user("more", uuid="u2", parent="u1")
    _rejects(
        _lines(first, second), 'line 1: field "parentUuid" refers to a later record'
    )


def test_message_shape_rules() -> None:
    _rejects(
        _lines(_envelope("user", "u1", None, message="text")),
        'line 1: field "message" must be an object',
    )
    _rejects(
        _lines(_user(7)),
        'line 1: field "message.content" must be a string or an array of blocks',
    )
    _rejects(_lines(_user(["text"])), "line 1: block 0 is not an object")
    _rejects(
        _lines(_user([{"text": "x"}])), 'line 1: block 0 field "type" must be a string'
    )
    _rejects(
        _lines(_user([{"type": "text", "text": 5}])),
        'line 1: block 0 field "text" must be a string',
    )


def test_tool_use_shape_rules() -> None:
    base = _user("go")
    _rejects(
        _lines(base, _assistant([{"type": "tool_use", "name": "Read", "input": {}}])),
        'line 2: block 0 field "id" must be a string',
    )
    _rejects(
        _lines(base, _assistant([{"type": "tool_use", "id": "c1", "input": {}}])),
        'line 2: block 0 field "name" must be a string',
    )
    _rejects(
        _lines(base, _assistant([_tool_use("c1", "x" * 65, {})])),
        'line 2: block 0 field "name" must be 1-64 printable characters',
    )
    _rejects(
        _lines(
            base,
            _assistant([{"type": "tool_use", "id": "c1", "name": "Read", "input": 1}]),
        ),
        'line 2: block 0 field "input" must be an object',
    )
    _rejects(
        _lines(base, _assistant([_tool_use("c1", "Bash", {})])),
        'line 2: block 0 field "input.command" must be a string',
    )
    _rejects(
        _lines(base, _assistant([_tool_use("c1", "Edit", {"new_string": "x"})])),
        'line 2: block 0 field "input.file_path" must be a string',
    )
    _rejects(
        _lines(
            base,
            _assistant(
                [_tool_use("c1", "Read", {"file_path": "/home/dev/proj/a\x00b"})]
            ),
        ),
        'line 2: block 0 field "input.file_path" is not a usable path',
    )
    _rejects(
        _lines(
            base,
            _assistant([_tool_use("c1", "Read", {"file_path": "/x/" + "y" * 5000})]),
        ),
        'line 2: block 0 field "input.file_path" is not a usable path',
    )
    _rejects(
        _lines(
            base,
            _user([{"type": "tool_result", "content": "x"}], uuid="u2", parent="u1"),
        ),
        'line 2: block 0 field "tool_use_id" must be a string',
    )


def test_timestamp_rules_name_the_line() -> None:
    _rejects(
        _lines({**_user("go"), "timestamp": "2026-08-23 10:00:00"}),
        'line 1: field "timestamp" must be an RFC 3339 UTC timestamp',
    )
    # Shape-valid but calendar-invalid: refused by ShadowEvent, located by the
    # record reference that materialize appends.
    with pytest.raises(AdapterError, match=re.escape("(at line:1)")):
        _events(_lines({**_user("go"), "timestamp": "2026-13-01T00:00:00Z"}))


def test_parse_rejects_non_bytes_and_non_path_repo() -> None:
    with pytest.raises(AdapterError, match="must be bytes"):
        ClaudeCodeAdapter().parse("{}", repo=None)  # type: ignore[arg-type]
    with pytest.raises(AdapterError, match="repo must be a Path or None"):
        ClaudeCodeAdapter().parse(b"{}\n", repo="x")  # type: ignore[arg-type]


def test_rejection_persists_nothing(store: ShadowStore, tmp_path: Path) -> None:
    broken = tmp_path / "broken.jsonl"
    broken.write_bytes(FIXTURE.read_bytes() + b"{not json}\n")
    with pytest.raises(AdapterError, match="line 36: invalid JSON"):
        ingest_file(store, broken, fmt="claude-code", repo=None)
    assert store.sessions() == []


# -- ingest, CLI, capsule ----------------------------------------------------------


def test_ingest_records_skipped_types_in_the_summary(store: ShadowStore) -> None:
    result = ingest_file(store, FIXTURE, fmt="claude-code", repo=None)
    assert (result.adapter, result.adapter_version) == (
        "claude-code",
        CLAUDE_CODE_ADAPTER_VERSION,
    )
    assert (result.event_count, result.observed_count, result.inferred_count) == (
        30,
        25,
        5,
    )
    assert (result.claim_count, result.unknown_count) == (2, 1)
    summary = store.session(result.shadow_id).summary
    assert summary["raw_record_count"] == 35
    assert summary["skipped_records"] == EXPECTED_SKIPPED
    assert summary["has_source_claims"] is False
    again = ingest_file(store, FIXTURE, fmt="claude-code", repo=None)
    assert (again.created, again.shadow_id) == (False, result.shadow_id)


def _run(
    capsys: pytest.CaptureFixture[str], argv: Sequence[str]
) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_cli_ingest_report_lint_export_verify_on_the_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(state))

    code, out, err = _run(
        capsys, ["shadow", "ingest", str(FIXTURE), "--format", "claude-code"]
    )
    assert (code, err) == (0, "")
    match = re.search(r"shadow_id=(shadow_[0-9a-f]{32}) .*claims=2 unknown=1 ", out)
    assert match is not None
    shadow_id = match.group(1)

    code, out, err = _run(capsys, ["shadow", "report", shadow_id, "--json"])
    assert (code, err) == (0, "")
    report = json.loads(out)
    assert report["shadow"]["adapter"] == "claude-code"
    assert report["graph_summary"] == {
        "segments_version": "segments.v1",
        "session_id": SESSION,
        "event_count": 30,
        "observed_count": 25,
        "inferred_count": 5,
        "unknown_count": 1,
        "segments": 3,
        "edges": 2,
    }
    assert report["rule_counts"] == {
        "claimed-without-evidence": 1,
        "edit-without-check": 0,
        "write-overlap": 1,
        "scope-drift": 1,
        "destructive-unverified": 0,
        "network-or-install": 1,
    }
    assert "ghp_" not in out and "hidden reasoning" not in out

    code, out, err = _run(
        capsys, ["shadow", "lint", shadow_id, "--rule", "scope-drift"]
    )
    assert (code, err) == (0, "")
    assert "findings=1" in out and "[scope-drift]" in out

    code, out, err = _run(
        capsys, ["shadow", "export", shadow_id, "--output", str(tmp_path)]
    )
    assert (code, err) == (0, "")
    capsule = tmp_path / f"{shadow_id}.graphene-shadow"
    verified = verify_capsule(capsule)
    assert verified["verified"] is True and verified["shadow_id"] == shadow_id

    code, out, err = _run(capsys, ["shadow", "verify", shadow_id])
    assert (code, err) == (0, "")
    assert "verified=True" in out

    # The capsule round-trips through the open format to the same session
    # digest; the shadow id differs because it binds the ingesting adapter.
    code, out, err = _run(
        capsys,
        ["shadow", "ingest", str(capsule / "events.ndjson"), "--format", "ndjson"],
    )
    assert (code, err) == (0, "")
    store = ShadowStore(state / SHADOW_DB_FILENAME)
    sessions = {record.adapter: record for record in store.sessions()}
    assert set(sessions) == {"claude-code", "ndjson"}
    assert sessions["ndjson"].shadow_id != shadow_id
    original = store.events(shadow_id)
    reingested = store.events(sessions["ndjson"].shadow_id)
    assert [e.event_id for e in original] == [e.event_id for e in reingested]
    assert session_sha256(e.event_id for e in original) == verified["session_sha256"]


def test_export_capsule_api_on_the_fixture(store: ShadowStore, tmp_path: Path) -> None:
    result = ingest_file(store, FIXTURE, fmt="claude-code", repo=None)
    exported = export_capsule(store, result.shadow_id, tmp_path / "out")
    capsule = Path(str(exported["capsule_dir"]))
    assert verify_capsule(capsule)["verified"] is True
    # The registered adapter collapses the real home, not the fixture's invented
    # one; the secret and the hidden reasoning must still be absent.
    events_text = (capsule / "events.ndjson").read_text()
    assert "ghp_" not in events_text and "hidden reasoning" not in events_text
