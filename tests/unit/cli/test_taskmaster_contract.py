import stat
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

import graphene.cli.mission as mission_cli
import graphene.orchestration.causal_query as causal_query
import graphene.orchestration.final_bundle as final_bundle
from graphene.cli.main import build_parser, main
from graphene.hashing import canonical_json_bytes, canonical_json_sha256, sha256_hex
from graphene.models import TruthKind
from graphene.orchestration.evidence import SQLiteAttemptEvidenceStore
from graphene.orchestration.models import MissionSnapshot, MissionStatus
from tests.unit.orchestration.test_final_bundle import _repository, _snapshot
from tests.unit.orchestration.test_store import _plan, _policy


@pytest.mark.parametrize(
    ("argv", "command"),
    [
        (["plan", "ship it", "--repo", "."], "plan"),
        (["plan", "lint", "mission_1"], "plan"),
        (["plan", "show", "mission_1"], "plan"),
        (["plan", "diff", "mission_1", "1", "2"], "plan"),
        (
            ["cancel", "mission_1", "--confirm", "mission_1"],
            "cancel",
        ),
        (["retry", "mission_1", "--task", "task_1"], "retry"),
        (
            ["request-replan", "mission_1", "--reason", "scope changed"],
            "request-replan",
        ),
        (
            [
                "task",
                "input",
                "mission_1",
                "task_1",
                "--gate",
                "gate_1",
                "--stdin",
            ],
            "task",
        ),
        (["run", "mission_1"], "run"),
        (["status", "mission_1"], "status"),
        (["watch", "mission_1"], "watch"),
        (["why", "app/a.py", "--mission", "mission_1"], "why"),
        (["bundle", "verify", "bundle.json"], "bundle"),
        (
            ["bundle", "create", "mission_1", "--output", "bundle.json"],
            "bundle",
        ),
    ],
)
def test_top_level_taskmaster_contract_parses(argv, command) -> None:
    assert build_parser().parse_args(argv).command == command


@pytest.mark.parametrize(
    "argv",
    [
        ["plan", "ship it", "--repo", "."],
        ["plan", "lint", "mission_1"],
        ["plan", "show", "mission_1"],
        ["plan", "diff", "mission_1", "1", "2"],
        ["cancel", "mission_1", "--confirm", "mission_1"],
        ["retry", "mission_1", "--task", "task_1"],
        ["request-replan", "mission_1", "--reason", "scope changed"],
        [
            "task",
            "input",
            "mission_1",
            "task_1",
            "--gate",
            "gate_1",
            "--stdin",
        ],
        ["run", "mission_1"],
        ["status", "mission_1"],
        ["watch", "mission_1"],
        ["why", "app/a.py", "--mission", "mission_1"],
        ["bundle", "verify", "bundle.json"],
        ["bundle", "create", "mission_1", "--output", "bundle.json"],
    ],
)
def test_top_level_contract_routes_to_mission_handler(
    argv, monkeypatch: pytest.MonkeyPatch
) -> None:
    received = []

    def handle(args, *, json_mode):
        received.append((args.command, json_mode))
        return 7

    monkeypatch.setattr(mission_cli, "handle", handle)

    assert main(argv) == 7
    assert received == [(argv[0], False)]


def test_plan_and_run_aliases_reuse_mission_start_and_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planned = build_parser().parse_args(
        [
            "plan",
            "ship it",
            "--repo",
            ".",
            "--success-criterion",
            "tests pass",
        ]
    )
    monkeypatch.setattr(
        mission_cli,
        "_start",
        lambda args: {
            "driver": args.driver,
            "goal": args.goal,
            "auto_approve": args.auto_approve,
        },
    )

    assert mission_cli._dispatch(planned) == (
        0,
        {"driver": "gemini-adk", "goal": "ship it", "auto_approve": False},
    )

    executed = build_parser().parse_args(["run", "mission_1"])
    monkeypatch.setattr(
        mission_cli,
        "_store_for_mission",
        lambda _mission_id: SimpleNamespace(
            snapshot=lambda _mission_id: SimpleNamespace(
                plan=SimpleNamespace(revision=3)
            )
        ),
    )
    monkeypatch.setattr(
        mission_cli,
        "_mutate",
        lambda args: {
            "mission_id": args.mission_id,
            "action": args.mission_action,
            "revision": args.revision,
        },
    )

    assert mission_cli._dispatch(executed) == (
        0,
        {"mission_id": "mission_1", "action": "approve-plan", "revision": 3},
    )


