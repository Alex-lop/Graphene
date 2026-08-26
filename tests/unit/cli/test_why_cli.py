"""``graphene why`` on a mission: ``--json`` flag and the judge-legible render.

The sandbox-gated tests drive a real scripted-local Taskmaster mission so the
causal result is built from hash-chained events and resolvable receipts; the
remaining tests are sandbox-free and cover the CLI surface and the renderer.
"""

from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

import graphene.cli.mission as mission_cli
from graphene.cli.main import build_parser, main
from graphene.hashing import canonical_json_bytes, sha256_hex
from graphene.orchestration.causal_query import RECEIPT_REFERENCE_KINDS, why
from graphene.orchestration.mission_models import MissionStatus
from graphene.orchestration.scripted import (
    load_scenario,
    run_scripted_mission,
    scripted_supported,
)
from graphene.orchestration.sqlite_mission_store import SQLiteMissionStore
from tests.unit.orchestration.test_store import NOW, _command, _complete_ready, _create

QUERY_PATH = "status_report/redact.py"
#: The work-a output of the sandbox-free store fixture in test_store.
QUERY_PATH_A = "app/a.py"
STAGES = [
    "target",
    "producer_attempt",
    "prior_attempts",
    "accepted_inputs",
    "assembly_candidate",
    "verification",
    "approval",
]
TRUST_LINE = (
    "TRUST: every line above is derived from hash-chained mission events and "
    "resolvable evidence references; unknowns are listed, never guessed."
)

requires_scripted = pytest.mark.skipif(
    not scripted_supported(),
    reason="a completed scripted-local mission needs the macOS fixture sandbox",
)


