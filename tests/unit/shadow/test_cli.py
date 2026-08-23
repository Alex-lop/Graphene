"""The ``graphene shadow`` command surface against the synthetic ndjson fixture.

Every command runs through ``graphene.cli.main.main`` with a private
``GRAPHENE_STATE_DIR``. Stdout is the contract, a failure is exactly one
``SHADOW_ERROR:`` line on stderr with exit status 1, and the mission store is
never created by any shadow command.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import stat
import subprocess
import sys
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest

from graphene.cli import shadow as shadow_cli
from graphene.cli.main import build_parser, main
from graphene.shadow.export import CAPSULE_FILES, EVENTS_NAME, MANIFEST_NAME
from graphene.shadow.lint import RULES, LintReport
from graphene.shadow.reconstruct import ShadowGraph
from graphene.shadow.report import TAGLINE, render_report
from graphene.shadow.store import SHADOW_DB_FILENAME, SHADOW_SCHEMA_VERSION
from graphene.shadow.verify import CapsuleVerifyError, verify_capsule

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "shadow" / "ndjson" / "session_v1.ndjson"
MISSION_DB_FILENAME = "missions.sqlite3"
RATIO_KEYS = ("covered_files", "backed_claims", "overlap_segments")
FIXTURE_RULES = ("claimed-without-evidence", "edit-without-check", "scope-drift")
_SHADOW_ID = re.compile(r"\bshadow_id=(shadow_[0-9a-f]{32})\b")
_INGEST_LINE = re.compile(
    r"^GRAPHENE shadow_id=shadow_[0-9a-f]{32} created=(True|False) events=\d+ "
    r"observed=\d+ inferred=\d+ claims=\d+ unknown=\d+ elapsed_ms=\d+\n$"
)
_VERIFY_LINE = re.compile(
    r"^GRAPHENE shadow_id=(shadow_[0-9a-f]{32}) event_count=(\d+) "
    r"session_sha256=[0-9a-f]{64} verified=True\n$"
)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(root))
    return root


def _run(
    capsys: pytest.CaptureFixture[str], argv: Sequence[str]
) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _ok(capsys: pytest.CaptureFixture[str], argv: Sequence[str]) -> str:
    code, out, err = _run(capsys, argv)
    assert (code, err) == (0, ""), err
    return out


def _json(capsys: pytest.CaptureFixture[str], argv: Sequence[str]) -> dict[str, object]:
    out = _ok(capsys, argv)
    assert out.count("\n") == 1 and out.endswith("\n")
    value = json.loads(out)
    assert isinstance(value, dict)
    return value


def _fails(
    capsys: pytest.CaptureFixture[str], argv: Sequence[str], message: str
) -> None:
    code, out, err = _run(capsys, argv)
    assert code == 1
    assert out == ""
    assert err.startswith("SHADOW_ERROR: ")
    assert err.count("\n") == 1
    assert message in err, err


@pytest.fixture
def shadow_id(state: Path, capsys: pytest.CaptureFixture[str]) -> str:
    out = _ok(capsys, ["shadow", "ingest", str(FIXTURE), "--format", "ndjson"])
    assert _INGEST_LINE.match(out), out
    assert "created=True" in out
    match = _SHADOW_ID.search(out)
    assert match is not None
    return match.group(1)


# -- ingest -------------------------------------------------------------------


def test_ingest_is_idempotent_and_json_capable(
    shadow_id: str, capsys: pytest.CaptureFixture[str]
) -> None:
    again = _ok(capsys, ["shadow", "ingest", str(FIXTURE), "--format", "ndjson"])
    assert _INGEST_LINE.match(again)
    assert f"shadow_id={shadow_id} created=False" in again

    value = _json(
        capsys, ["--json", "shadow", "ingest", str(FIXTURE), "--format", "ndjson"]
    )
    assert value["shadow_id"] == shadow_id
    assert value["created"] is False
    assert value["adapter"] == "ndjson"
    assert value["event_count"] >= 25
    assert value["claim_count"] >= 1
    assert value["unknown_count"] >= 1
    assert value["source_bytes"] == FIXTURE.stat().st_size


def test_unknown_format_fails_closed_with_the_adapter_message(
    state: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # ``--format`` is an argparse choice, so an unregistered name never reaches
    # the adapter registry; the wrong adapter for a file fails closed instead.
    argv = ["shadow", "ingest", str(FIXTURE), "--format", "claude-code"]
    code, out, err = _run(capsys, argv)

    assert (code, out) == (1, "")
    assert err == 'SHADOW_ERROR: line 1: missing field "type"\n'
    with pytest.raises(SystemExit) as raised:
        main(["shadow", "ingest", str(FIXTURE), "--format", "bogus"])
    assert raised.value.code == 2
    assert not (state / MISSION_DB_FILENAME).exists()


def test_adapter_errors_reach_stderr_verbatim(
    state: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = json.loads(FIXTURE.read_text(encoding="utf-8").splitlines()[0])
    first["foo"] = 1
    bad = tmp_path / "bad.ndjson"
    bad.write_text(json.dumps(first) + "\n", encoding="utf-8")

    code, out, err = _run(capsys, ["shadow", "ingest", str(bad), "--format", "ndjson"])

    assert (code, out) == (1, "")
    assert err.startswith("SHADOW_ERROR: line 1")
    assert "foo" in err
    _fails(
        capsys,
        ["shadow", "ingest", str(tmp_path / "absent"), "--format", "ndjson"],
        "absent",
    )
    assert _ok(capsys, ["shadow", "list"]) == ""


# -- report -------------------------------------------------------------------


def test_report_text_carries_tagline_ratios_and_fixture_findings(
    shadow_id: str, capsys: pytest.CaptureFixture[str]
) -> None:
    text = _ok(capsys, ["shadow", "report", shadow_id])
    lines = text.splitlines()

    assert lines[0] == "GRAPHENE SHADOW REPORT"
    assert lines[1] == f'"{TAGLINE}"'
    assert f"shadow_id      {shadow_id}" in lines
    assert "adapter        ndjson 1.0.0" in lines
    assert "RATIOS" in lines and "FINDINGS" in lines and "PROVENANCE" in lines
    for key in RATIO_KEYS:
        assert re.search(rf"^  {key}\s+\d+/\d+  — ", text, re.MULTILINE), key
    for rule in FIXTURE_RULES:
        assert f"[{rule}]" in text, rule
    assert "    governed: Under Graphene's governed mode" in text
    assert "Inference is labeled, never presented as evidence." in text
    assert text.endswith("Graphene did not inspect which tests exercise which file.\n")


def test_report_json_is_the_value_behind_the_text(
    shadow_id: str, capsys: pytest.CaptureFixture[str]
) -> None:
    text = _ok(capsys, ["shadow", "report", shadow_id])
    value = _json(capsys, ["shadow", "report", shadow_id, "--json"])

    assert render_report(value) == text
    assert value["tagline"] == TAGLINE
    assert value["shadow"]["shadow_id"] == shadow_id
    assert [ratio["key"] for ratio in value["ratios"]] == list(RATIO_KEYS)
    assert {finding["rule"] for finding in value["findings"]} >= set(FIXTURE_RULES)
    assert value["rule_counts"]["claimed-without-evidence"] >= 1
    assert _json(capsys, ["--json", "shadow", "report", shadow_id]) == value


# -- lint ---------------------------------------------------------------------


def test_lint_lists_every_rule_and_honours_rule_filters(
    shadow_id: str, capsys: pytest.CaptureFixture[str]
) -> None:
    text = _ok(capsys, ["shadow", "lint", shadow_id])
    lines = text.splitlines()

    assert lines[0] == (
        f"GRAPHENE SHADOW LINT shadow_id={shadow_id} lint=lint.v1 segments=segments.v1"
    )
    assert lines[1] == "rules_applied=" + ",".join(RULES)
    for key in RATIO_KEYS:
        assert any(line.startswith(f"ratio {key}=") for line in lines), key
    assert any(line.startswith("findings=") for line in lines)
    assert any(
        line.startswith("  high [claimed-without-evidence] seq=") for line in lines
    )
    assert any(line.startswith("  warn [edit-without-check] seq=") for line in lines)
    assert any(line.startswith("    governed: ") for line in lines)
    counts = next(line for line in lines if line.startswith("counts "))
    assert all(f"{rule}=" in counts for rule in RULES)
    assert lines[-1].startswith("Coverage is coarse in v0")

    value = _json(
        capsys, ["shadow", "lint", shadow_id, "--rule", "scope-drift", "--json"]
    )
    report = LintReport.model_validate(value)
    assert report.rules_applied == ("scope-drift",)
    assert report.findings and all(f.rule == "scope-drift" for f in report.findings)
    assert report.rule_counts == {"scope-drift": len(report.findings)}
    assert tuple(ratio.key for ratio in report.ratios) == RATIO_KEYS

    two = _json(
        capsys,
        [
            "--json",
            "shadow",
            "lint",
            shadow_id,
            "--rule",
            "scope-drift",
            "--rule",
            "edit-without-check",
        ],
    )
    assert two["rules_applied"] == ["edit-without-check", "scope-drift"]
    with pytest.raises(SystemExit):
        main(["shadow", "lint", shadow_id, "--rule", "bogus"])


# -- graph --------------------------------------------------------------------


def test_graph_emits_dot_or_json(
    shadow_id: str, capsys: pytest.CaptureFixture[str]
) -> None:
    dot = _ok(capsys, ["shadow", "graph", shadow_id, "--dot"])

    assert dot.startswith("digraph shadow {\n")
    assert dot.endswith("}\n")
    assert 'provenance="inferred"' in dot
    assert '"seg_0001"' in dot
    assert "inferred" in dot

    value = _json(capsys, ["shadow", "graph", shadow_id, "--json"])
    graph = ShadowGraph.model_validate(value)
    assert graph.segments_version == "segments.v1"
    assert graph.event_count >= 25
    assert len(graph.segments) >= 2
    assert _json(capsys, ["--json", "shadow", "graph", shadow_id, "--dot"]) == value
    for argv in (
        ["shadow", "graph", shadow_id],
        ["shadow", "graph", shadow_id, "--dot", "--json"],
    ):
        with pytest.raises(SystemExit):
            main(argv)


# -- export, verify, list -----------------------------------------------------


def test_export_writes_a_verifiable_capsule(
    shadow_id: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "out"
    capsule = output / f"{shadow_id}.graphene-shadow"

    out = _ok(capsys, ["shadow", "export", shadow_id, "--output", str(output)])

    assert out == f"GRAPHENE capsule_dir={capsule}\n"
    assert stat.S_IMODE(capsule.stat().st_mode) == 0o700
    assert sorted(entry.name for entry in capsule.iterdir()) == sorted(
        (*CAPSULE_FILES, MANIFEST_NAME)
    )
    assert all(
        stat.S_IMODE((capsule / name).stat().st_mode) == 0o600
        for name in (*CAPSULE_FILES, MANIFEST_NAME)
    )
    manifest = json.loads((capsule / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["shadow_id"] == shadow_id
    assert manifest["adapter"] == "ndjson"
    assert manifest["source_adapter"] != ""
    assert verify_capsule(capsule)["verified"] is True

    _fails(
        capsys,
        ["shadow", "export", shadow_id, "--output", str(output)],
        "capsule directory already exists",
    )
    value = _json(
        capsys,
        ["--json", "shadow", "export", shadow_id, "--output", str(tmp_path / "two")],
    )
    assert value["shadow_id"] == shadow_id
    assert value["capsule_dir"] == str(
        tmp_path / "two" / f"{shadow_id}.graphene-shadow"
    )
    assert value["files"] == sorted((*CAPSULE_FILES, MANIFEST_NAME))

    data = bytearray((capsule / EVENTS_NAME).read_bytes())
    data[20] ^= 0x01
    (capsule / EVENTS_NAME).write_bytes(bytes(data))
    with pytest.raises(CapsuleVerifyError, match=f"{EVENTS_NAME} digest mismatch"):
        verify_capsule(capsule)


def test_capsule_stream_re_ingests_to_the_same_shadow_id(
    shadow_id: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _ok(capsys, ["shadow", "export", shadow_id, "--output", str(tmp_path / "out")])
    capsule = tmp_path / "out" / f"{shadow_id}.graphene-shadow"

    again = _ok(
        capsys, ["shadow", "ingest", str(capsule / EVENTS_NAME), "--format", "ndjson"]
    )
    assert f"shadow_id={shadow_id} created=False" in again

    completed = subprocess.run(
        (sys.executable, "-m", "graphene.shadow.verify", str(capsule)),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "backend")},
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["shadow_id"] == shadow_id


def test_export_relative_output_resolves_against_cwd(
    shadow_id: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    out = _ok(capsys, ["shadow", "export", shadow_id, "--output", "relative-out"])

    capsule = tmp_path / "relative-out" / f"{shadow_id}.graphene-shadow"
    assert out == f"GRAPHENE capsule_dir={capsule}\n"
    assert capsule.is_dir()


def test_verify_and_list_describe_the_stored_session(
    shadow_id: str, capsys: pytest.CaptureFixture[str]
) -> None:
    verified = _ok(capsys, ["shadow", "verify", shadow_id])
    match = _VERIFY_LINE.match(verified)
    assert match is not None and match.group(1) == shadow_id
    assert int(match.group(2)) >= 25
    value = _json(capsys, ["--json", "shadow", "verify", shadow_id])
    assert value["verified"] is True and value["shadow_id"] == shadow_id

    listing = _ok(capsys, ["shadow", "list"])
    lines = listing.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith(f"{shadow_id} adapter=ndjson 1.0.0 session_id=")
    assert re.search(r" events=\d+ ingested_at=\d{4}-\d{2}-\d{2}T", lines[0])
    sessions = _json(capsys, ["--json", "shadow", "list"])["sessions"]
    assert [session["shadow_id"] for session in sessions] == [shadow_id]


def test_list_is_empty_before_any_ingest(
    state: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _ok(capsys, ["shadow", "list"]) == ""
    assert _json(capsys, ["--json", "shadow", "list"]) == {"sessions": []}
    assert shadow_cli.main(["shadow", "list"]) == 0
    assert capsys.readouterr() == ("", "")


# -- failure contract and isolation ------------------------------------------


def test_unknown_session_and_malformed_ids_fail_closed(
    state: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    unknown = "shadow_" + "0" * 32
    commands = (
        ["shadow", "report", "{}"],
        ["shadow", "lint", "{}"],
        ["shadow", "graph", "{}", "--dot"],
        ["shadow", "export", "{}", "--output", str(tmp_path / "out")],
        ["shadow", "verify", "{}"],
    )
    for template in commands:
        argv = [part.format(unknown) for part in template]
        code, out, err = _run(capsys, argv)
        assert (code, out) == (1, ""), argv
        assert err == f"SHADOW_ERROR: unknown shadow session {unknown}\n", argv
        argv = [part.format("not-an-id") for part in template]
        code, out, err = _run(capsys, argv)
        assert (code, out) == (1, ""), argv
        assert err == (
            "SHADOW_ERROR: shadow_id must look like shadow_<32 hex characters>, "
            "got 'not-an-id'\n"
        ), argv
    assert not (tmp_path / "out").exists()


def test_shadow_commands_never_touch_the_mission_store(
    shadow_id: str, state: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for argv in (
        ["shadow", "report", shadow_id],
        ["shadow", "lint", shadow_id],
        ["shadow", "graph", shadow_id, "--dot"],
        ["shadow", "export", shadow_id, "--output", str(tmp_path / "out")],
        ["shadow", "verify", shadow_id],
        ["shadow", "list"],
    ):
        _ok(capsys, argv)

    names = {entry.name for entry in state.iterdir()}
    assert MISSION_DB_FILENAME not in names
    assert names <= {
        SHADOW_DB_FILENAME,
        f"{SHADOW_DB_FILENAME}-wal",
        f"{SHADOW_DB_FILENAME}-shm",
    }
    database = state / SHADOW_DB_FILENAME
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == (
            SHADOW_SCHEMA_VERSION
        )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert tables == {"shadow_schema_migrations", "shadow_sessions", "shadow_events"}


def test_state_directory_errors_are_shadow_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GRAPHENE_STATE_DIR", "relative/state")

    code, out, err = _run(capsys, ["shadow", "list"])

    assert (code, out) == (1, "")
    assert err == "SHADOW_ERROR: GRAPHENE_STATE_DIR must be absolute\n"


def test_handle_rejects_an_unknown_action(capsys: pytest.CaptureFixture[str]) -> None:
    args = SimpleNamespace(command="shadow", shadow_action="bogus", json_mode=False)

    assert shadow_cli.handle(args) == 1
    assert capsys.readouterr() == ("", "SHADOW_ERROR: unknown shadow action 'bogus'\n")


def test_json_flags_are_parsed_without_clobbering_each_other() -> None:
    parser = build_parser()

    sub = parser.parse_args(["shadow", "lint", "x", "--json"])
    assert (sub.json_mode, sub.shadow_json) == (False, True)
    top = parser.parse_args(["--json", "shadow", "lint", "x"])
    assert (top.json_mode, top.shadow_json) == (True, False)
    graph = parser.parse_args(["shadow", "graph", "x", "--json"])
    assert graph.graph_format == "json" and graph.json_mode is False
    standalone = shadow_cli.build_parser().parse_args(["shadow", "graph", "x", "--dot"])
    assert standalone.graph_format == "dot"
    ingest = parser.parse_args(["shadow", "ingest", "x.ndjson", "--format", "ndjson"])
    assert ingest.format == "ndjson" and ingest.repo is None
    assert ingest.path == Path("x.ndjson")