@pytest.mark.parametrize(
    ("argv", "action"),
    [
        (["cancel", "mission_1", "--confirm", "mission_1"], "cancel"),
        (["retry", "mission_1", "--task", "task_1"], "retry"),
        (
            ["request-replan", "mission_1", "--reason", "scope changed"],
            "request-replan",
        ),
    ],
)
def test_top_level_mutations_reuse_mission_mutator(
    argv: list[str], action: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mission_cli,
        "_mutate",
        lambda args: {
            "mission_id": args.mission_id,
            "mission_action": args.mission_action,
        },
    )

    assert mission_cli._dispatch(build_parser().parse_args(argv)) == (
        0,
        {"mission_id": "mission_1", "mission_action": action},
    )


def test_plan_show_and_diff_reuse_verified_store_plan_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    head = SimpleNamespace()
    diff = {
        "mission_id": "mission_1",
        "previous_plan_revision": 1,
        "plan_revision": 2,
        "diff_sha256": "d" * 64,
    }
    mission = SimpleNamespace(
        mission_id="mission_1",
        base_sha="a" * 40,
        goal="Implement the bounded mission.",
        status=MissionStatus.PROPOSED,
        resource_budget=_policy().resource_budget,
    )
    head = SimpleNamespace(seq=4)
    store = SimpleNamespace(
        snapshot=lambda _mission_id: SimpleNamespace(
            head=head, plan=plan, mission=mission
        ),
        verify=lambda _mission_id: head,
        tail=lambda *_args: (),
        plan_diff=lambda mission_id, previous, current: (
            diff
            if (mission_id, previous, current) == ("mission_1", 1, 2)
            else None
        ),
    )
    monkeypatch.setattr(mission_cli, "_store_for_mission", lambda _mission_id: store)
    monkeypatch.setattr(
        mission_cli,
        "_projection",
        lambda _mission_id: SimpleNamespace(
            snapshot=lambda _identifier: SimpleNamespace(
                tasks=tuple(
                    SimpleNamespace(
                        task_id=task.task_id,
                        state="queued",
                        blocker_reason=None,
                        dependency_ids=task.dependencies,
                    )
                    for task in plan.tasks
                ),
                critical_path_task_ids=("work-a", "assemble", "verify"),
                needs_you=None,
            )
        ),
    )

    shown = mission_cli._dispatch(
        build_parser().parse_args(["plan", "show", "mission_1"])
    )
    compared = mission_cli._dispatch(
        build_parser().parse_args(["plan", "diff", "mission_1", "1", "2"])
    )

    assert shown[0] == 0
    assert shown[1]["plan"] == plan.model_dump(mode="json")
    assert shown[1]["plan_revision"] == plan.revision
    # Nothing has been approved, and the table says so rather than implying it.
    assert shown[1]["approved_revision"] is None
    assert shown[1]["frontier_is_projected"] is True
    assert shown[1]["ready_frontier"] == ["work-a", "work-b"]
    rendered = mission_cli._render_plan_table(shown[1])
    assert "Needs approval: plan v1" in rendered
    assert "Frontier on approval: work-a, work-b" in rendered
    assert "{" not in rendered and "[" not in rendered
    assert compared == (0, diff)

    with pytest.raises(mission_cli.MissionCliError, match="two revisions"):
        mission_cli._dispatch(
            build_parser().parse_args(["plan", "diff", "mission_1", "1"])
        )
    with pytest.raises(mission_cli.MissionCliError, match="revision arguments"):
        mission_cli._dispatch(
            build_parser().parse_args(["plan", "show", "mission_1", "1"])
        )


