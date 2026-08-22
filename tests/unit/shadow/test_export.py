"""Capsule export and bytes-only verification.

The store is populated directly with ``ShadowEvent.create`` streams, so every
assertion here is independent of the ndjson adapter. Tampering is applied to
the files on disk and must fail closed with a message that names the file or
the line; the manifest is re-pinned where the test wants to reach a deeper
check than the file digest.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from graphene.hashing import canonical_json_bytes, sha256_hex
from graphene.shadow import verify as verify_module
from graphene.shadow.events import ShadowEvent, session_sha256
from graphene.shadow.export import (
    CAPSULE_FILES,
    CAPSULE_SCHEMA,
    EVENTS_NAME,
    GRAPH_NAME,
    LINT_NAME,
    MANIFEST_NAME,
    REDACTION_NOTE,
    REPORT_NAME,
    VERIFY_NAME,
    ShadowExportError,
    capsule_name,
    export_capsule,
)
from graphene.shadow.lint import LINT_VERSION, lint
from graphene.shadow.reconstruct import SEGMENTS_VERSION, reconstruct
from graphene.shadow.report import TAGLINE, render_report, report_value
from graphene.shadow.store import (
    SHADOW_DB_FILENAME,
    ShadowStore,
    ShadowStoreError,
    shadow_id_for,
)
from graphene.shadow.verify import (
    CHECKS,
    MANIFEST_KEYS,
    CapsuleVerifyError,
    verify_capsule,
)

ROOT = Path(__file__).resolve().parents[3]
ADAPTER = "ndjson"
VERSION = "1.0.0"
SOURCE_SHA256 = "b" * 64
NOW = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
_ACTORS = {"message": "user", "check_result": "tool"}
_CLAIM = {"matcher": "claims.v1", "category": "checks_pass", "pattern_id": "tests-pass"}
EXPECTED_FILES = sorted((*CAPSULE_FILES, MANIFEST_NAME))


def _event(seq: int, kind: str, **over: object) -> ShadowEvent:
    fields: dict[str, object] = {
        "session_id": "sess-1",
        "seq": seq,
        "actor": _ACTORS.get(kind, "agent"),
        "kind": kind,
        "provenance": "observed",
        "source": {
            "adapter": ADAPTER,
            "adapter_version": VERSION,
            "record_ref": f"line:{seq}",
            "raw_type": "test",
        },
    }
    fields.update(over)
    return ShadowEvent.create(**fields)


def _stream() -> tuple[ShadowEvent, ...]:
    message = _event(7, "message", actor="agent", excerpt="All tests pass.")
    return (
        _event(1, "message", excerpt="Make the greeting configurable."),
        _event(2, "file_edit", paths=("app/greet.py",)),
        _event(3, "check_run", check_family="pytest", argv_excerpt="pytest -q"),
        _event(4, "check_result", check_family="pytest", exit_code=0),
        _event(5, "install_op", argv_excerpt="uv sync"),
        _event(6, "file_edit", paths=("app/config.py",)),
        message,
        _event(
            8,
            "claim",
            provenance="inferred",
            derived_from=(message.event_id,),
            claim=_CLAIM,
            excerpt=message.excerpt,
        ),
        _event(9, "file_create", paths=(".env",)),
    )


@pytest.fixture
def store(tmp_path: Path) -> ShadowStore:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    return ShadowStore(state / SHADOW_DB_FILENAME)


def _ingest(store: ShadowStore, events: tuple[ShadowEvent, ...]) -> str:
    shadow_id, created = store.ingest(
        events,
        adapter=ADAPTER,
        adapter_version=VERSION,
        source_sha256=SOURCE_SHA256,
        source_bytes=1234,
        repo_label="graphene",
        summary={"event_count": len(events), "heuristics": {"claims": "claims.v1"}},
        now=NOW,
    )
    assert created
    return shadow_id


@pytest.fixture
def exported(store: ShadowStore, tmp_path: Path) -> tuple[Path, str, dict[str, object]]:
    shadow_id = _ingest(store, _stream())
    result = export_capsule(store, shadow_id, tmp_path / "out")
    return Path(str(result["capsule_dir"])), shadow_id, result


def _manifest(capsule: Path) -> dict[str, object]:
    return json.loads((capsule / MANIFEST_NAME).read_text(encoding="utf-8"))


def _write_manifest(capsule: Path, manifest: dict[str, object]) -> None:
    (capsule / MANIFEST_NAME).write_bytes(canonical_json_bytes(manifest) + b"\n")


def _repin(capsule: Path) -> None:
    """Recompute the manifest's file digests after a deliberate edit."""

    manifest = _manifest(capsule)
    files = manifest["files"]
    assert isinstance(files, dict)
    for name in files:
        data = (capsule / name).read_bytes()
        files[name] = {"sha256": sha256_hex(data), "bytes": len(data)}
    _write_manifest(capsule, manifest)