@pytest.fixture(scope="module")
def completed(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    if not scripted_supported():
        pytest.skip("scripted-local mission requires the macOS fixture sandbox")
    state = tmp_path_factory.mktemp("why") / "state"
    state.mkdir(mode=0o700)
    mission_id = "mission-why-001"
    # Same layout the CLI derives from GRAPHENE_STATE_DIR for this mission id.
    runtime = state / "missions" / sha256_hex(mission_id.encode())[:32]
    store = SQLiteMissionStore(state / "missions.sqlite3")
    run_scripted_mission(
        scenario=load_scenario(),
        store=store,
        runtime=runtime,
        mission_id=mission_id,
    )
    snapshot = store.snapshot(mission_id)
    assert snapshot.mission.status == MissionStatus.AWAITING_RESULT
    assert store.verify(mission_id) == snapshot.head
    return SimpleNamespace(
        state=state, mission_id=mission_id, store=store, snapshot=snapshot
    )


@requires_scripted
def test_why_json_flag_emits_canonical_causal_result_with_attempt_identity(
    completed: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(completed.state))

    code = main(["why", QUERY_PATH, "--mission", completed.mission_id, "--json"])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert canonical_json_bytes(payload).decode() + "\n" == captured.out
    assert payload["mission_id"] == completed.mission_id
    assert payload["query"] == QUERY_PATH
    assert payload["matched_by"] == "path"
    assert payload["snapshot_sha256"] == completed.snapshot.snapshot_sha256
    assert payload["event_head_sha256"] == completed.snapshot.head.event_sha256
    assert [link["stage"] for link in payload["links"]] == STAGES
    producer = payload["links"][1]
    assert producer["status"] == "established"
    attempts = {item.attempt_id: item for item in completed.snapshot.attempts}
    attempt_nodes = [n for n in producer["nodes"] if n["node_type"] == "attempt"]
    assert attempt_nodes
    for node in attempt_nodes:
        attempt = attempts[node["node_id"]]
        assert node["worker_id"] == attempt.worker_id
        assert node["worker_id"].startswith("scripted-worker-")
        assert node["fencing_token"] == attempt.fencing_token >= 1
        assert node["attempt_number"] == attempt.attempt_number == 1
        assert node["task_id"] == attempt.task_id
    receipts = [n for n in producer["nodes"] if n["node_type"] == "reference"]
    assert receipts
    assert {n["kind"] for n in receipts} == {"test-receipt"}
    assert all(n["resolvable"] is True for n in receipts)
    assert {n["attempt_id"] for n in receipts} <= {n["node_id"] for n in attempt_nodes}
    # Verification receipts are attached to the verification stage too.
    verification = payload["links"][4]
    assert verification["status"] == "established"
    assert any(
        n["node_type"] == "reference" and n["kind"] == "test-receipt"
        for n in verification["nodes"]
    )
    # Public metadata only: no private keys, no artifact bytes.
    for forbidden in ("prompt", "artifact_bytes", "api_key", "credential"):
        assert forbidden not in captured.out
    # The local flag and the global flag produce identical bytes.
    assert main(["--json", "why", QUERY_PATH, "--mission", completed.mission_id]) == 0
    assert capsys.readouterr().out == captured.out


@requires_scripted
def test_why_human_render_is_judge_legible(
    completed: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(completed.state))
    assert main(["why", QUERY_PATH, "--mission", completed.mission_id, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    code = main(["why", QUERY_PATH, "--mission", completed.mission_id])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    lines = captured.out.splitlines()
    assert lines[0] == f"WHY {completed.mission_id} {QUERY_PATH} matched_by=path"
    assert "STAGE target established" in lines
    assert "STAGE producer_attempt established" in lines
    assert "STAGE verification established" in lines
    receipt_lines = [
        line for line in lines if line.startswith("  receipt test-receipt ")
    ]
    assert receipt_lines
    assert all(line.endswith(" resolvable=True") for line in receipt_lines)
    attempt_lines = [line for line in lines if line.startswith("  node attempt ")]
    assert attempt_lines
    assert all(
        " worker=scripted-worker-" in line
        and " attempt_number=1 " in line
        and " fence=" in line
        for line in attempt_lines
    )
    assert any(line.startswith("  events ") for line in lines)
    assert any(line.startswith("  note ") for line in lines)
    assert lines[-1] == TRUST_LINE
    assert captured.out == mission_cli._render_why(payload)


def test_why_parser_accepts_local_json_flag_without_touching_global_flag() -> None:
    local = build_parser().parse_args(["why", "p", "--mission", "m", "--json"])
    assert local.json_mode_local is True
    assert local.json_mode is False
    for_run = build_parser().parse_args(["why", "p", "--run", "run_1", "--json"])
    assert for_run.json_mode_local is True
    plain = build_parser().parse_args(["why", "p", "--mission", "m"])
    assert plain.json_mode_local is False
    assert plain.json_mode is False


def test_mission_handle_honours_local_json_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    value = {
        "mission_id": "mission_1",
        "query": "app/a.py",
        "matched_by": "none",
        "plan_revision": 1,
        "plan_sha256": "cd" * 32,
        "approved_plan_revision": None,
        "links": [],
        "unknowns": ["No committed publication or artifact matches app/a.py."],
    }
    monkeypatch.setattr(mission_cli, "_why_value", lambda _args: value)

    args = build_parser().parse_args(
        ["why", "app/a.py", "--mission", "mission_1", "--json"]
    )
    assert mission_cli.handle(args) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == canonical_json_bytes(value).decode() + "\n"

    args = build_parser().parse_args(["why", "app/a.py", "--mission", "mission_1"])
    assert mission_cli.handle(args) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == (
        "WHY mission_1 app/a.py matched_by=none\n"
        "PLAN v1 sha256:cdcdcdcdcdcd… approval: none\n"
        "UNKNOWN No committed publication or artifact matches app/a.py.\n"
        f"{TRUST_LINE}\n"
    )


def test_render_why_labels_receipts_nodes_events_and_unknowns() -> None:
    digest = "ab" * 32
    value = {
        "mission_id": "mission_1",
        "query": "app/a.py",
        "matched_by": "path",
        "plan_revision": 2,
        "plan_sha256": digest,
        "approved_plan_revision": 2,
        "links": [
            {
                "stage": "target",
                "status": "established",
                "nodes": [
                    {
                        "node_type": "publication",
                        "node_id": "pub_1",
                        "kind": "patch",
                        "sha256": digest,
                        "task_id": "task_a",
                        "attempt_id": "attempt_1",
                        "paths": ["app/a.py"],
                        "resolvable": None,
                        "worker_id": None,
                        "fencing_token": None,
                        "attempt_number": None,
                    }
                ],
                "event_ids": ["event_3", "event_4"],
                "note": "Committed publication metadata matches the query.",
            },
            {
                "stage": "producer_attempt",
                "status": "established",
                "nodes": [
                    {
                        "node_type": "attempt",
                        "node_id": "attempt_1",
                        "kind": None,
                        "sha256": None,
                        "task_id": "task_a",
                        "attempt_id": "attempt_1",
                        "paths": [],
                        "resolvable": None,
                        "worker_id": "worker-1",
                        "fencing_token": 7,
                        "attempt_number": 2,
                    },
                    {
                        "node_type": "reference",
                        "node_id": "receipt_1",
                        "kind": "test-receipt",
                        "sha256": digest,
                        "task_id": "task_a",
                        "attempt_id": "attempt_1",
                        "paths": [],
                        "resolvable": True,
                    },
                    {
                        "node_type": "reference",
                        "node_id": "provider_1",
                        "kind": "worker-provider-receipt",
                        "sha256": digest,
                        "resolvable": False,
                    },
                ],
                "event_ids": ["event_2"],
                "note": "The verified snapshot binds each target to its producer attempt.",
            },
            {
                "stage": "accepted_inputs",
                "status": "established",
                "nodes": [
                    {
                        "node_type": "reference",
                        "node_id": "input_1",
                        "kind": "patch",
                        "sha256": digest,
                        "resolvable": None,
                    }
                ],
                "event_ids": [],
                "note": "Producer attempts declare these exact accepted inputs.",
            },
            {
                "stage": "approval",
                "status": "unknown",
                "nodes": [{"node_type": "event", "node_id": "event_9"}],
                "event_ids": ["event_9"],
                "note": "No committed final decision references the assembly candidate.",
            },
        ],
        "unknowns": ["Reference availability is unknown: patch:input_1."],
    }

    rendered = mission_cli._render_why(value)

    assert rendered == (
        "WHY mission_1 app/a.py matched_by=path\n"
        "PLAN v2 sha256:abababababab… approved\n"
        "STAGE target established\n"
        "  node publication pub_1 kind=patch task=task_a attempt=attempt_1 "
        "worker=none attempt_number=none fence=none sha256=abababababab\n"
        "  events event_3,event_4\n"
        "  note Committed publication metadata matches the query.\n"
        "STAGE producer_attempt established\n"
        "  node attempt attempt_1 kind=none task=task_a attempt=attempt_1 "
        "worker=worker-1 attempt_number=2 fence=7 sha256=none\n"
        "  receipt test-receipt receipt_1 resolvable=True\n"
        "  receipt worker-provider-receipt provider_1 resolvable=False\n"
        "  events event_2\n"
        "  note The verified snapshot binds each target to its producer attempt.\n"
        "STAGE accepted_inputs established\n"
        "  node reference input_1 kind=patch task=none attempt=none worker=none "
        "attempt_number=none fence=none sha256=abababababab resolvable=none\n"
        "  events none\n"
        "  note Producer attempts declare these exact accepted inputs.\n"
        "STAGE approval unknown\n"
        "  node event event_9 kind=none task=none attempt=none worker=none "
        "attempt_number=none fence=none sha256=none\n"
        "  events event_9\n"
        "  note No committed final decision references the assembly candidate.\n"
        "UNKNOWN Reference availability is unknown: patch:input_1.\n"
        f"{TRUST_LINE}\n"
    )


def test_causal_query_attempt_nodes_carry_identity_and_attempt_bound_receipts(
    tmp_path,
) -> None:
    """Sandbox-free: the store-level mission proves node population directly."""

    from tests.adversarial.test_final_approval_bundle import (
        _complete_trusted_verification,
    )

    store = SQLiteMissionStore(tmp_path / "mission.sqlite")
    _create(store)
    _complete_ready(store, "mission-1", at=NOW, round_number=1)
    _complete_ready(store, "mission-1", at=NOW + timedelta(seconds=2), round_number=2)
    _complete_trusted_verification(store)
    store.enter_awaiting_result(
        "mission-1", _command("await-why"), recorded_at=NOW + timedelta(seconds=6)
    )
    snapshot = store.snapshot("mission-1")
    assert store.verify("mission-1") == snapshot.head
    events = store.tail("mission-1", 0, snapshot.head.seq)
    attempts = {item.attempt_id: item for item in snapshot.attempts}
    known = {
        (reference.kind, reference.id, reference.sha256)
        for attempt in snapshot.attempts
        for reference in (*attempt.input_publications, *attempt.evidence_refs)
    }

    result = why(
        snapshot,
        events,
        "app/a.py",
        reference_exists=lambda reference: (
            reference.kind,
            reference.id,
            reference.sha256,
        )
        in known,
    )

    producer = result.links[1]
    assert producer.stage == "producer_attempt"
    attempt_nodes = [node for node in producer.nodes if node.node_type == "attempt"]
    assert attempt_nodes
    for node in attempt_nodes:
        attempt = attempts[node.node_id]
        assert node.worker_id == attempt.worker_id
        assert node.fencing_token == attempt.fencing_token
        assert node.attempt_number == attempt.attempt_number
    receipt_nodes = [node for node in producer.nodes if node.node_type == "reference"]
    assert receipt_nodes
    for node in receipt_nodes:
        assert node.kind in RECEIPT_REFERENCE_KINDS
        assert node.resolvable is True
        attempt = attempts[node.attempt_id]
        assert node.task_id == attempt.task_id
        assert (node.kind, node.node_id, node.sha256) in {
            (item.kind, item.id, item.sha256) for item in attempt.evidence_refs
        }
    # Non-attempt nodes never carry attempt identity fields.
    for link in result.links:
        for node in link.nodes:
            if node.node_type != "attempt":
                assert node.worker_id is None
                assert node.fencing_token is None
                assert node.attempt_number is None
    # An unresolvable receipt is reported as an explicit unknown, never guessed.
    blind = why(snapshot, events, "app/a.py", reference_exists=lambda _reference: False)
    assert all(
        node.resolvable is False
        for link in blind.links
        for node in link.nodes
        if node.node_type == "reference"
    )
    assert any("Reference availability is unknown" in item for item in blind.unknowns)


def test_why_names_the_stage_a_prior_attempt_reached(tmp_path) -> None:
    """A prior attempt that ended without a publication says how far it got.

    `state` and `result_code` say an attempt failed; neither says whether the
    model had run or the acceptance check had already passed when it did. The
    stage the runtime recorded is committed into the task-outcome event, and
    `why` reads it from the same validated chain it reads everything else
    from — no new authority, no new store column. The `--json` body is this
    exact model dump, and the human render is `_render_why` over it.
    """
    from graphene.orchestration.mission_models import AttemptResult, TaskKind
    from tests.unit.orchestration.test_store import _register_worker

    store = SQLiteMissionStore(tmp_path / "stage.sqlite")
    _create(store)
    store.refresh_ready("mission-1", _command("ready-stage"), recorded_at=NOW)
    task = next(
        item for item in store.ready_tasks("mission-1") if item.task_id == "work-a"
    )
    _register_worker(store, "worker-stage", capabilities=(TaskKind.WORK,), at=NOW)
    dispatch = store.claim_task(
        "mission-1",
        task.task_id,
        "worker-stage",
        _command("claim-stage"),
        recorded_at=NOW,
        ttl_seconds=30,
    )
    store.complete_attempt(
        "mission-1",
        dispatch.attempt_id,
        dispatch.worker_id,
        dispatch.lease_id,
        dispatch.fencing_token,
        AttemptResult(
            succeeded=False,
            retryable=True,
            result_code="acceptance_check_failed",
            stage="check",
        ),
        _command("complete-stage"),
        recorded_at=NOW + timedelta(seconds=1),
        retry_backoff_seconds=0,
    )
    # The retry publishes app/a.py, which is what makes the failed attempt
    # reachable from `why` at all: the query is rooted at a publication.
    _complete_ready(store, "mission-1", at=NOW + timedelta(seconds=5), round_number=1)
    snapshot = store.snapshot("mission-1")
    assert store.verify("mission-1") == snapshot.head

    result = why(
        snapshot,
        store.tail("mission-1", 0, snapshot.head.seq),
        QUERY_PATH_A,
        reference_exists=lambda _reference: True,
    )

    payload = result.model_dump(mode="json")
    prior = next(link for link in payload["links"] if link["stage"] == "prior_attempts")
    assert prior["status"] == "established"
    attempts = [item for item in prior["nodes"] if item["node_type"] == "attempt"]
    assert [item["node_id"] for item in attempts] == [dispatch.attempt_id]
    assert attempts[0]["result_code"] == "acceptance_check_failed"
    assert attempts[0]["stage_reached"] == "check"
    # The producing attempt succeeded, so it carries no stage.
    producer = next(
        link for link in payload["links"] if link["stage"] == "producer_attempt"
    )
    assert all(
        item["stage_reached"] is None
        for item in producer["nodes"]
        if item["node_type"] == "attempt"
    )
    # The bytes `--json` prints are this dump; the human render names it too.
    rendered = mission_cli._render_why(payload)
    assert f"  node attempt {dispatch.attempt_id} " in rendered
    assert " state=failed result_code=acceptance_check_failed stage=check" in rendered
