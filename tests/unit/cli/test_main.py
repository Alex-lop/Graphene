from __future__ import annotations

import importlib
import json
import os
import sqlite3
import tomllib
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from graphene.cli.main import build_parser, main
from graphene.hashing import canonical_json_bytes, sha256_hex
from graphene.lineage import SQLiteArtifactStore, SQLiteLineageStore
from graphene.models import (
    EventInput,
    EvidenceKind,
    LineageAuthority,
    LineageEventType,
    SourceKind,
    SourceReference,
    TruthKind,
    VerifiedHead,
)

cli_main = importlib.import_module("graphene.cli.main")
ROOT = Path(__file__).parents[3]
RUN_ID = "run_cli_001"


def _source(
    artifacts: SQLiteArtifactStore,
    kind: SourceKind,
    label: str,
) -> SourceReference:
    evidence_kind = {
        SourceKind.TOOL_RECEIPT: EvidenceKind.TOOL_RECEIPT,
        SourceKind.POLICY_EVALUATION: EvidenceKind.POLICY_RECEIPT,
    }.get(kind, EvidenceKind.OPERATOR_REQUEST)
    reference = artifacts(evidence_kind, {"schema_version": 2, "label": label})
    return SourceReference(kind=kind, id=reference.id, sha256=reference.sha256)


def _database(tmp_path: Path):
    path = tmp_path / "lineage.sqlite3"
    artifacts = SQLiteArtifactStore(path)
    store = SQLiteLineageStore(path, artifact_resolver=artifacts.resolve)
    head = VerifiedHead(run_id=RUN_ID, seq=0, event_sha256=None, event_count=0)

    start = store.append(
        RUN_ID,
        head,
        "cli_event_start_001",
        EventInput(
            session_id=None,
            invocation_id=None,
            model_id=None,
            tool_call_id=None,
            repo_id="graphene-demo",
            base_sha="a" * 40,
            agent_profile_id="auth-maintainer@1",
            policy_revision=1,
            event_type=LineageEventType.RUN_STARTED,
            truth_kind=TruthKind.SERVER_DERIVED,
            authority=LineageAuthority.LIFECYCLE_SERVICE,
            references=(),
            source_ref=_source(artifacts, SourceKind.LIFECYCLE_REQUEST, "start"),
            payload={"state": "STARTING"},
        ),
    )
    head = VerifiedHead(
        run_id=RUN_ID,
        seq=start.seq,
        event_sha256=start.event_sha256,
        event_count=start.seq,
    )
    started = store.append(
        RUN_ID,
        head,
        "cli_event_read_start_001",
        EventInput(
            session_id="session_cli_001",
            invocation_id="invocation_cli_001",
            model_id="model-test",
            tool_call_id="call_read_001",
            repo_id="graphene-demo",
            base_sha="a" * 40,
            agent_profile_id="auth-maintainer@1",
            policy_revision=1,
            event_type=LineageEventType.TOOL_STARTED,
            truth_kind=TruthKind.RUNTIME_OBSERVED,
            authority=LineageAuthority.SCOPED_TOOL_WRAPPER,
            references=(),
            source_ref=_source(artifacts, SourceKind.TOOL_RECEIPT, "read-start"),
            payload={"operation": "read_file", "status": "started"},
        ),
    )
    head = VerifiedHead(
        run_id=RUN_ID,
        seq=started.seq,
        event_sha256=started.event_sha256,
        event_count=started.seq,
    )
    completed = store.append(
        RUN_ID,
        head,
        "cli_event_read_done_001",
        EventInput(
            session_id="session_cli_001",
            invocation_id="invocation_cli_001",
            model_id="model-test",
            tool_call_id="call_read_001",
            repo_id="graphene-demo",
            base_sha="a" * 40,
            agent_profile_id="auth-maintainer@1",
            policy_revision=1,
            event_type=LineageEventType.TOOL_COMPLETED,
            truth_kind=TruthKind.RUNTIME_OBSERVED,
            authority=LineageAuthority.SCOPED_TOOL_WRAPPER,
            references=(),
            source_ref=_source(artifacts, SourceKind.TOOL_RECEIPT, "read-done"),
            payload={
                "operation": "read_file",
                "status": "completed",
                "path": "app/auth/limiter.py",
                "file_version_id": "f" * 64,
                "byte_count": 1700,
                "line_count": 58,
            },
        ),
    )
    return path, (start, started, completed)