def _rewrite_json(capsule: Path, name: str, mutate: Callable[[dict], None]) -> None:
    value = json.loads((capsule / name).read_text(encoding="utf-8"))
    mutate(value)
    (capsule / name).write_bytes(canonical_json_bytes(value) + b"\n")
    _repin(capsule)


def _rewrite_lines(capsule: Path, mutate: Callable[[list[bytes]], list[bytes]]) -> None:
    lines = (capsule / EVENTS_NAME).read_bytes().split(b"\n")[:-1]
    (capsule / EVENTS_NAME).write_bytes(
        b"".join(line + b"\n" for line in mutate(lines))
    )
    _repin(capsule)


def _edit_line(lines: list[bytes], index: int, key: str, value: object) -> list[bytes]:
    record = json.loads(lines[index])
    record[key] = value
    lines[index] = canonical_json_bytes(record)
    return lines


# -- export -------------------------------------------------------------------


def test_export_writes_a_private_capsule_with_every_file(
    exported: tuple[Path, str, dict[str, object]], tmp_path: Path
) -> None:
    capsule, shadow_id, result = exported

    assert capsule == tmp_path / "out" / capsule_name(shadow_id)
    assert capsule.name == f"{shadow_id}.graphene-shadow"
    assert stat.S_IMODE(capsule.stat().st_mode) == 0o700
    assert sorted(entry.name for entry in capsule.iterdir()) == EXPECTED_FILES
    for name in EXPECTED_FILES:
        metadata = (capsule / name).lstat()
        assert stat.S_ISREG(metadata.st_mode)
        assert stat.S_IMODE(metadata.st_mode) == 0o600
    assert set(result) == {"shadow_id", "capsule_dir", "manifest_sha256", "files"}
    assert result["shadow_id"] == shadow_id
    assert result["files"] == EXPECTED_FILES
    assert result["manifest_sha256"] == sha256_hex(
        (capsule / MANIFEST_NAME).read_bytes()
    )


def test_manifest_pins_every_other_file_by_digest_and_size(
    exported: tuple[Path, str, dict[str, object]], store: ShadowStore
) -> None:
    capsule, shadow_id, _ = exported
    manifest = _manifest(capsule)
    events = store.events(shadow_id)

    assert set(MANIFEST_KEYS) <= set(manifest)
    assert manifest["schema"] == CAPSULE_SCHEMA
    assert manifest["shadow_id"] == shadow_id
    assert manifest["session_id"] == "sess-1"
    assert manifest["adapter"] == ADAPTER
    assert manifest["adapter_version"] == VERSION
    assert manifest["source_adapter"] == ADAPTER
    assert manifest["source_adapter_version"] == VERSION
    assert manifest["source_sha256"] == SOURCE_SHA256
    assert manifest["source_bytes"] == 1234
    assert manifest["event_count"] == len(events) == 9
    digest = session_sha256(event.event_id for event in events)
    assert manifest["session_sha256"] == digest
    assert shadow_id_for(ADAPTER, VERSION, digest) == shadow_id
    assert manifest["heuristics"] == {
        "segments": SEGMENTS_VERSION,
        "claims": "claims.v1",
        "lint": LINT_VERSION,
    }
    assert manifest["redaction"] == REDACTION_NOTE
    assert set(manifest["files"]) == set(CAPSULE_FILES)
    for name, entry in manifest["files"].items():
        data = (capsule / name).read_bytes()
        assert entry == {"sha256": sha256_hex(data), "bytes": len(data)}


