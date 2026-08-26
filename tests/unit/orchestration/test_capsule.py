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

from graphene.hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from graphene.orchestration import capsule
from graphene.orchestration.capsule import (
    AUTHORITY_NOTE,
    CAPSULE_SCHEMA,
    CAPSULE_SUFFIX,
    NOT_VERIFIABLE_OFFLINE,
    PRODUCER_NOTE,
    RECEIPT_KINDS,
    REDACTION_NOTE,
    CapsuleError,
    export_mission_capsule,
    rewind_plan,
    verify_mission_capsule,
)
from graphene.orchestration.evidence import SQLiteAttemptEvidenceStore
from graphene.orchestration.mission_models import MissionEventType, MissionStatus, Plan
from graphene.orchestration.scripted import (
    load_scenario,
    propose_scripted_mission,
    run_scripted_mission,
    scripted_supported,
)
from graphene.orchestration.sqlite_mission_store import SQLiteMissionStore
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
    "attempt_coverage",
    "manifest_summary",
]
PROVIDER_RECEIPT_ID = "artifact_provider_receipt_0001"

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


def _events(capsule_dir: Path) -> list[dict]:
    raw = (capsule_dir / "events.ndjson").read_bytes()
    return [json.loads(line) for line in raw.split(b"\n") if line]


def _rechain(path: Path) -> tuple[int, str]:
    """Re-link an ndjson hash chain after tampering, as any producer could."""

    lines = [json.loads(line) for line in path.read_bytes().split(b"\n") if line]
    previous: str | None = None
    rebuilt = []
    for number, value in enumerate(lines, 1):
        value["seq"] = number
        value["previous_event_sha256"] = previous
        value["payload_sha256"] = canonical_json_sha256(value["payload"])
        value.pop("event_sha256", None)
        previous = value["event_sha256"] = canonical_json_sha256(value)
        rebuilt.append(canonical_json_bytes(value))
    path.write_bytes(b"".join(line + b"\n" for line in rebuilt))
    assert previous is not None
    return len(rebuilt), previous


def _reforge(capsule_dir: Path, manifest: dict | None = None) -> None:
    """Re-chain every event file, restate the manifest heads, and re-sign.

    This is everything an unsigned capsule lets a tamperer do. The verifier
    accepts the result, which is exactly why it must disclaim producer
    authenticity in ``not_checked`` instead of implying it.
    """

    manifest = _manifest(capsule_dir) if manifest is None else manifest
    count, head = _rechain(capsule_dir / "events.ndjson")
    manifest["head"] = {"seq": count, "event_count": count, "event_sha256": head}
    manifest["counts"]["events"] = count
    total = 0
    for entry in manifest["attempts"]:
        count, head = _rechain(capsule_dir / entry["file"])
        entry["event_count"], entry["event_sha256"] = count, head
        total += count
    manifest["counts"]["attempt_evidence_events"] = total
    _resign_manifest(capsule_dir, manifest)


def _provider_receipt() -> dict:
    from graphene.orchestration.worker_runtime import WorkerProviderReceipt

    return WorkerProviderReceipt(
        driver="adk_fake",
        client_version="test",
        requested_model="stub-model",
        returned_model="stub-model",
        credential_mode="not_applicable",
        input_bytes=12,
        output_bytes=34,
        latency_ms=5,
        call_started_at="2026-08-20T00:00:00.000Z",
        call_ended_at="2026-08-20T00:00:00.005Z",
        usage_source="unavailable",
    ).model_dump(mode="json")


