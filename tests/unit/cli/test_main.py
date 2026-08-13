from __future__ import annotations

import json
import sqlite3
import tomllib
from contextlib import closing
from pathlib import Path

import pytest
from graphene.cli.main import EXIT_UNAVAILABLE, build_parser, main
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

ROOT = Path(__file__).parents[3]
RUN_ID = "run_cli_001"


def _source(
    artifacts: SQLiteArtifactStore,
    kind: SourceKind,
    label: str,
) -> SourceReference:
    evidence_kind = (
        EvidenceKind.TOOL_RECEIPT
        if kind == SourceKind.TOOL_RECEIPT
        else EvidenceKind.OPERATOR_REQUEST
    )
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


@pytest.mark.parametrize(
    ("argv", "command", "memory_action"),
    [
        (
            ["run", "baseline_max_attempts", "--profile", "platform-maintainer@1"],
            "run",
            None,
        ),
        (["watch", RUN_ID], "watch", None),
        (["inspect", "event_001", "--run", RUN_ID], "inspect", None),
        (["why", "app/auth/limiter.py", "--run", RUN_ID], "why", None),
        (["replay", RUN_ID, "--speed", "8"], "replay", None),
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
        (["promote", "run_consumer_001"], "promote", None),
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


def test_project_installs_the_graphene_console_entry_point():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]

    assert project["scripts"] == {"graphene": "graphene.cli.main:main"}


def test_json_watch_is_canonical_event_only_ndjson(tmp_path, monkeypatch, capsys):
    path, events = _database(tmp_path)
    monkeypatch.setenv("GRAPHENE_LINEAGE_DB", str(path))

    assert main(["--json", "watch", RUN_ID]) == 0
    captured = capsys.readouterr()
    lines = captured.out.splitlines()

    assert captured.err == ""
    assert captured.out == "".join(
        canonical_json_bytes(event.model_dump(mode="json")).decode() + "\n"
        for event in events
    )
    assert [json.loads(line)["seq"] for line in lines] == [1, 2, 3]
    assert not captured.out.startswith(("RUN ", "EVENT ", "Graphene"))
    assert "\x1b[" not in captured.out


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
    assert set(tmp_path.iterdir()) == before_paths


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
    assert inspected.out == (
        canonical_json_bytes(events[-1].model_dump(mode="json")).decode() + "\n"
    )

    assert main(["--json", "why", "app/auth/limiter.py", "--run", RUN_ID]) == 0
    explained = capsys.readouterr()
    payload = json.loads(explained.out)
    assert explained.err == ""
    assert payload["path"] == "app/auth/limiter.py"
    assert payload["observations"] == [
        {
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
        "Whole-repository impact is unknown.",
    ]
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


def test_mutating_commands_parse_but_fail_explicitly_unavailable(capsys):
    commands = (
        ["run", "baseline_max_attempts", "--profile", "platform-maintainer@1"],
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
        ["answer", "question_001", "--choice", "rate_limiter_only"],
        ["memory", "approve", "mem_auth_review@1"],
        ["memory", "reject", "mem_auth_review@1"],
        [
            "handoff",
            RUN_ID,
            "--to",
            "billing-observer@1",
            "--task",
            "adapted_window_seconds",
        ],
        ["promote", "run_consumer_001"],
    )

    for argv in commands:
        assert main(argv) == EXIT_UNAVAILABLE
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith("UNAVAILABLE:")
