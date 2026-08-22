from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from graphene.hashing import canonical_json_bytes, sha256_hex
from graphene.orchestration import capsule
from graphene.orchestration.capsule import (
    AUTHORITY_NOTE,
    CAPSULE_SCHEMA,
    CAPSULE_SUFFIX,
    NOT_VERIFIABLE_OFFLINE,
    RECEIPT_KINDS,
    REDACTION_NOTE,
    CapsuleError,
    export_mission_capsule,
    rewind_plan,
    verify_mission_capsule,
)
from graphene.orchestration.evidence import SQLiteAttemptEvidenceStore
from graphene.orchestration.models import MissionStatus, Plan
from graphene.orchestration.scripted import (
    load_scenario,
    propose_scripted_mission,
    run_scripted_mission,
    scripted_supported,
)
from graphene.orchestration.store import SQLiteMissionStore
from tests.unit.orchestration.test_store import _plan, _task

SENTINEL = b"operator guidance: rotate the deploy key before Friday"
NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
EXPECTED_CHECKS = [
    "manifest_file_digests",
    "mission_event_chain",
    "attempt_evidence_chains",
    "receipt_references",
    "receipt_contents",
    "final_bundle",
    "tree_manifest",
    "publication_envelopes",
    "plan_revisions",
]

requires_scripted = pytest.mark.skipif(
    not scripted_supported(),
    reason="capsule export from a scripted-local mission needs the macOS sandbox",
)