def _inject_provider_receipt(capsule_dir: Path, content: bytes) -> str:
    """Bind a worker-provider-receipt file to the first attempt chain and re-forge."""

    manifest = _manifest(capsule_dir)
    entry = manifest["attempts"][0]
    name = f"receipts/{PROVIDER_RECEIPT_ID}.json"
    (capsule_dir / name).write_bytes(content)
    reference = {
        "kind": "worker-provider-receipt",
        "id": PROVIDER_RECEIPT_ID,
        "sha256": sha256_hex(content),
    }

    def attach(value: dict) -> None:
        value["references"] = [*value["references"], reference]

    _rewrite_line(capsule_dir / entry["file"], entry["event_count"], attach)
    manifest["receipts"].append(
        {
            "id": PROVIDER_RECEIPT_ID,
            "kind": "worker-provider-receipt",
            "sha256": reference["sha256"],
            "bytes": len(content),
            "attempt_ids": [entry["attempt_id"]],
            "file": name,
        }
    )
    manifest["counts"]["receipts"] += 1
    _reforge(capsule_dir, manifest)
    return entry["attempt_id"]


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
    summary = next(
        item for item in result["checks"] if item["name"] == "manifest_summary"
    )
    assert "mission_status proposed" in summary["detail"]

    # The layout is exact even when a directory is empty: dropping one fails.
    (capsule_dir / "attempts").rmdir()
    failure = _failure(verify_mission_capsule(capsule_dir))
    assert failure["name"] == "manifest_file_digests"
    assert "missing=['attempts']" in failure["detail"]


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