def test_plan_lint_returns_deterministic_criterion_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    policy = _policy()
    head = SimpleNamespace()
    snapshot = SimpleNamespace(
        head=head,
        mission=SimpleNamespace(creation_source="operator"),
        plan=plan,
    )
    store = SimpleNamespace(
        snapshot=lambda _mission_id: snapshot,
        verify=lambda _mission_id: head,
    )
    monkeypatch.setattr(mission_cli, "_store_for_mission", lambda _mission_id: store)
    monkeypatch.setattr(
        mission_cli,
        "_gemini_source",
        lambda _mission_id, _snapshot: (Path.cwd(), policy, 2),
    )

    value = mission_cli._plan_lint_value("mission_1")

    assert value["valid"] is True
    assert value["issues"] == []
    assert value["criterion_coverage"] == [
        {
            "criterion_id": item.criterion_id,
            "producer_task_ids": list(item.producer_task_ids),
            "verification_kind": item.verification_kind.value,
            "verifier_task_id": item.verifier_task_id,
            "verifier_id": item.verifier_id,
        }
        for item in plan.criteria
    ]
    rendered = mission_cli._render_plan_lint(value)
    assert "PLAN mission_1 VALID revision=1" in rendered
    assert "CRITERION" in rendered and "producers=" in rendered

    lint = build_parser().parse_args(["plan", "lint", "mission_1"])
    monkeypatch.setattr(
        mission_cli,
        "_plan_lint_value",
        lambda _mission_id: {"valid": False, "issues": [{"code": "invalid"}]},
    )
    assert mission_cli._dispatch(lint) == (
        1,
        {"valid": False, "issues": [{"code": "invalid"}]},
    )

    ambiguous = build_parser().parse_args(
        ["plan", "lint", "mission_1", "--repo", "."]
    )
    with pytest.raises(mission_cli.MissionCliError, match="does not accept"):
        mission_cli._dispatch(ambiguous)
    with pytest.raises(mission_cli.MissionCliError, match="requires a mission ID"):
        mission_cli._dispatch(build_parser().parse_args(["plan", "lint"]))


def test_why_alias_uses_verified_mission_causal_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head = SimpleNamespace(event_count=1)
    snapshot = SimpleNamespace(head=head)
    event = SimpleNamespace(seq=1)
    store = SimpleNamespace(
        artifact_resolver=SimpleNamespace(resolve=lambda _kind, _identifier: b"proof"),
        snapshot=lambda _mission_id: snapshot,
        verify=lambda _mission_id: head,
        tail=lambda _mission_id, _after, _limit: (event,),
    )
    monkeypatch.setattr(mission_cli, "_store_for_mission", lambda _mission_id: store)

    def fake_why(received_snapshot, events, query, *, reference_exists):
        assert received_snapshot is snapshot
        assert events == (event,)
        assert query == "app/a.py"
        assert reference_exists(
            SimpleNamespace(
                kind="patch", id="artifact_1", sha256=sha256_hex(b"proof")
            )
        )
        return SimpleNamespace(
            model_dump=lambda **_options: {
                "mission_id": "mission_1",
                "query": query,
                "matched_by": "path",
                "links": [],
                "unknowns": [],
            }
        )

    monkeypatch.setattr(causal_query, "why", fake_why)
    args = build_parser().parse_args(
        ["why", "app/a.py", "--mission", "mission_1"]
    )

    assert mission_cli._why_value(args)["matched_by"] == "path"