def _append_access_denied(path: Path, previous) -> object:
    artifacts = SQLiteArtifactStore(path)
    store = SQLiteLineageStore(path, artifact_resolver=artifacts.resolve)
    return store.append(
        RUN_ID,
        VerifiedHead(
            run_id=RUN_ID,
            seq=previous.seq,
            event_sha256=previous.event_sha256,
            event_count=previous.seq,
        ),
        "cli_event_scope_denied_001",
        EventInput(
            session_id="session_cli_001",
            invocation_id="invocation_cli_001",
            model_id="model-test",
            tool_call_id="call_denied_001",
            repo_id="graphene-demo",
            base_sha="a" * 40,
            agent_profile_id="auth-maintainer@1",
            policy_revision=1,
            event_type=LineageEventType.SCOPE_DENIED,
            truth_kind=TruthKind.POLICY_AUTHORITATIVE,
            authority=LineageAuthority.POLICY_ENGINE,
            references=(),
            source_ref=_source(
                artifacts,
                SourceKind.POLICY_EVALUATION,
                "scope-denied",
            ),
            payload={
                "operation": "read_file",
                "reason_code": "outside_runtime_scope",
                "status": "denied",
            },
        ),
    )


@pytest.mark.parametrize(
    ("argv", "command", "memory_action"),
    [
        (
            ["run", "baseline_max_attempts", "--profile", "platform-maintainer@1"],
            "run",
            None,
        ),
        (
            ["watch", RUN_ID, "--after-seq", "4", "--snapshot"],
            "watch",
            None,
        ),
        (["inspect", "event_001", "--run", RUN_ID], "inspect", None),
        (["why", "app/auth/limiter.py", "--run", RUN_ID], "why", None),
        (["replay", RUN_ID, "--speed", "8"], "replay", None),
        (["review", RUN_ID], "review", None),
        (
            [
                "feedback",
                "hunk_001",
                "--event",
                "event_001",
                "--run",
                RUN_ID,
                "--message",
                "Keep the security check.",
            ],
            "feedback",
            None,
        ),
        (["answer", "question_001", "--choice", "all_auth"], "answer", None),
        (["memory", "approve", "mem_auth_review@1"], "memory", "approve"),
        (["memory", "reject", "mem_auth_review@1"], "memory", "reject"),
        (
            [
                "handoff",
                RUN_ID,
                "--to",
                "auth-maintainer@1",
                "--task",
                "adapted_window_seconds",
                "--start",
            ],
            "handoff",
            None,
        ),
        (
            ["promote", "run_consumer_001", "--decision", "commit"],
            "promote",
            None,
        ),
        (
            ["demo", "--driver", "scripted-local", "--no-open", "--speed", "8"],
            "demo",
            None,
        ),
    ],
)
def test_parser_accepts_the_frozen_command_grammar(argv, command, memory_action):
    parsed = build_parser().parse_args(argv)

    assert parsed.command == command
    assert getattr(parsed, "memory_action", None) == memory_action


def test_parser_has_only_environment_database_and_credential_boundaries():
    parser = build_parser()

    for option in ("--db", "--database", "--token"):
        with pytest.raises(SystemExit):
            parser.parse_args(["watch", RUN_ID, option, "forbidden"])
    for speed in ("0", "-1", "nan", "inf"):
        with pytest.raises(SystemExit):
            parser.parse_args(["replay", RUN_ID, "--speed", speed])
    for after_seq in ("-1", "1.0", "01"):
        with pytest.raises(SystemExit):
            parser.parse_args(["watch", RUN_ID, "--after-seq", after_seq])