def test_export_removes_the_capsule_directory_when_its_chmod_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    runtime = tmp_path / "runtime"
    store = SQLiteMissionStore(tmp_path / "missions.sqlite")
    mission_id = "mission-capsule-failed-chmod"
    propose_scripted_mission(
        scenario=load_scenario(), store=store, runtime=runtime, mission_id=mission_id
    )
    evidence = SQLiteAttemptEvidenceStore(runtime / "attempt-evidence.sqlite3")
    output = tmp_path / "out"
    output.mkdir(mode=0o700)
    original = os.chmod

    def failing(path, mode, *args, **kwargs):
        if Path(path).name.endswith(CAPSULE_SUFFIX):
            raise PermissionError("chmod denied")
        return original(path, mode, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(capsule.os, "chmod", failing)
        with pytest.raises(CapsuleError, match="could not be written"):
            export_mission_capsule(
                store=store, evidence=evidence, mission_id=mission_id, output_dir=output
            )
    # No empty capsule directory survives the failure, so a retry can succeed.
    assert list(output.iterdir()) == []

    exported = export_mission_capsule(
        store=store, evidence=evidence, mission_id=mission_id, output_dir=output
    )
    assert verify_mission_capsule(Path(exported["capsule_dir"]))["verified"] is True


@requires_scripted
def test_rechained_capsule_verifies_and_verifier_disclaims_producer_authenticity(
    completed: SimpleNamespace, tmp_path: Path
):
    # Events up to the final bundle's head are pinned a second time by the
    # bundle's event_head_sha256, so re-chaining them breaks that binding.
    pinned = _copy(completed.capsule_dir, tmp_path / "pinned")
    approved = next(
        item["seq"] for item in _events(pinned) if item["event_type"] == "plan.approved"
    )

    def forge_rationale(value: dict) -> None:
        value["payload"] = {**value["payload"], "operator_rationale": "Forged."}

    _rewrite_line(pinned / "events.ndjson", approved, forge_rationale)
    assert _failure(verify_mission_capsule(pinned))["name"] == "manifest_file_digests"
    _reforge(pinned)
    failure = _failure(verify_mission_capsule(pinned))
    assert failure["name"] == "final_bundle" and "event head" in failure["detail"]

    # Past that head nothing but the chain itself binds the record: a re-chained,
    # self-consistent capsule verifies because there is no signature to break.
    copied = _copy(completed.capsule_dir, tmp_path)
    last = _events(copied)[-1]
    assert last["event_type"] == "final_result_bundle.ready"

    def forge_status(value: dict) -> None:
        value["payload"] = {**value["payload"], "status": "forged"}

    _rewrite_line(copied / "events.ndjson", last["seq"], forge_status)
    _reforge(copied)
    result = verify_mission_capsule(copied)

    # So the verifier must say plainly that it proves internal consistency,
    # not who produced the capsule.
    assert result["verified"] is True
    assert any("signature" in item for item in result["not_checked"])
    assert any(PRODUCER_NOTE in item for item in result["not_checked"])
    assert any("graphene mission db verify" in item for item in result["not_checked"])
    verify_document = (copied / "VERIFY.md").read_text()
    assert "signature" in verify_document and PRODUCER_NOTE in verify_document
    assert "producer authenticity" in _manifest(copied)["not_verifiable_offline"]


@requires_scripted
def test_tampered_manifest_summary_fails_naming_the_field(
    completed: SimpleNamespace, tmp_path: Path
):
    original = _manifest(completed.capsule_dir)
    failed = next(item for item in original["attempts"] if item["state"] == "failed")
    first = original["attempts"][0]

    def tampered(label: str, mutate) -> str:
        copied = _copy(completed.capsule_dir, tmp_path / label)
        manifest = _manifest(copied)
        mutate(manifest)
        _resign_manifest(copied, manifest)
        failure = _failure(verify_mission_capsule(copied))
        assert failure["name"] == "manifest_summary", (label, failure)
        return failure["detail"]

    def approve(manifest: dict) -> None:
        manifest["final_bundle"]["decision"] = {
            "state": "approved",
            "event_seq": manifest["head"]["seq"],
        }

    detail = tampered("decision", approve)
    assert "decision" in detail and "approved" in detail and "pending" in detail

    def complete(manifest: dict) -> None:
        manifest["mission_status"] = "completed"
        manifest["mission"]["status"] = "completed"

    detail = tampered("status", complete)
    assert "mission_status" in detail and "awaiting_result" in detail

    def entry(manifest: dict, attempt_id: str) -> dict:
        return next(
            item for item in manifest["attempts"] if item["attempt_id"] == attempt_id
        )

    def pass_the_failed_attempt(manifest: dict) -> None:
        entry(manifest, failed["attempt_id"])["state"] = "committed"
        entry(manifest, failed["attempt_id"])["result_code"] = "passed"

    detail = tampered("state", pass_the_failed_attempt)
    assert failed["attempt_id"] in detail and "state" in detail

    def relabel_result(manifest: dict) -> None:
        entry(manifest, failed["attempt_id"])["result_code"] = "passed"

    detail = tampered("result", relabel_result)
    assert failed["attempt_id"] in detail and "result_code" in detail

    def impostor(manifest: dict) -> None:
        entry(manifest, first["attempt_id"])["worker_id"] = "impostor"

    detail = tampered("worker", impostor)
    assert first["attempt_id"] in detail and "worker_id" in detail

    def inflate(manifest: dict) -> None:
        manifest["counts"]["events"] = 999

    detail = tampered("counts", inflate)
    assert "counts.events" in detail and "999" in detail

    def undercount(manifest: dict) -> None:
        manifest["excluded_artifact_kinds"]["patch"] -= 1
        manifest["counts"]["excluded_artifacts"] -= 1

    detail = tampered("excluded", undercount)
    assert "excluded_artifact_kinds" in detail

    # base_sha, policy_id, revision, and policy_sha256 are already bound by the
    # final bundle check; repo_id is only provable from project.created.
    def repolicy(manifest: dict) -> None:
        manifest["policy"]["repo_id"] = "repo_forged"

    detail = tampered("policy", repolicy)
    assert "policy" in detail and "project.created" in detail


@requires_scripted
def test_dropped_attempt_chain_fails_unless_declared_honestly(
    completed: SimpleNamespace, tmp_path: Path
):
    copied = _copy(completed.capsule_dir, tmp_path)
    manifest = _manifest(copied)
    entry = next(item for item in manifest["attempts"] if item["state"] == "failed")
    attempt_id = entry["attempt_id"]
    owned = [
        item for item in manifest["receipts"] if item["attempt_ids"] == [attempt_id]
    ]
    assert owned, "the failed attempt minted its own check receipt"
    (copied / entry["file"]).unlink()
    for receipt in owned:
        (copied / receipt["file"]).unlink()
    manifest["attempts"] = [
        item for item in manifest["attempts"] if item["attempt_id"] != attempt_id
    ]
    manifest["receipts"] = [item for item in manifest["receipts"] if item not in owned]
    manifest["counts"]["attempt_evidence_chains"] -= 1
    manifest["counts"]["attempt_evidence_events"] -= entry["event_count"]
    manifest["counts"]["receipts"] -= len(owned)
    _resign_manifest(copied, manifest)

    failure = _failure(verify_mission_capsule(copied))
    assert failure["name"] == "attempt_coverage"
    assert attempt_id in failure["detail"] and "neither" in failure["detail"]

    declared = {
        "attempt_id": attempt_id,
        "task_id": entry["task_id"],
        "state": "committed",
        "reason": "attempt has no evidence link",
    }
    manifest["attempts_without_evidence"] = [declared]
    _resign_manifest(copied, manifest)
    failure = _failure(verify_mission_capsule(copied))
    assert failure["name"] == "manifest_summary"
    assert attempt_id in failure["detail"] and "state" in failure["detail"]

    declared["state"] = "failed"
    _resign_manifest(copied, manifest)
    result = verify_mission_capsule(copied)
    assert result["verified"] is True
    coverage = next(
        item for item in result["checks"] if item["name"] == "attempt_coverage"
    )
    assert "1 declared without evidence" in coverage["detail"]
    assert any("attempts without evidence" in item for item in result["not_checked"])

    ghost = _copy(completed.capsule_dir, tmp_path / "ghost")
    manifest = _manifest(ghost)
    manifest["attempts_without_evidence"] = [
        {**declared, "attempt_id": "attempt_ghost"}
    ]
    _resign_manifest(ghost, manifest)
    failure = _failure(verify_mission_capsule(ghost))
    assert failure["name"] == "attempt_coverage"
    assert "attempt_ghost" in failure["detail"] and "never leased" in failure["detail"]


@requires_scripted
def test_worker_provider_receipt_is_schema_validated(
    completed: SimpleNamespace, tmp_path: Path
):
    valid = _provider_receipt()
    genuine = _copy(completed.capsule_dir, tmp_path / "genuine")
    _inject_provider_receipt(genuine, canonical_json_bytes(valid))
    result = verify_mission_capsule(genuine)
    assert result["verified"] is True
    contents = next(
        item for item in result["checks"] if item["name"] == "receipt_contents"
    )
    assert "1 worker provider receipts" in contents["detail"]

    cases = {
        "extra": (
            canonical_json_bytes({**valid, "note": "x"}),
            "not a valid WorkerProviderReceipt",
        ),
        "prompt": (
            canonical_json_bytes({**valid, "prompt": "secret"}),
            "non-public key",
        ),
        "order": (json.dumps(valid, indent=2).encode(), "not canonical JSON"),
        "defaults": (
            canonical_json_bytes({k: v for k, v in valid.items() if k != "framework"}),
            "canonical bytes of its WorkerProviderReceipt",
        ),
    }
    for label, (content, message) in cases.items():
        copied = _copy(completed.capsule_dir, tmp_path / label)
        _inject_provider_receipt(copied, content)
        failure = _failure(verify_mission_capsule(copied))
        assert failure["name"] == "receipt_contents", (label, failure)
        assert PROVIDER_RECEIPT_ID in failure["detail"], (label, failure)
        assert message in failure["detail"], (label, failure)


@requires_scripted
def test_unlisted_directory_fails_naming_it(completed: SimpleNamespace, tmp_path: Path):
    copied = _copy(completed.capsule_dir, tmp_path)
    (copied / "evil" / "nested").mkdir(parents=True)
    failure = _failure(verify_mission_capsule(copied))
    assert failure["name"] == "manifest_file_digests"
    assert "unlisted=['evil', 'evil/nested']" in failure["detail"]


def test_recorded_plan_digests_fail_closed_on_conflicting_events():
    def event(event_type: MissionEventType, **payload) -> SimpleNamespace:
        return SimpleNamespace(event_type=event_type, payload=payload)

    events = [
        event(MissionEventType.PLAN_PROPOSED, plan_revision=1, plan_sha256="a" * 64),
        event(MissionEventType.PLAN_VALIDATED, plan_revision=1, plan_sha256="c" * 64),
        event(MissionEventType.PLAN_REVISED, plan_revision=2, plan_sha256="b" * 64),
    ]
    assert capsule._recorded_plan_digests(events) == {1: "a" * 64, 2: "b" * 64}

    conflicting = [
        *events,
        event(MissionEventType.PLAN_PROPOSED, plan_revision=1, plan_sha256="d" * 64),
    ]
    with pytest.raises(CapsuleError, match="revision 1 has conflicting"):
        capsule._recorded_plan_digests(conflicting)
    with pytest.raises(capsule._CheckFailed, match="revision 1 has conflicting"):
        capsule._recorded_plan_digests(conflicting, failure=capsule._CheckFailed)
    malformed = [
        event(MissionEventType.PLAN_PROPOSED, plan_revision="1", plan_sha256="a" * 64)
    ]
    with pytest.raises(capsule._CheckFailed, match="malformed"):
        capsule._recorded_plan_digests(malformed, failure=capsule._CheckFailed)


@requires_scripted
def test_conflicting_plan_digest_event_fails_closed_in_the_verifier(
    completed: SimpleNamespace, tmp_path: Path
):
    copied = _copy(completed.capsule_dir, tmp_path)
    path = copied / "events.ndjson"
    proposed = next(
        item for item in _events(copied) if item["event_type"] == "plan.proposed"
    )
    forged = {**proposed, "payload": {**proposed["payload"], "plan_sha256": "f" * 64}}
    path.write_bytes(path.read_bytes() + canonical_json_bytes(forged) + b"\n")
    _reforge(copied)

    failure = _failure(verify_mission_capsule(copied))
    assert failure["name"] == "plan_revisions"
    assert "revision 1" in failure["detail"] and "conflicting" in failure["detail"]


def test_fake_adk_mission_capsule_reports_provider_call_overlap_and_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A two-worker fake ADK mission exports its bound receipts and call windows."""

    from graphene.cli import mission as mission_cli
    from graphene.orchestration.overlap import OverlapMeasurement
    from tests.unit.orchestration.test_gemini_mission_runtime import (
        prepare_fake_two_worker_mission,
        quiet_resource_sampler,
    )

    prepared = prepare_fake_two_worker_mission(tmp_path, monkeypatch)
    result = mission_cli._execute_adk_mission(
        store=prepared.store,
        mission_id=prepared.mission_id,
        registry=prepared.registry,
        check_runner=mission_cli._policy_check,
        resource_sampler=quiet_resource_sampler,
    )
    assert result["status"] == "awaiting_result"
    output = tmp_path / "capsules"
    output.mkdir()
    evidence = mission_cli._mission_evidence(prepared.store, prepared.mission_id)
    exported = export_mission_capsule(
        store=prepared.store,
        evidence=evidence,
        mission_id=prepared.mission_id,
        output_dir=output,
    )
    capsule_dir = Path(exported["capsule_dir"])
    overlap = OverlapMeasurement.model_validate_json(
        (capsule_dir / "overlap.json").read_bytes()
    )
    assert overlap.model_dump(mode="json") == result["parallel_overlap"]
    assert {pair.basis for pair in overlap.pairs} >= {
        "attempt_timestamps",
        "provider_call_timestamps",
    }
    receipts = sorted(path.name for path in (capsule_dir / "receipts").iterdir())
    kinds = {
        json.loads((capsule_dir / "receipts" / name).read_bytes()).get("driver")
        for name in receipts
    }
    assert "adk_fake" in kinds
    verified = verify_mission_capsule(capsule_dir)
    assert verified["verified"] is True