def test_bundle_create_is_canonical_create_only_and_verifiable_by_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    missions = state / "missions"
    runtime = missions / "runtime-one"
    state.mkdir(mode=0o700)
    missions.mkdir(mode=0o700)
    runtime.mkdir(mode=0o700)
    repository = runtime / "repository"
    base, result_commit = _repository(repository, b"base one\n")
    snapshot, artifacts, policy_sha256 = _snapshot(
        repository, base, result_commit
    )
    values = snapshot.model_dump(mode="json", exclude={"snapshot_sha256"})
    values["mission"] = {
        **values["mission"],
        "final_outcome": None,
        "status": MissionStatus.AWAITING_RESULT.value,
    }
    snapshot = MissionSnapshot.model_validate(
        {**values, "snapshot_sha256": canonical_json_sha256(values)}
    )
    bundle = final_bundle.build_final_result_bundle(
        snapshot,
        artifacts,
        repository,
        result_commit=None,
        policy_sha256=policy_sha256,
    )
    prepared_raw = canonical_json_bytes(bundle.model_dump(mode="json"))
    store = SimpleNamespace(
        artifact_resolver=artifacts,
        snapshot=lambda _mission_id: snapshot,
        verify=lambda _mission_id: snapshot.head,
    )

    def prepare(_mission_id: str):
        directory = mission_cli._bundle_directory(runtime, create=True)
        persisted = directory / f"{bundle.bundle_id}.json"
        if not persisted.exists():
            mission_cli._atomic_create(persisted, prepared_raw)
        return prepared_raw, bundle, runtime

    monkeypatch.setattr(mission_cli, "_prepare_pending_bundle", prepare)
    monkeypatch.setattr(mission_cli, "_store_for_mission", lambda _mission_id: store)
    monkeypatch.setattr(mission_cli, "_mission_runtime", lambda _mission_id: runtime)
    monkeypatch.setattr(mission_cli, "_state_root", lambda: state)
    output = tmp_path / "review-bundle.json"

    created = mission_cli._bundle_create_value(
        build_parser().parse_args(
            ["bundle", "create", "mission-1", "--output", str(output)]
        )
    )

    raw = output.read_bytes()
    bundle = final_bundle.FinalResultBundleV2.model_validate_json(raw)
    persisted = runtime / "final-bundles" / f"{bundle.bundle_id}.json"
    assert raw == canonical_json_bytes(bundle.model_dump(mode="json"))
    assert persisted.read_bytes() == raw
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert created["bundle_id"] == bundle.bundle_id
    assert created["bundle_sha256"] == bundle.bundle_sha256
    assert created["approval_binding"] == "bundle_id"

    explicit = mission_cli._bundle_verify_value(
        build_parser().parse_args(["bundle", "verify", str(output)])
    )
    by_id = mission_cli._bundle_verify_value(
        build_parser().parse_args(["bundle", "verify", bundle.bundle_id])
    )
    assert explicit["source"] == "explicit_bundle_file"
    assert by_id["source"] == "persisted_bundle_id"
    assert not tuple(tmp_path.glob(".*.tmp"))

    symlink = tmp_path / "bundle-link.json"
    symlink.symlink_to(output)
    with pytest.raises(mission_cli.MissionCliError, match="non-symlink"):
        mission_cli._bundle_create_value(
            build_parser().parse_args(
                [
                    "bundle",
                    "create",
                    "mission-1",
                    "--output",
                    str(symlink),
                ]
            )
        )

    with pytest.raises(mission_cli.MissionCliError, match="new non-symlink"):
        mission_cli._bundle_create_value(
            build_parser().parse_args(
                [
                    "bundle",
                    "create",
                    "mission-1",
                    "--output",
                    str(output),
                ]
            )
        )


def test_bundle_verify_rejects_invalid_files_and_verifier_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    malformed = tmp_path / "bundle.json"
    malformed.write_bytes(b"{}")
    args = build_parser().parse_args(["bundle", "verify", str(malformed)])
    with pytest.raises(mission_cli.MissionCliError, match="unavailable or invalid"):
        mission_cli._bundle_verify_value(args)

    bundle = SimpleNamespace(
        mission_id="mission_1", bundle_id="final_result_1", bundle_sha256="a" * 64
    )
    head = SimpleNamespace()
    snapshot = SimpleNamespace(
        head=head, policy=SimpleNamespace(policy_sha256="b" * 64)
    )
    store = SimpleNamespace(
        artifact_resolver=SimpleNamespace(resolve=lambda _kind, _identifier: None),
        snapshot=lambda _mission_id: snapshot,
        verify=lambda _mission_id: head,
    )
    monkeypatch.setattr(
        final_bundle.FinalResultBundleV2,
        "model_validate_json",
        classmethod(lambda _cls, _raw: bundle),
    )
    monkeypatch.setattr(
        final_bundle, "verify_final_result_bundle", lambda *_a, **_k: False
    )
    monkeypatch.setattr(mission_cli, "_store_for_mission", lambda _mission_id: store)
    monkeypatch.setattr(mission_cli, "_mission_runtime", lambda _mission_id: tmp_path)
    with pytest.raises(mission_cli.MissionCliError, match="failed closed"):
        mission_cli._bundle_verify_value(args)