@pytest.fixture(scope="module")
def completed(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    if not scripted_supported():
        pytest.skip("scripted-local mission requires the macOS fixture sandbox")
    root = tmp_path_factory.mktemp("capsule")
    runtime = root / "runtime"
    store = SQLiteMissionStore(root / "missions.sqlite")
    mission_id = "mission-capsule-001"
    run_scripted_mission(
        scenario=load_scenario(),
        store=store,
        runtime=runtime,
        mission_id=mission_id,
    )
    evidence = store.artifact_resolver
    assert isinstance(evidence, SQLiteAttemptEvidenceStore)
    # A private operator input that is never referenced by any event: it must
    # never leave the evidence spool.
    evidence.put_artifact("operator-input", SENTINEL)
    output = root / "out"
    output.mkdir(mode=0o700)
    exported = export_mission_capsule(
        store=store,
        evidence=evidence,
        mission_id=mission_id,
        output_dir=output,
        now=NOW,
    )
    return SimpleNamespace(
        store=store,
        evidence=evidence,
        mission_id=mission_id,
        runtime=runtime,
        output=output,
        capsule_dir=Path(exported["capsule_dir"]),
        exported=exported,
    )


def _copy(capsule_dir: Path, destination: Path) -> Path:
    target = destination / capsule_dir.name
    shutil.copytree(capsule_dir, target)
    return target


def _files(capsule_dir: Path) -> dict[str, bytes]:
    return {
        path.relative_to(capsule_dir).as_posix(): path.read_bytes()
        for path in sorted(capsule_dir.rglob("*"))
        if path.is_file()
    }


def _manifest(capsule_dir: Path) -> dict:
    return json.loads((capsule_dir / "manifest.json").read_bytes())


def _write_manifest(capsule_dir: Path, manifest: dict) -> None:
    (capsule_dir / "manifest.json").write_bytes(
        json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
    )


def _resign_manifest(capsule_dir: Path, manifest: dict | None = None) -> None:
    """Simulate an attacker who updates the manifest digests after tampering."""

    manifest = _manifest(capsule_dir) if manifest is None else manifest
    manifest["files"] = {
        name: {"sha256": sha256_hex(content), "bytes": len(content)}
        for name, content in _files(capsule_dir).items()
        if name != "manifest.json"
    }
    _write_manifest(capsule_dir, manifest)


def _rewrite_line(path: Path, seq: int, mutate) -> None:
    lines = path.read_bytes().split(b"\n")
    value = json.loads(lines[seq - 1])
    mutate(value)
    lines[seq - 1] = canonical_json_bytes(value)
    path.write_bytes(b"\n".join(lines))


def _failure(result: dict) -> dict:
    assert result["verified"] is False
    failed = [item for item in result["checks"] if not item["ok"]]
    assert len(failed) == 1 and failed[0] is result["checks"][-1]
    return failed[0]


@requires_scripted
def test_export_verifies_cold_and_lists_every_check(completed: SimpleNamespace):
    snapshot = completed.store.snapshot(completed.mission_id)
    assert snapshot.mission.status == MissionStatus.AWAITING_RESULT
    capsule_dir = completed.capsule_dir
    assert capsule_dir.name == f"{completed.mission_id}{CAPSULE_SUFFIX}"

    result = verify_mission_capsule(capsule_dir)

    assert result["verified"] is True
    assert [item["name"] for item in result["checks"]] == EXPECTED_CHECKS
    assert all(item["ok"] for item in result["checks"])
    for phrase in NOT_VERIFIABLE_OFFLINE:
        assert any(phrase in item for item in result["not_checked"])

    manifest = _manifest(capsule_dir)
    assert manifest["schema"] == CAPSULE_SCHEMA
    assert manifest["mission_id"] == completed.mission_id
    assert manifest["exported_at"] == NOW.isoformat()
    assert manifest["mission_status"] == "awaiting_result"
    assert manifest["head"] == {
        "seq": snapshot.head.seq,
        "event_count": snapshot.head.event_count,
        "event_sha256": snapshot.head.event_sha256,
    }
    assert manifest["snapshot_sha256"] == snapshot.snapshot_sha256
    assert manifest["policy"]["policy_sha256"] == snapshot.policy.policy_sha256
    assert manifest["redaction"] == REDACTION_NOTE
    assert manifest["not_verifiable_offline"] == list(NOT_VERIFIABLE_OFFLINE)
    assert manifest["authority_note"] == AUTHORITY_NOTE
    assert manifest["final_bundle"]["present"] is True
    assert manifest["final_bundle"]["decision"]["state"] == "pending"
    assert manifest["counts"]["attempts"] == len(snapshot.attempts) == 7
    assert manifest["counts"]["attempt_evidence_chains"] == 7
    assert manifest["counts"]["publications"] == len(snapshot.publications) == 6
    assert manifest["counts"]["receipts"] == len(manifest["receipts"]) == 7
    assert {item["kind"] for item in manifest["receipts"]} == {"test-receipt"}
    assert manifest["plan_revisions"] == [
        {
            "revision": 1,
            "plan_sha256": sha256_hex(
                canonical_json_bytes(snapshot.plan.model_dump(mode="json"))
            ),
            "file": "plan/revision-1.json",
        }
    ]

    files = _files(capsule_dir)
    assert set(manifest["files"]) == set(files) - {"manifest.json"}
    assert files["events.ndjson"].count(b"\n") == snapshot.head.seq
    assert len([name for name in files if name.startswith("attempts/")]) == 7
    assert len([name for name in files if name.startswith("receipts/")]) == 7
    assert "plan/revision-1.json" in files
    assert "uv run --frozen python -m graphene.orchestration.capsule verify" in (
        files["VERIFY.md"].decode()
    )
    reference = manifest["final_bundle"]["reference"]
    assert files["final-bundle.json"] == completed.evidence.resolve(
        reference["kind"], reference["id"]
    )
    tree = json.loads(files["tree-manifest.json"])
    bundle = json.loads(files["final-bundle.json"])
    assert tree["candidate_tree_sha256"] == bundle["candidate_tree_sha256"]
    assert tree["changed_paths"] == bundle["changed_paths"]
    assert tree["result_commit"] is None
    envelopes = json.loads(files["envelopes.json"])
    assert {item["publication_id"] for item in envelopes} == {
        item.publication_id for item in snapshot.publications
    }
    assert all(item["artifact_envelope_sha256"] for item in envelopes)
    overlap = json.loads(files["overlap.json"])
    assert overlap["observed"] is True and overlap["max_window_ms"] > 0
    unknowns = json.loads(files["unknowns.json"])
    assert unknowns["snapshot_unknowns"] == list(snapshot.unknowns)
    assert unknowns["bundle_unresolved_unknowns"] == bundle["unresolved_unknowns"]
    assert completed.exported["status"] == "exported"
    assert completed.exported["final_bundle_present"] is True
    assert completed.exported["manifest_sha256"] == sha256_hex(
        (capsule_dir / "manifest.json").read_bytes()
    )


@requires_scripted
def test_capsule_layout_is_private_and_symlink_free(completed: SimpleNamespace):
    assert stat.S_IMODE(completed.capsule_dir.lstat().st_mode) == 0o700
    for path in completed.capsule_dir.rglob("*"):
        metadata = path.lstat()
        assert not stat.S_ISLNK(metadata.st_mode)
        if stat.S_ISDIR(metadata.st_mode):
            assert stat.S_IMODE(metadata.st_mode) == 0o700, path
        else:
            assert stat.S_ISREG(metadata.st_mode)
            assert stat.S_IMODE(metadata.st_mode) & ~0o600 == 0, path
    assert {path.name for path in completed.capsule_dir.iterdir() if path.is_dir()} == {
        "plan",
        "attempts",
        "receipts",
    }


@requires_scripted
def test_capsule_redacts_every_private_artifact(completed: SimpleNamespace):
    files = _files(completed.capsule_dir)
    with sqlite3.connect(completed.evidence.path) as connection:
        rows = connection.execute(
            "SELECT kind, artifact_bytes FROM attempt_artifacts"
        ).fetchall()
    private = [
        (kind, content)
        for kind, content in rows
        if kind not in RECEIPT_KINDS and kind != "final-result-bundle"
    ]
    assert {kind for kind, _ in private} >= {"patch", "operator-input"}
    for kind, content in private:
        assert not any(blob == content for blob in files.values()), kind
        if kind in {"patch", "operator-input"}:
            assert not any(content in blob for blob in files.values()), kind
    for name, blob in files.items():
        assert SENTINEL not in blob, name
        assert b"diff --git" not in blob, name
    manifest = _manifest(completed.capsule_dir)
    assert set(manifest["excluded_artifact_kinds"]) >= {
        "changed-path-hunk-manifest",
        "command-template-receipt",
        "inherited-context-manifest",
        "patch",
        "resource-receipt",
    }
    assert manifest["excluded_artifact_kinds"]["patch"] >= 6
    assert not set(manifest["excluded_artifact_kinds"]) & RECEIPT_KINDS
    for name, blob in files.items():
        if name.startswith("receipts/"):
            keys = set(json.loads(blob))
            assert not keys & {"prompt", "output", "api_key", "stdout", "stderr"}


@requires_scripted
def test_export_refuses_existing_or_unsafe_destinations(
    completed: SimpleNamespace, tmp_path: Path
):
    arguments = {
        "store": completed.store,
        "evidence": completed.evidence,
        "mission_id": completed.mission_id,
    }
    with pytest.raises(CapsuleError, match="already exists"):
        export_mission_capsule(**arguments, output_dir=completed.output)
    with pytest.raises(CapsuleError, match="unavailable"):
        export_mission_capsule(**arguments, output_dir=tmp_path / "missing")
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(CapsuleError, match="non-symlink"):
        export_mission_capsule(**arguments, output_dir=link)
    with pytest.raises(CapsuleError, match="timezone-aware"):
        export_mission_capsule(
            **arguments, output_dir=tmp_path, now=datetime(2026, 8, 22, 12, 0)
        )
    with pytest.raises(CapsuleError, match="mission ID is invalid"):
        export_mission_capsule(
            store=completed.store,
            evidence=completed.evidence,
            mission_id="../escape",
            output_dir=tmp_path,
        )
    with pytest.raises(CapsuleError, match="could not be verified"):
        export_mission_capsule(
            store=completed.store,
            evidence=completed.evidence,
            mission_id="mission-unknown",
            output_dir=tmp_path,
        )
    other = SQLiteAttemptEvidenceStore(tmp_path / "other-evidence.sqlite3")
    with pytest.raises(CapsuleError, match="bound resolver"):
        export_mission_capsule(
            store=completed.store,
            evidence=other,
            mission_id=completed.mission_id,
            output_dir=tmp_path,
        )
    assert not any(path.name.endswith(CAPSULE_SUFFIX) for path in tmp_path.iterdir())


@requires_scripted
def test_tampered_event_line_fails_naming_the_seq(
    completed: SimpleNamespace, tmp_path: Path
):
    copied = _copy(completed.capsule_dir, tmp_path)
    events = copied / "events.ndjson"

    def tamper_payload(value: dict) -> None:
        value["payload"] = {**value["payload"], "status": "tampered"}

    _rewrite_line(events, 5, tamper_payload)
    unsigned = _failure(verify_mission_capsule(copied))
    assert unsigned["name"] == "manifest_file_digests"
    assert "events.ndjson" in unsigned["detail"]

    _resign_manifest(copied)
    failure = _failure(verify_mission_capsule(copied))
    assert failure["name"] == "mission_event_chain"
    assert "seq 5" in failure["detail"] and "payload digest" in failure["detail"]

    relinked = _copy(completed.capsule_dir, tmp_path / "relinked")

    def tamper_link(value: dict) -> None:
        value["previous_event_sha256"] = "0" * 64

    _rewrite_line(relinked / "events.ndjson", 9, tamper_link)
    _resign_manifest(relinked)
    failure = _failure(verify_mission_capsule(relinked))
    assert failure["name"] == "mission_event_chain"
    assert "seq 9" in failure["detail"]


@requires_scripted
def test_tampered_attempt_chain_fails_naming_the_attempt(
    completed: SimpleNamespace, tmp_path: Path
):
    copied = _copy(completed.capsule_dir, tmp_path)
    entry = _manifest(copied)["attempts"][0]

    def tamper(value: dict) -> None:
        value["payload"] = {**value["payload"], "worker_id": "impostor"}

    _rewrite_line(copied / entry["file"], 1, tamper)
    _resign_manifest(copied)
    failure = _failure(verify_mission_capsule(copied))
    assert failure["name"] == "attempt_evidence_chains"
    assert entry["attempt_id"] in failure["detail"]
    assert "seq 1" in failure["detail"]


@requires_scripted
def test_tampered_receipt_fails_naming_the_reference_id(
    completed: SimpleNamespace, tmp_path: Path
):
    copied = _copy(completed.capsule_dir, tmp_path)
    entry = _manifest(copied)["receipts"][0]
    path = copied / entry["file"]
    value = json.loads(path.read_bytes())
    value["exit_code"] = 7
    path.write_bytes(canonical_json_bytes(value))
    _resign_manifest(copied)
    failure = _failure(verify_mission_capsule(copied))
    assert failure["name"] == "receipt_references"
    assert entry["id"] in failure["detail"] and "digest" in failure["detail"]

    orphan = _copy(completed.capsule_dir, tmp_path / "orphan")
    (orphan / "receipts" / "artifact_orphan.json").write_bytes(b"{}")
    _resign_manifest(orphan)
    failure = _failure(verify_mission_capsule(orphan))
    assert failure["name"] == "receipt_references"
    assert "artifact_orphan" in failure["detail"]


@requires_scripted
def test_tampered_envelope_and_plan_fail_naming_the_record(
    completed: SimpleNamespace, tmp_path: Path
):
    copied = _copy(completed.capsule_dir, tmp_path)
    path = copied / "envelopes.json"
    envelopes = json.loads(path.read_bytes())
    envelopes[0]["sha256"] = "f" * 64
    path.write_bytes(json.dumps(envelopes).encode())
    _resign_manifest(copied)
    failure = _failure(verify_mission_capsule(copied))
    assert failure["name"] == "publication_envelopes"
    assert envelopes[0]["publication_id"] in failure["detail"]

    planned = _copy(completed.capsule_dir, tmp_path / "planned")
    path = planned / "plan" / "revision-1.json"
    value = json.loads(path.read_bytes())
    value["plan"]["max_concurrency"] = 64
    path.write_bytes(json.dumps(value).encode())
    _resign_manifest(planned)
    failure = _failure(verify_mission_capsule(planned))
    assert failure["name"] == "plan_revisions"
    assert "revision 1" in failure["detail"]


@requires_scripted
def test_deleted_final_bundle_fails_unless_manifest_says_absent(
    completed: SimpleNamespace, tmp_path: Path
):
    copied = _copy(completed.capsule_dir, tmp_path)
    (copied / "final-bundle.json").unlink()
    failure = _failure(verify_mission_capsule(copied))
    assert failure["name"] == "manifest_file_digests"
    assert "final-bundle.json" in failure["detail"]

    absent = _copy(completed.capsule_dir, tmp_path / "absent")
    (absent / "final-bundle.json").unlink()
    (absent / "tree-manifest.json").write_bytes(
        json.dumps({"present": False, "note": "none registered"}).encode()
    )
    manifest = _manifest(absent)
    manifest["final_bundle"] = {"present": False, "note": "none registered"}
    _resign_manifest(absent, manifest)
    result = verify_mission_capsule(absent)
    assert result["verified"] is True
    final = next(item for item in result["checks"] if item["name"] == "final_bundle")
    assert "absent" in final["detail"]
    assert any("final result bundle" in item for item in result["not_checked"])

    lying = _copy(completed.capsule_dir, tmp_path / "lying")
    manifest = _manifest(lying)
    manifest["final_bundle"] = {"present": False, "note": "none registered"}
    _resign_manifest(lying, manifest)
    failure = _failure(verify_mission_capsule(lying))
    assert failure["name"] == "final_bundle"
    assert "manifest says none" in failure["detail"]


def test_proposed_mission_capsule_has_no_bundle_and_verifies(tmp_path: Path):
    runtime = tmp_path / "runtime"
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    mission_id = "mission-capsule-proposed"
    propose_scripted_mission(
        scenario=load_scenario(),
        store=store,
        runtime=runtime,
        mission_id=mission_id,
        created_at=NOW,
    )
    evidence = SQLiteAttemptEvidenceStore(runtime / "attempt-evidence.sqlite3")
    output = tmp_path / "out"
    output.mkdir(mode=0o700)

    exported = export_mission_capsule(
        store=store,
        evidence=evidence,
        mission_id=mission_id,
        output_dir=output,
        now=NOW,
    )

    assert store.artifact_resolver is evidence
    assert exported["final_bundle_present"] is False
    capsule_dir = Path(exported["capsule_dir"])
    manifest = _manifest(capsule_dir)
    assert manifest["mission_status"] == "proposed"
    assert manifest["final_bundle"]["present"] is False
    assert manifest["attempts"] == [] and manifest["receipts"] == []
    assert manifest["excluded_artifact_kinds"] == {}
    assert json.loads((capsule_dir / "envelopes.json").read_bytes()) == []
    assert (
        json.loads((capsule_dir / "tree-manifest.json").read_bytes())["present"]
        is False
    )
    assert (
        json.loads((capsule_dir / "unknowns.json").read_bytes())[
            "bundle_unresolved_unknowns"
        ]
        is None
    )
    result = verify_mission_capsule(capsule_dir)
    assert result["verified"] is True
    assert [item["name"] for item in result["checks"]] == EXPECTED_CHECKS
    assert any("none was registered" in item for item in result["not_checked"])


def test_verify_rejects_non_directories_and_unreadable_manifests(tmp_path: Path):
    with pytest.raises(CapsuleError, match="unavailable"):
        verify_mission_capsule(tmp_path / "missing")
    regular = tmp_path / "capsule.json"
    regular.write_bytes(b"{}")
    with pytest.raises(CapsuleError, match="not a directory"):
        verify_mission_capsule(regular)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(CapsuleError, match="manifest is unavailable"):
        verify_mission_capsule(empty)
    link = tmp_path / "link"
    link.symlink_to(empty, target_is_directory=True)
    with pytest.raises(CapsuleError, match="not a directory"):
        verify_mission_capsule(link)
    wrong = tmp_path / "wrong"
    wrong.mkdir()
    (wrong / "manifest.json").write_bytes(b'{"schema": "other"}')
    with pytest.raises(CapsuleError, match="schema"):
        verify_mission_capsule(wrong)
    malformed = tmp_path / "malformed"
    malformed.mkdir()
    (malformed / "manifest.json").write_bytes(
        json.dumps({"schema": CAPSULE_SCHEMA, "mission_id": "m", "head": {}}).encode()
    )
    with pytest.raises(CapsuleError, match="head is malformed"):
        verify_mission_capsule(malformed)


@requires_scripted
def test_main_verify_reports_exit_codes(
    completed: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    assert capsule.main(["verify", str(completed.capsule_dir)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["verified"] is True
    assert printed["mission_id"] == completed.mission_id

    copied = _copy(completed.capsule_dir, tmp_path)
    (copied / "events.ndjson").write_bytes(b"")
    assert capsule.main(["verify", str(copied)]) == 1
    printed = json.loads(capsys.readouterr().out)
    assert printed["verified"] is False

    assert capsule.main(["verify", str(tmp_path / "missing")]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "error:" in captured.err


def test_rewind_plan_reconstructs_previous_revision_only_when_digest_matches():
    previous = _plan("mission-rewind")
    by_id = {task.task_id: task for task in previous.tasks}
    changed = by_id["work-a"].model_copy(update={"priority": 9})
    added = _task("work-c", "patch-c", "patch", "app/c.py", priority=0)
    current = Plan(
        mission_id="mission-rewind",
        revision=2,
        previous_revision=1,
        criteria=(
            previous.criteria[0].model_copy(
                update={"description": "All checks pass twice."}
            ),
        ),
        tasks=tuple(
            sorted(
                (
                    *(task for task in previous.tasks if task.task_id != "work-a"),
                    changed,
                    added,
                ),
                key=lambda item: item.task_id,
            )
        ),
        max_concurrency=3,
    )
    diff = SQLiteMissionStore._plan_diff(previous, current)

    assert rewind_plan(current, diff) == previous

    forged = {**diff, "previous_plan_sha256": "0" * 64}
    with pytest.raises(CapsuleError, match="could not be reconstructed"):
        rewind_plan(current, forged)
    with pytest.raises(CapsuleError, match="does not describe"):
        rewind_plan(current, {**diff, "plan_revision": 3})


def test_export_cleans_up_when_a_file_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    runtime = tmp_path / "runtime"
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    mission_id = "mission-capsule-failed-write"
    propose_scripted_mission(
        scenario=load_scenario(), store=store, runtime=runtime, mission_id=mission_id
    )
    evidence = SQLiteAttemptEvidenceStore(runtime / "attempt-evidence.sqlite3")
    output = tmp_path / "out"
    output.mkdir(mode=0o700)
    original = capsule._write_private_file

    def failing(path: Path, content: bytes) -> None:
        if path.name == "VERIFY.md":
            raise OSError("disk full")
        original(path, content)

    monkeypatch.setattr(capsule, "_write_private_file", failing)
    with pytest.raises(CapsuleError, match="could not be written"):
        export_mission_capsule(
            store=store, evidence=evidence, mission_id=mission_id, output_dir=output
        )
    assert list(output.iterdir()) == []
    assert os.path.isdir(output)