def test_events_ndjson_is_canonical_and_round_trips_to_the_same_id(
    exported: tuple[Path, str, dict[str, object]], store: ShadowStore
) -> None:
    capsule, shadow_id, _ = exported
    events = store.events(shadow_id)
    data = (capsule / EVENTS_NAME).read_bytes()

    assert data == b"".join(
        canonical_json_bytes(event.to_record()) + b"\n" for event in events
    )
    lines = data.split(b"\n")[:-1]
    parsed = tuple(ShadowEvent.from_record(json.loads(line)) for line in lines)
    assert parsed == events
    assert all("event_id" in json.loads(line) for line in lines)

    again = store.ingest(
        parsed,
        adapter=ADAPTER,
        adapter_version=VERSION,
        source_sha256=sha256_hex(data),
        source_bytes=len(data),
        repo_label=None,
        summary={"re-ingest": True},
        now=NOW,
    )
    assert again == (shadow_id, False)


def test_graph_lint_and_report_match_fresh_runs(
    exported: tuple[Path, str, dict[str, object]], store: ShadowStore
) -> None:
    capsule, shadow_id, _ = exported
    events = store.events(shadow_id)
    graph = reconstruct(events)
    lint_report = lint(events, graph)
    expected = render_report(
        report_value(store.session(shadow_id).to_dict(), graph, lint_report)
    )

    assert json.loads((capsule / GRAPH_NAME).read_bytes()) == graph.model_dump(
        mode="json"
    )
    assert json.loads((capsule / LINT_NAME).read_bytes()) == lint_report.model_dump(
        mode="json"
    )
    report = (capsule / REPORT_NAME).read_text(encoding="utf-8")
    assert report == expected
    assert report.startswith("GRAPHENE SHADOW REPORT\n")
    assert TAGLINE in report
    assert shadow_id in report
    assert "[claimed-without-evidence]" in report
    assert "[scope-drift]" in report


def test_verify_markdown_names_the_exact_commands(
    exported: tuple[Path, str, dict[str, object]],
) -> None:
    capsule, shadow_id, _ = exported
    text = (capsule / VERIFY_NAME).read_text(encoding="utf-8")
    manifest = _manifest(capsule)
    name = capsule_name(shadow_id)

    assert f"uv run --frozen python -m graphene.shadow.verify {name}" in text
    assert (
        f"uv run --frozen graphene shadow ingest {name}/{EVENTS_NAME} --format ndjson"
        in text
    )
    assert "shadow.event.v1" in text and "shadow.session.v1" in text
    assert f'"shadow_id":"{shadow_id}"' in text
    assert str(manifest["session_sha256"]) in text
    assert str(manifest["source_sha256"]) in text
    assert SEGMENTS_VERSION in text and LINT_VERSION in text
    assert REDACTION_NOTE in text


def test_export_creates_a_missing_output_directory(
    store: ShadowStore, tmp_path: Path
) -> None:
    shadow_id = _ingest(store, _stream())
    nested = tmp_path / "deep" / "er" / "out"

    result = export_capsule(store, shadow_id, nested)

    assert Path(str(result["capsule_dir"])).parent == nested
    assert stat.S_IMODE(nested.stat().st_mode) == 0o700


def test_export_refuses_an_existing_capsule(
    exported: tuple[Path, str, dict[str, object]], store: ShadowStore, tmp_path: Path
) -> None:
    capsule, shadow_id, _ = exported
    before = {name: (capsule / name).read_bytes() for name in EXPECTED_FILES}

    with pytest.raises(ShadowExportError, match="capsule directory already exists"):
        export_capsule(store, shadow_id, tmp_path / "out")
    assert {name: (capsule / name).read_bytes() for name in EXPECTED_FILES} == before


def test_export_refuses_a_symlinked_or_non_directory_output(
    store: ShadowStore, tmp_path: Path
) -> None:
    shadow_id = _ingest(store, _stream())
    (tmp_path / "real").mkdir()
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "real")
    regular = tmp_path / "file"
    regular.write_text("not a directory\n")

    with pytest.raises(ShadowExportError, match="cannot be a symlink"):
        export_capsule(store, shadow_id, link)
    with pytest.raises(ShadowExportError, match="not a directory"):
        export_capsule(store, shadow_id, regular)
    assert not any((tmp_path / "real").iterdir())