def test_task_input_reads_private_bounded_file_without_echoing_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = b"private operator guidance\n"
    source = tmp_path / "input.txt"
    source.write_bytes(secret)
    head = SimpleNamespace(
        model_dump=lambda **_options: {"seq": 1, "event_sha256": "h" * 64}
    )
    reference = SimpleNamespace(
        sha256=sha256_hex(secret),
        model_dump=lambda **_options: {
            "kind": "operator-input",
            "id": "artifact_private",
            "sha256": sha256_hex(secret),
        },
    )
    captured: dict[str, object] = {}

    class Evidence:
        def put_artifact(self, kind: str, content: bytes):
            captured["artifact"] = (kind, content)
            return reference

    class Store:
        def snapshot(self, mission_id: str):
            assert mission_id == "mission_1"
            return SimpleNamespace(head=head)

        def verify(self, mission_id: str):
            return head

        def head(self, mission_id: str):
            return head

        def supply_task_input(self, *args, **kwargs):
            captured["call"] = (args, kwargs)
            return head

    store = Store()
    monkeypatch.setattr(mission_cli, "_store_for_mission", lambda _mission_id: store)
    monkeypatch.setattr(
        mission_cli, "_mission_evidence", lambda _store, _mission_id: Evidence()
    )
    args = build_parser().parse_args(
        [
            "task",
            "input",
            "mission_1",
            "task_1",
            "--gate",
            "gate_1",
            "--file",
            str(source),
        ]
    )

    value = mission_cli._task_input_value(args)

    assert captured["artifact"] == ("operator-input", secret)
    call_args, call_kwargs = captured["call"]
    assert call_args[:4] == ("mission_1", "task_1", "gate_1", reference)
    assert call_kwargs["expected_head"] is head
    assert call_kwargs["truth_kind"] == TruthKind.SERVER_DERIVED
    assert secret not in canonical_json_bytes(value)
    assert value["input_reference"]["id"] == "artifact_private"

    oversized = tmp_path / "large.txt"
    oversized.write_bytes(b"x" * 4_097)
    with pytest.raises(mission_cli.MissionCliError, match="1 to 4096"):
        mission_cli._task_input_bytes(
            build_parser().parse_args(
                [
                    "task",
                    "input",
                    "mission_1",
                    "task_1",
                    "--gate",
                    "gate_1",
                    "--file",
                    str(oversized),
                ]
            )
        )

    link = tmp_path / "input-link.txt"
    link.symlink_to(source)
    with pytest.raises(mission_cli.MissionCliError, match="non-symlink"):
        mission_cli._task_input_bytes(
            build_parser().parse_args(
                [
                    "task",
                    "input",
                    "mission_1",
                    "task_1",
                    "--gate",
                    "gate_1",
                    "--file",
                    str(link),
                ]
            )
        )


def test_task_input_accepts_bounded_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = b"stdin guidance"
    monkeypatch.setattr(
        mission_cli.sys,
        "stdin",
        SimpleNamespace(buffer=BytesIO(secret), isatty=lambda: False),
    )
    args = build_parser().parse_args(
        [
            "task",
            "input",
            "mission_1",
            "task_1",
            "--gate",
            "gate_1",
            "--stdin",
        ]
    )

    assert mission_cli._task_input_bytes(args) == secret