def test_project_installs_the_graphene_console_entry_point():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]

    assert project["scripts"] == {
        "graphene": "graphene.cli.main:main",
        "graphene-mcp": "graphene.integrations.stdio:main",
    }


def test_demo_owns_its_database_and_forwards_options(monkeypatch):
    demo = importlib.import_module("graphene.demo")
    received = {}

    def run_demo(**options):
        received.update(options)
        return 0

    monkeypatch.delenv("GRAPHENE_LINEAGE_DB", raising=False)
    monkeypatch.setattr(demo, "run_demo", run_demo)

    assert (
        main(
            [
                "demo",
                "--no-open",
                "--cleanup",
                "--speed",
                "4",
                "--exit-after-demo",
                "--automated-fixture",
            ]
        )
        == 0
    )
    assert received == {
        "driver": "scripted-local",
        "speed": 4.0,
        "no_open": True,
        "cleanup": True,
        "keep_open": False,
        "automated_fixture": True,
    }


def test_json_watch_is_canonical_event_only_ndjson(tmp_path, monkeypatch, capsys):
    path, events = _database(tmp_path)
    monkeypatch.setenv("GRAPHENE_LINEAGE_DB", str(path))

    assert (
        main(
            [
                "--json",
                "watch",
                RUN_ID,
                "--after-seq",
                "1",
                "--snapshot",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    lines = captured.out.splitlines()

    assert captured.err == ""
    assert captured.out == "".join(
        canonical_json_bytes(event.model_dump(mode="json")).decode() + "\n"
        for event in events[1:]
    )
    assert [json.loads(line)["seq"] for line in lines] == [2, 3]
    assert not captured.out.startswith(("RUN ", "EVENT ", "Graphene"))
    assert "\x1b[" not in captured.out

    assert (
        main(
            [
                "--json",
                "watch",
                RUN_ID,
                "--after-seq",
                "4",
                "--snapshot",
            ]
        )
        == 1
    )
    inconsistent = capsys.readouterr()
    assert inconsistent.out == ""
    assert "EVIDENCE_INVALID" in inconsistent.err
    assert "exceeds the verified head" in inconsistent.err


def test_watch_follows_monotonic_suffix_until_terminal_state(
    tmp_path,
    monkeypatch,
    capsys,
):
    path, events = _database(tmp_path)
    monkeypatch.setenv("GRAPHENE_LINEAGE_DB", str(path))
    polls = []

    def append_terminal(delay):
        polls.append(delay)
        _append_access_denied(path, events[-1])

    monkeypatch.setattr(cli_main.time, "sleep", append_terminal)
    assert main(["--json", "watch", RUN_ID, "--after-seq", "3"]) == 0
    captured = capsys.readouterr()
    rendered = [json.loads(line) for line in captured.out.splitlines()]

    assert captured.err == ""
    assert polls == [0.05]
    assert [item["seq"] for item in rendered] == [4]
    assert rendered[-1]["event_type"] == "scope.denied"


def test_watch_detects_database_replacement_and_ctrl_c_is_read_only(
    tmp_path,
    monkeypatch,
    capsys,
):
    path, _ = _database(tmp_path)
    monkeypatch.setenv("GRAPHENE_LINEAGE_DB", str(path))
    replacement = tmp_path / "replacement.sqlite3"
    replacement.write_bytes(path.read_bytes())

    def replace_database(_delay):
        os.replace(replacement, path)

    monkeypatch.setattr(cli_main.time, "sleep", replace_database)
    assert main(["--json", "watch", RUN_ID, "--after-seq", "3"]) == 1
    replaced = capsys.readouterr()
    assert replaced.out == ""
    assert "EVIDENCE_INVALID" in replaced.err
    assert "replaced" in replaced.err

    interrupt_root = tmp_path / "interrupt"
    interrupt_root.mkdir()
    path, _ = _database(interrupt_root)
    monkeypatch.setenv("GRAPHENE_LINEAGE_DB", str(path))
    before = path.read_bytes()
    before_events, _ = cli_main._load(path, RUN_ID)

    def interrupt(_delay):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli_main.time, "sleep", interrupt)
    assert main(["--json", "watch", RUN_ID, "--after-seq", "3"]) == 130
    interrupted = capsys.readouterr()
    assert interrupted.out == interrupted.err == ""
    after_events, _ = cli_main._load(path, RUN_ID)
    assert path.read_bytes() == before
    assert after_events == before_events


def test_replay_speed_drives_capped_committed_timeline_with_no_initial_delay(
    tmp_path,
    monkeypatch,
    capsys,
):
    first = datetime(2026, 8, 12, tzinfo=UTC)
    recorded = iter((first, first + timedelta(seconds=1), first + timedelta(seconds=5)))
    store_module = importlib.import_module("graphene.lineage.store")
    monkeypatch.setattr(store_module, "_now", lambda: next(recorded))
    path, _ = _database(tmp_path)
    events, projection = cli_main._load(path, RUN_ID)
    delays = []

    cli_main._replay(
        events,
        projection,
        speed=2,
        json_mode=False,
        sleeper=delays.append,
    )
    human = capsys.readouterr()

    assert delays == [0.5, 1.0]
    assert human.err == ""
    assert human.out.count("RUN ") == 1


def test_json_replay_flushes_each_committed_event(tmp_path, monkeypatch):
    path, events = _database(tmp_path)
    stream, projection = cli_main._load(path, RUN_ID)

    class Output:
        def __init__(self):
            self.value = ""
            self.flush_count = 0

        def write(self, value):
            self.value += value

        def flush(self):
            self.flush_count += 1

    output = Output()
    monkeypatch.setattr(cli_main.sys, "stdout", output)
    cli_main._replay(
        stream,
        projection,
        speed=1,
        json_mode=True,
        sleeper=lambda _delay: None,
    )

    assert output.flush_count == len(events)
    assert [json.loads(line)["seq"] for line in output.value.splitlines()] == [1, 2, 3]


def test_replay_is_restart_stable_and_does_not_mutate_the_database(
    tmp_path,
    monkeypatch,
    capsys,
):
    path, _ = _database(tmp_path)
    monkeypatch.setenv("GRAPHENE_LINEAGE_DB", str(path))
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    before = path.read_bytes()
    before_paths = set(tmp_path.iterdir())

    assert main(["--json", "replay", RUN_ID, "--speed", "1"]) == 0
    first = capsys.readouterr()
    assert main(["--json", "replay", RUN_ID, "--speed", "8"]) == 0
    second = capsys.readouterr()

    assert first.err == second.err == ""
    assert first.out == second.out
    assert sha256_hex(first.out.encode()) == sha256_hex(second.out.encode())
    assert path.read_bytes() == before
    assert set(tmp_path.iterdir()) - before_paths <= {
        path.with_name(path.name + "-shm"),
        path.with_name(path.name + "-wal"),
    }


def test_inspect_and_why_report_only_canonical_stored_observations(
    tmp_path,
    monkeypatch,
    capsys,
):
    path, events = _database(tmp_path)
    monkeypatch.setenv("GRAPHENE_LINEAGE_DB", str(path))

    assert main(["inspect", events[-1].event_id, "--run", RUN_ID]) == 0
    inspected = capsys.readouterr()
    assert inspected.err == ""
    inspected_payload = json.loads(inspected.out)
    assert inspected_payload["query"] == "inspect"
    assert inspected_payload["item"] == {
        "type": "event",
        "event": events[-1].model_dump(mode="json"),
    }
    assert canonical_json_bytes(inspected_payload).decode() + "\n" == inspected.out

    assert main(["--json", "why", "app/auth/limiter.py", "--run", RUN_ID]) == 0
    explained = capsys.readouterr()
    payload = json.loads(explained.out)
    assert explained.err == ""
    assert payload["path"] == "app/auth/limiter.py"
    assert payload["observations"] == [
        {
            "authority": "scoped_tool_wrapper",
            "event_id": events[-1].event_id,
            "event_type": "tool.completed",
            "operation": "read_file",
            "seq": 3,
            "status": "completed",
            "truth_kind": "runtime_observed",
        }
    ]
    assert payload["unknowns"] == [
        "Timing does not prove causality.",
        "Relationships without an explicit stored payload/reference binding are unknown.",
        "Whole-repository impact is unknown.",
    ]
    assert {item["relation"] for item in payload["relationships"]} == {"READ"}
    assert canonical_json_bytes(payload).decode() + "\n" == explained.out


def test_not_found_and_invalid_evidence_are_stderr_only(tmp_path, monkeypatch, capsys):
    empty_path = tmp_path / "empty.sqlite3"
    artifacts = SQLiteArtifactStore(empty_path)
    SQLiteLineageStore(empty_path, artifact_resolver=artifacts.resolve)
    monkeypatch.setenv("GRAPHENE_LINEAGE_DB", str(empty_path))

    assert main(["--json", "watch", "run_missing_001"]) != 0
    missing = capsys.readouterr()
    assert missing.out == ""
    assert "NOT_FOUND" in missing.err

    path, _ = _database(tmp_path)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            "UPDATE events SET event_sha256 = ? WHERE run_id = ? AND seq = 2",
            ("0" * 64, RUN_ID),
        )
        connection.commit()
    monkeypatch.setenv("GRAPHENE_LINEAGE_DB", str(path))

    assert main(["--json", "replay", RUN_ID, "--speed", "8"]) != 0
    invalid = capsys.readouterr()
    assert invalid.out == ""
    assert "EVIDENCE_INVALID" in invalid.err


def test_env_errors_do_not_echo_paths_or_credentials(tmp_path, monkeypatch, capsys):
    credential_canary = "Bearer CLI_CREDENTIAL_CANARY_7ea4"
    path_canary = str(tmp_path / "DB_PATH_CANARY_6bb9.sqlite3")
    monkeypatch.setenv("GRAPHENE_DEMO_TOKEN", credential_canary)
    monkeypatch.delenv("GRAPHENE_LINEAGE_DB", raising=False)

    assert main(["watch", RUN_ID]) != 0
    missing = capsys.readouterr()
    assert missing.out == ""
    assert "GRAPHENE_LINEAGE_DB" in missing.err
    assert credential_canary not in missing.err

    monkeypatch.setenv("GRAPHENE_LINEAGE_DB", path_canary)
    assert main(["watch", RUN_ID]) != 0
    absent = capsys.readouterr()
    assert absent.out == ""
    assert path_canary not in absent.err
    assert credential_canary not in absent.err

    blank = tmp_path / "blank.sqlite3"
    blank.write_bytes(b"")
    monkeypatch.setenv("GRAPHENE_LINEAGE_DB", str(blank))
    assert main(["replay", RUN_ID, "--speed", "8"]) != 0
    malformed = capsys.readouterr()
    assert malformed.out == ""
    assert blank.read_bytes() == b""
    assert not (tmp_path / "blank.sqlite3-wal").exists()
    assert not (tmp_path / "blank.sqlite3-shm").exists()


def test_run_requires_database_without_echoing_credentials(monkeypatch, capsys):
    credential_canary = "RUN_CREDENTIAL_CANARY_76fb"
    monkeypatch.setenv("GRAPHENE_DEMO_TOKEN", credential_canary)
    monkeypatch.delenv("GRAPHENE_LINEAGE_DB", raising=False)

    assert (
        main(
            [
                "--json",
                "run",
                "baseline_max_attempts",
                "--profile",
                "platform-maintainer@1",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "CONFIG_ERROR: GRAPHENE_LINEAGE_DB is required\n"
    assert credential_canary not in captured.err


def test_promote_requires_the_lineage_database(monkeypatch, capsys):
    monkeypatch.delenv("GRAPHENE_LINEAGE_DB", raising=False)
    assert main(["promote", "run_consumer_001", "--decision", "commit"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "CONFIG_ERROR: GRAPHENE_LINEAGE_DB is required\n"