def test_export_unknown_session_fails_closed(
    store: ShadowStore, tmp_path: Path
) -> None:
    with pytest.raises(ShadowStoreError, match="unknown shadow session"):
        export_capsule(store, "shadow_" + "0" * 32, tmp_path / "out")
    assert not (tmp_path / "out").exists()


# -- verify -------------------------------------------------------------------


def test_verify_capsule_recomputes_everything_and_reports_checks(
    exported: tuple[Path, str, dict[str, object]],
) -> None:
    capsule, shadow_id, result = exported

    verified = verify_capsule(capsule)

    assert verified["verified"] is True
    assert verified["shadow_id"] == shadow_id
    assert verified["capsule_dir"] == str(capsule)
    assert verified["session_id"] == "sess-1"
    assert verified["event_count"] == 9
    assert verified["session_sha256"] == _manifest(capsule)["session_sha256"]
    assert verified["manifest_sha256"] == result["manifest_sha256"]
    assert verified["checks"] == list(CHECKS)
    assert set(verified["files"]) == set(CAPSULE_FILES)
    assert json.loads(canonical_json_bytes(verified)) == verified


def test_verify_accepts_a_relative_path_from_cwd(
    exported: tuple[Path, str, dict[str, object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    capsule, shadow_id, _ = exported
    monkeypatch.chdir(capsule.parent)

    assert verify_capsule(Path(capsule.name))["shadow_id"] == shadow_id


def test_verify_main_prints_json_and_fails_closed(
    exported: tuple[Path, str, dict[str, object]], capsys: pytest.CaptureFixture[str]
) -> None:
    capsule, shadow_id, _ = exported

    assert verify_module.main([str(capsule)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["shadow_id"] == shadow_id
    assert captured.out.count("\n") == 1

    pinned = _manifest(capsule)["files"][EVENTS_NAME]["bytes"]
    (capsule / EVENTS_NAME).write_bytes(b"{}\n")
    assert verify_module.main([str(capsule)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        f"SHADOW_ERROR: {EVENTS_NAME} size mismatch: {MANIFEST_NAME} says {pinned} "
        "bytes, found 3\n"
    )


def test_verify_module_runs_as_a_python_module(
    exported: tuple[Path, str, dict[str, object]],
) -> None:
    capsule, shadow_id, _ = exported
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "backend")}

    completed = subprocess.run(
        (sys.executable, "-m", "graphene.shadow.verify", str(capsule)),
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["shadow_id"] == shadow_id


def _tamper_byte(capsule: Path) -> None:
    data = bytearray((capsule / EVENTS_NAME).read_bytes())
    data[10] ^= 0x01
    (capsule / EVENTS_NAME).write_bytes(bytes(data))


def _tamper_excerpt(capsule: Path) -> None:
    _rewrite_lines(capsule, lambda lines: _edit_line(lines, 6, "excerpt", "edited"))


def _swap_lines(capsule: Path) -> None:
    def swap(lines: list[bytes]) -> list[bytes]:
        lines[0], lines[1] = lines[1], lines[0]
        return lines

    _rewrite_lines(capsule, swap)


def _drop_last_line(capsule: Path) -> None:
    _rewrite_lines(capsule, lambda lines: lines[:-1])


def _strip_newline(capsule: Path) -> None:
    data = (capsule / EVENTS_NAME).read_bytes()
    (capsule / EVENTS_NAME).write_bytes(data[:-1])
    _repin(capsule)


def _blank_line(capsule: Path) -> None:
    _rewrite_lines(capsule, lambda lines: [*lines, b""])


def _non_canonical_line(capsule: Path) -> None:
    def pad(lines: list[bytes]) -> list[bytes]:
        lines[0] = json.dumps(json.loads(lines[0]), sort_keys=True).encode()
        return lines

    _rewrite_lines(capsule, pad)


def _drop_event_id(capsule: Path) -> None:
    def drop(lines: list[bytes]) -> list[bytes]:
        record = json.loads(lines[2])
        del record["event_id"]
        lines[2] = canonical_json_bytes(record)
        return lines

    _rewrite_lines(capsule, drop)


def _extra_file(capsule: Path) -> None:
    (capsule / "extra.txt").write_text("surprise\n")


def _missing_file(capsule: Path) -> None:
    (capsule / LINT_NAME).unlink()


def _symlinked_file(capsule: Path) -> None:
    target = capsule / LINT_NAME
    moved = capsule.parent / "lint-elsewhere.json"
    target.rename(moved)
    target.symlink_to(moved)


def _manifest_edit(key: str, value: object) -> Callable[[Path], None]:
    def mutate(capsule: Path) -> None:
        manifest = _manifest(capsule)
        manifest[key] = value
        _write_manifest(capsule, manifest)

    return mutate


def _manifest_drop(key: str) -> Callable[[Path], None]:
    def mutate(capsule: Path) -> None:
        manifest = _manifest(capsule)
        del manifest[key]
        _write_manifest(capsule, manifest)

    return mutate


def _manifest_heuristic(key: str, value: str) -> Callable[[Path], None]:
    def mutate(capsule: Path) -> None:
        manifest = _manifest(capsule)
        manifest["heuristics"][key] = value
        _write_manifest(capsule, manifest)

    return mutate


def _manifest_size(capsule: Path) -> None:
    manifest = _manifest(capsule)
    manifest["files"][GRAPH_NAME]["bytes"] += 1
    _write_manifest(capsule, manifest)


def _manifest_unlist(capsule: Path) -> None:
    manifest = _manifest(capsule)
    del manifest["files"][REPORT_NAME]
    _write_manifest(capsule, manifest)


def _manifest_array(capsule: Path) -> None:
    (capsule / MANIFEST_NAME).write_bytes(b"[]\n")


def _manifest_garbage(capsule: Path) -> None:
    (capsule / MANIFEST_NAME).write_bytes(b"{not json\n")


def _graph_label(capsule: Path) -> None:
    def mutate(value: dict) -> None:
        value["segments"][0]["label"] = "tampered label"

    _rewrite_json(capsule, GRAPH_NAME, mutate)


def _graph_invalid(capsule: Path) -> None:
    def mutate(value: dict) -> None:
        value["event_count"] = 1

    _rewrite_json(capsule, GRAPH_NAME, mutate)


def _lint_message(capsule: Path) -> None:
    def mutate(value: dict) -> None:
        value["findings"][0]["message"] = "tampered"

    _rewrite_json(capsule, LINT_NAME, mutate)


def _report_replaced(capsule: Path) -> None:
    (capsule / REPORT_NAME).write_text("not a report\n")
    _repin(capsule)


def _report_other_id(capsule: Path) -> None:
    path = capsule / REPORT_NAME
    text = path.read_text(encoding="utf-8")
    shadow_id = str(_manifest(capsule)["shadow_id"])
    path.write_text(text.replace(shadow_id, "shadow_" + "f" * 32))
    _repin(capsule)


TAMPERS: tuple[tuple[str, Callable[[Path], None], str], ...] = (
    ("flipped byte", _tamper_byte, f"{EVENTS_NAME} digest mismatch"),
    (
        "edited excerpt, manifest re-pinned",
        _tamper_excerpt,
        f"{EVENTS_NAME} line 7: event_id does not match the canonical encoding",
    ),
    (
        "swapped lines",
        _swap_lines,
        f"{EVENTS_NAME} line 1: seq 2 is not contiguous (expected 1)",
    ),
    (
        "dropped last line",
        _drop_last_line,
        f"event count mismatch: {MANIFEST_NAME} says 9, {EVENTS_NAME} has 8",
    ),
    (
        "missing trailing newline",
        _strip_newline,
        f"{EVENTS_NAME} must end with a newline",
    ),
    ("blank line", _blank_line, f"{EVENTS_NAME} line 10 is blank"),
    (
        "non-canonical line",
        _non_canonical_line,
        f"{EVENTS_NAME} line 1 is not canonical",
    ),
    ("event_id removed", _drop_event_id, f"{EVENTS_NAME} line 3 has no event_id"),
    ("extra file", _extra_file, "unlisted file in capsule: extra.txt"),
    ("missing file", _missing_file, f"{LINT_NAME} is missing"),
    ("symlinked file", _symlinked_file, f"{LINT_NAME} cannot be a symlink"),
    (
        "shadow_id changed",
        _manifest_edit("shadow_id", "shadow_" + "0" * 32),
        "does not match the adapter and session digest",
    ),
    (
        "adapter_version changed",
        _manifest_edit("adapter_version", "9.9.9"),
        "does not match the adapter and session digest",
    ),
    (
        "session_sha256 changed",
        _manifest_edit("session_sha256", "c" * 64),
        "session digest mismatch",
    ),
    (
        "session_id changed",
        _manifest_edit("session_id", "other"),
        f"session_id mismatch: {MANIFEST_NAME} says other",
    ),
    (
        "event_count changed",
        _manifest_edit("event_count", 3),
        f"event count mismatch: {MANIFEST_NAME} says 3, {EVENTS_NAME} has 9",
    ),
    (
        "schema changed",
        _manifest_edit("schema", "graphene.shadow.capsule.v2"),
        f"is not {CAPSULE_SCHEMA}",
    ),
    (
        "redaction dropped",
        _manifest_drop("redaction"),
        f"{MANIFEST_NAME} is missing redaction",
    ),
    ("files dropped", _manifest_drop("files"), f"{MANIFEST_NAME} is missing files"),
    (
        "source_bytes negative",
        _manifest_edit("source_bytes", -1),
        "source_bytes must be a non-negative integer",
    ),
    (
        "heuristics lint.v2",
        _manifest_heuristic("lint", "lint.v2"),
        "are not the ones this Graphene implements",
    ),
    (
        "heuristics segments.v0",
        _manifest_heuristic("segments", "segments.v0"),
        "are not the ones this Graphene implements",
    ),
    ("size edited", _manifest_size, f"{GRAPH_NAME} size mismatch"),
    ("file unlisted", _manifest_unlist, f"{MANIFEST_NAME} does not list {REPORT_NAME}"),
    ("manifest array", _manifest_array, f"{MANIFEST_NAME} must be a JSON object"),
    ("manifest garbage", _manifest_garbage, f"{MANIFEST_NAME} is not valid JSON"),
    (
        "graph label",
        _graph_label,
        f"{GRAPH_NAME} does not match {SEGMENTS_VERSION} over {EVENTS_NAME}",
    ),
    ("graph invalid", _graph_invalid, f"{GRAPH_NAME} is not a valid ShadowGraph"),
    (
        "lint message",
        _lint_message,
        f"{LINT_NAME} does not match {LINT_VERSION} over {EVENTS_NAME}",
    ),
    (
        "report replaced",
        _report_replaced,
        f"{REPORT_NAME} is not the shadow report for",
    ),
    (
        "report for another id",
        _report_other_id,
        f"{REPORT_NAME} is not the shadow report for",
    ),
)


@pytest.mark.parametrize(
    ("label", "tamper", "message"), TAMPERS, ids=[t[0] for t in TAMPERS]
)
def test_tampered_capsules_fail_closed(
    exported: tuple[Path, str, dict[str, object]],
    label: str,
    tamper: Callable[[Path], None],
    message: str,
) -> None:
    capsule, _, _ = exported
    assert verify_capsule(capsule)["verified"] is True

    tamper(capsule)

    with pytest.raises(CapsuleVerifyError) as raised:
        verify_capsule(capsule)
    assert message in str(raised.value), label


def test_verify_rejects_missing_symlinked_or_manifestless_directories(
    exported: tuple[Path, str, dict[str, object]], tmp_path: Path
) -> None:
    capsule, _, _ = exported
    link = tmp_path / "link.graphene-shadow"
    link.symlink_to(capsule)
    empty = tmp_path / "empty.graphene-shadow"
    empty.mkdir()

    with pytest.raises(CapsuleVerifyError, match="capsule directory not found"):
        verify_capsule(tmp_path / "absent")
    with pytest.raises(CapsuleVerifyError, match="cannot be a symlink"):
        verify_capsule(link)
    with pytest.raises(CapsuleVerifyError, match=f"{MANIFEST_NAME} is missing"):
        verify_capsule(empty)
    with pytest.raises(CapsuleVerifyError, match="capsule directory not found"):
        verify_capsule(capsule / MANIFEST_NAME)