def test_mission_evidence_reuses_only_the_bound_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    expected = SQLiteAttemptEvidenceStore(runtime / "attempt-evidence.sqlite3")
    store = SimpleNamespace(artifact_resolver=expected)
    monkeypatch.setattr(mission_cli, "_mission_runtime", lambda _mission_id: runtime)

    assert mission_cli._mission_evidence(store, "mission_1") is expected

    other = SQLiteAttemptEvidenceStore(tmp_path / "other.sqlite3")
    with pytest.raises(mission_cli.MissionCliError, match="another path"):
        mission_cli._mission_evidence(
            SimpleNamespace(artifact_resolver=other), "mission_1"
        )


def test_confirm_human_binds_authoritative_local_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pwd

    looked_up = []
    monkeypatch.setattr(mission_cli.os, "getuid", lambda: 501)
    monkeypatch.setattr(
        pwd,
        "getpwuid",
        lambda uid: looked_up.append(uid) or SimpleNamespace(pw_name="os-user"),
    )
    monkeypatch.setattr(
        mission_cli.sys, "stdin", SimpleNamespace(isatty=lambda: True)
    )
    monkeypatch.setattr(
        mission_cli.sys, "stdout", SimpleNamespace(isatty=lambda: True)
    )
    args = SimpleNamespace(confirm_human=True, operator_label="reviewer")

    assert mission_cli._truth_kind(args) == TruthKind.HUMAN_ATTESTED
    assert looked_up == [501]
    assert args.operator_label.startswith("reviewer@local-")
    assert len(args.operator_label) <= 64


class _Head:
    seq = 4

    def model_dump(self, mode: str = "json") -> dict[str, object]:
        return {"seq": self.seq}


class _MissionStub:
    mission_id = "mission_1"
    creation_source = "api"
    status = MissionStatus.PROPOSED
    base_sha = "a" * 40

    def model_dump(self, mode: str = "json") -> dict[str, object]:
        return {"mission_id": self.mission_id, "status": str(self.status)}


def _mission_stub() -> _MissionStub:
    return _MissionStub()


def test_plan_approval_binds_the_digest_the_operator_was_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Approving a revision number is not approving a graph.

    The CLI always hands the store the digest of the plan it just read, and
    refuses outright when the operator names a different one — so a plan that
    moved between reading the diff and typing the approval cannot be approved
    by accident.
    """
    plan = _plan()
    digest = canonical_json_sha256(plan.model_dump(mode="json"))
    head = _Head()
    snapshot = SimpleNamespace(
        head=head,
        plan=plan,
        # `creation_source` is neither "scripted_fixture" nor "operator", so
        # the branch under test is the plain store approval, not an execution.
        mission=_mission_stub(),
    )
    calls: list[dict[str, object]] = []

    def approve_plan(mission_id, command_id, **kwargs):
        calls.append(kwargs)
        return head

    store = SimpleNamespace(
        snapshot=lambda _mission_id: snapshot,
        head=lambda _mission_id: head,
        approve_plan=approve_plan,
    )
    monkeypatch.setattr(mission_cli, "_store_for_mission", lambda _mission_id: store)
    monkeypatch.setattr(mission_cli, "_store", lambda *args, **kwargs: store)

    args = build_parser().parse_args(
        ["plan", "approve", "mission_1", "--revision", "1", "--operator-label", "alex"]
    )
    mission_cli._dispatch(args)
    assert calls[-1]["expected_plan_sha256"] == digest

    wrong = build_parser().parse_args(
        [
            "plan",
            "approve",
            "mission_1",
            "--revision",
            "1",
            "--plan-sha256",
            "0" * 64,
            "--operator-label",
            "alex",
        ]
    )
    with pytest.raises(mission_cli.MissionCliError, match="digest does not match"):
        mission_cli._dispatch(wrong)

    named = build_parser().parse_args(
        [
            "plan",
            "approve",
            "mission_1",
            "--revision",
            "1",
            "--plan-sha256",
            digest,
            "--operator-label",
            "alex",
        ]
    )
    mission_cli._dispatch(named)
    assert calls[-1]["expected_plan_sha256"] == digest

    # The flag belongs to approval alone.
    with pytest.raises(mission_cli.MissionCliError, match="does not accept"):
        mission_cli._dispatch(
            build_parser().parse_args(
                ["plan", "show", "mission_1", "--plan-sha256", digest]
            )
        )
