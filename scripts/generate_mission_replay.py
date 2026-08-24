from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from graphene.hashing import canonical_json_bytes, sha256_hex
from graphene.orchestration.projection import (
    AttemptEvidenceView,
    AttemptView,
    EvidenceRefView,
    GateOptionView,
    GateView,
    MissionControlSnapshot,
    MissionHeadView,
    MissionView,
    PublicationView,
    RelationshipView,
    ResourceMetricView,
    ResourceSummaryView,
    ResultView,
    StageView,
    TaskView,
    WorkerView,
    diff_snapshots,
    encode_cursor,
)
from graphene.orchestration.replay import MISSION_REPLAY_TRUTH_LABEL

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "backend/graphene/orchestration/static/mission-replay.json"
MISSION_ID = "mission_status_reports"


def digest(value: str) -> str:
    return sha256_hex(value.encode())


def ref(kind: str, identity: str) -> EvidenceRefView:
    return EvidenceRefView(kind=kind, id=identity, sha256=digest(f"{kind}:{identity}"))


def task(
    task_id: str,
    title: str,
    state: str,
    *,
    dependencies: tuple[str, ...] = (),
    kind: str = "work",
    blocker: str | None = None,
    priority: int = 50,
    worker_id: str | None = None,
    attempt_id: str | None = None,
) -> TaskView:
    contract = {
        "redact_notes": (
            "Redact private note text by default and pass check_redact_notes."
        ),
        "render_json": (
            "Produce the scoped JSON status renderer and pass check_render_json."
        ),
        "render_markdown": (
            "Produce the scoped Markdown status renderer and pass check_render_markdown."
        ),
        "wire_cli": (
            "Consume only accepted renderer artifacts, wire both formats into the CLI, "
            "and pass check_wire_cli."
        ),
        "assemble": (
            "Assemble only accepted task publications into the isolated candidate and "
            "pass check_assemble."
        ),
        "verify": (
            "Verify the exact assembled candidate with the bound check_verify receipt."
        ),
    }[task_id]
    write_scope = {
        "redact_notes": ("src/status_report/redaction.py", "tests/test_redaction.py"),
        "render_json": (
            "src/status_report/json_report.py",
            "tests/test_json_report.py",
        ),
        "render_markdown": (
            "src/status_report/markdown_report.py",
            "tests/test_markdown_report.py",
        ),
        "wire_cli": ("src/status_report/cli.py", "tests/test_cli.py"),
        "assemble": (),
        "verify": (),
    }[task_id]
    return TaskView(
        task_id=task_id,
        title=title,
        contract=contract,
        state=state,
        kind=kind,
        priority=priority,
        assigned_role="integration-verifier" if kind != "work" else "repository-worker",
        dependency_ids=dependencies,
        worker_id=worker_id,
        current_attempt_id=attempt_id,
        blocker_reason=blocker,
        read_scope=("src/status_report/**", "tests/**"),
        write_scope=tuple(sorted(write_scope)),
        allowed_command_templates=("python_test_target",),
        acceptance_checks=(f"check_{task_id}",),
    )


def attempt(
    attempt_id: str,
    task_id: str,
    worker_id: str,
    number: int,
    status: str,
    *references: EvidenceRefView,
    result_code: str | None = None,
) -> AttemptView:
    return AttemptView(
        attempt_id=attempt_id,
        task_id=task_id,
        worker_id=worker_id,
        number=number,
        status=status,
        workspace_id=f"workspace_{attempt_id}",
        lease_id=f"lease_{attempt_id}",
        fencing_token=number,
        result_code=result_code,
        evidence=AttemptEvidenceView(
            kind="generic_attempt_v1", evidence_id=f"evidence_{attempt_id}"
        ),
        evidence_refs=tuple(references),
    )


def workers(attempts: tuple[AttemptView, ...]) -> tuple[WorkerView, ...]:
    latest: dict[str, AttemptView] = {}
    for item in attempts:
        if item.worker_id not in latest or item.number >= latest[item.worker_id].number:
            latest[item.worker_id] = item
    return tuple(
        WorkerView(
            worker_id=worker_id,
            label=worker_id.replace("_", " ").title(),
            role="integration-verifier"
            if item.task_id in {"assemble", "verify"}
            else "repository-worker",
            status=item.status,
            task_id=item.task_id,
            attempt_id=item.attempt_id,
            fencing_token=item.fencing_token,
        )
        for worker_id, item in sorted(latest.items())
    )


def relationships(
    tasks: tuple[TaskView, ...],
    worker_values: tuple[WorkerView, ...],
    gates: tuple[GateView, ...],
    publications: tuple[PublicationView, ...],
) -> tuple[RelationshipView, ...]:
    values: dict[str, RelationshipView] = {}

    def add(source: str, target: str, kind: str) -> None:
        identity = f"{kind}:{source}:{target}"
        values[identity] = RelationshipView(
            relationship_id=identity, source=source, target=target, kind=kind
        )

    for item in tasks:
        add(f"mission:{MISSION_ID}", f"task:{item.task_id}", "decomposed_into")
        for dependency in item.dependency_ids:
            add(f"task:{item.task_id}", f"task:{dependency}", "depends_on")
    for item in worker_values:
        add(f"task:{item.task_id}", f"worker:{item.worker_id}", "assigned_to")
    for item in gates:
        if item.status != "pending":
            continue
        if item.task_id:
            add(f"task:{item.task_id}", f"gate:{item.gate_id}", "blocked_by")
        elif item.gate_id.startswith("final_result_"):
            add(f"result:{MISSION_ID}", f"gate:{item.gate_id}", "blocked_by")
    work_task_ids = {item.task_id for item in tasks if item.kind == "work"}
    for item in publications:
        if item.state == "accepted" and item.task_id in work_task_ids:
            add(f"integration:{MISSION_ID}", f"task:{item.task_id}", "accepted_from")
        if item.state == "accepted":
            for consumer in item.consumers:
                add(f"task:{consumer}", f"task:{item.task_id}", "inherited")
    add("task:assemble", f"integration:{MISSION_ID}", "produced")
    add(f"integration:{MISSION_ID}", f"verification:{MISSION_ID}", "verified_by")
    add("task:verify", f"verification:{MISSION_ID}", "produced")
    add(f"verification:{MISSION_ID}", f"result:{MISSION_ID}", "produced")
    return tuple(values[key] for key in sorted(values))


def publication(task_id: str, consumers: tuple[str, ...]) -> PublicationView:
    return PublicationView(
        publication_id=f"publication_{task_id}",
        task_id=task_id,
        attempt_id=f"attempt_{task_id}_2"
        if task_id == "render_markdown"
        else f"attempt_{task_id}_1",
        output_name=f"{task_id}_patch",
        kind="patch",
        state="accepted",
        sha256=digest(f"publication:{task_id}"),
        paths=(f"fixture/{task_id}.patch",),
        consumers=consumers,
    )


PRIVACY_GATE = GateView(
    gate_id="gate_privacy_default",
    task_id="redact_notes",
    reason="Should generated status reports redact note text by default?",
    status="pending",
    evidence_summary="Raw notes may contain private operator context.",
    options=(
        GateOptionView(
            value="redact_default",
            label="Redact by default",
            consequence="Reports expose structure and counts while masking note text.",
        ),
        GateOptionView(
            value="raw_notes",
            label="Include raw notes",
            consequence="Reports may disclose private note content and require a broader policy.",
        ),
    ),
    truth_kind="simulated_fixture",
)

FINAL_RESULT_GATE = GateView(
    gate_id="final_result_recorded_fixture",
    reason="Review the exact verified candidate before the recorded fixture decision.",
    status="pending",
    evidence_summary=(
        "The candidate and verification receipts are committed fixture evidence. "
        "Replay remains read-only and human_attestation=false."
    ),
    options=(
        GateOptionView(
            value="continue_recorded_simulated_approval",
            label="Continue with recorded simulated approval",
            consequence=(
                "Continue to the fixture's recorded isolated-commit checkpoint; this "
                "does not attest a human decision or execute Git."
            ),
        ),
    ),
    truth_kind="simulated_fixture",
)


def snapshot(
    seq: int,
    task_values: tuple[TaskView, ...],
    attempt_values: tuple[AttemptView, ...],
    *,
    gate: GateView = PRIVACY_GATE,
    extra_gates: tuple[GateView, ...] = (),
    needs_you: GateView | None = None,
    publications: tuple[PublicationView, ...] = (),
    integration: StageView | None = None,
    verification: StageView | None = None,
    resources: ResourceSummaryView | None = None,
    result: ResultView | None = None,
    mission_status: str = "running",
    critical_path: tuple[str, ...] = (),
    unknowns: tuple[str, ...] = (),
) -> MissionControlSnapshot:
    head_digest = digest(f"mission-head:{seq}")
    mission = MissionView(
        mission_id=MISSION_ID,
        goal="Add redacted JSON and Markdown status reports to the fixture CLI.",
        success_criteria=(
            "Both report formats pass their bound checks.",
            "Private note text is redacted by default.",
            "The assembled candidate passes full verification.",
        ),
        status=mission_status,
        plan_revision=1,
        # The fixture is a mission that was approved at revision 1, so the
        # replay says so rather than leaving the reader to assume it.
        plan_sha256=digest("mission-plan:1"),
        approved_plan_revision=1,
        outcome="Verified isolated result available."
        if mission_status == "completed"
        else None,
        creation_source="scripted_fixture",
    )
    head = MissionHeadView(mission_id=MISSION_ID, seq=seq, event_sha256=head_digest)
    worker_values = workers(attempt_values)
    gates = tuple(sorted((gate, *extra_gates), key=lambda item: item.gate_id))
    values: dict[str, Any] = {
        "view_version": 1,
        "mission": mission,
        "head": head,
        "cursor": encode_cursor(MISSION_ID, seq, head_digest),
        "tasks": tuple(sorted(task_values, key=lambda item: item.task_id)),
        "attempts": tuple(sorted(attempt_values, key=lambda item: item.attempt_id)),
        "workers": worker_values,
        "gates": gates,
        "publications": tuple(
            sorted(publications, key=lambda item: item.publication_id)
        ),
        "relationships": relationships(task_values, worker_values, gates, publications),
        "integration": integration
        or StageView(state="queued", summary="Integration has not started."),
        "verification": verification
        or StageView(state="queued", summary="Verification has not started."),
        "resources": resources
        or ResourceSummaryView(
            status="unavailable",
            summary="No authoritative resource receipt is available at this checkpoint.",
        ),
        "needs_you": needs_you,
        "critical_path_task_ids": critical_path,
        "result": result
        or ResultView(state="pending", summary="No final result is available."),
        "unknowns": unknowns,
    }
    provisional = MissionControlSnapshot.model_construct(
        **values, snapshot_sha256="0" * 64
    )
    digest_value = digest(
        canonical_json_bytes(
            provisional.model_dump(mode="json", exclude={"cursor", "snapshot_sha256"})
        ).decode()
    )
    return MissionControlSnapshot(**values, snapshot_sha256=digest_value)


def stages() -> tuple[MissionControlSnapshot, ...]:
    base = {
        "redact_notes": ("Redact private notes", (), "work", 90),
        "render_json": ("Render JSON status", (), "work", 80),
        "render_markdown": ("Render Markdown status", (), "work", 80),
        "wire_cli": (
            "Wire both formats into the CLI",
            ("redact_notes", "render_json", "render_markdown"),
            "work",
            60,
        ),
        "assemble": ("Assemble accepted patches", ("wire_cli",), "assembly", 40),
        "verify": ("Verify assembled candidate", ("assemble",), "verification", 20),
    }

    def tasks(
        states: dict[str, str],
        owners: dict[str, tuple[str, str]] = {},
        blockers: dict[str, str] = (),
    ):
        return tuple(
            task(
                task_id,
                title,
                states.get(task_id, "queued"),
                dependencies=dependencies,
                kind=kind,
                priority=priority,
                blocker=(blockers or {}).get(task_id),
                worker_id=owners.get(task_id, (None, None))[0],
                attempt_id=owners.get(task_id, (None, None))[1],
            )
            for task_id, (title, dependencies, kind, priority) in base.items()
        )

    gate_decided = PRIVACY_GATE.model_copy(
        update={"status": "decided", "resolution": "redact_default"}
    )
    pressure = ResourceSummaryView(
        status="pressure",
        summary="Two of two worker slots are occupied; ready work remains queued.",
        metrics=(
            ResourceMetricView(
                label="Managed worker slots",
                display_value="2 / 2",
                category="measured_runtime",
                attribution_quality="measured_bound",
            ),
            ResourceMetricView(
                label="Approved context",
                display_value="estimated 5.2k tokens",
                category="estimated_context",
                attribution_quality="sampled_partial",
            ),
            ResourceMetricView(
                label="Remote provider CPU/RAM",
                display_value="unavailable",
                category="provider",
                attribution_quality="unavailable",
            ),
        ),
    )
    empty = ()
    s1 = snapshot(
        1,
        tasks(
            {
                "redact_notes": "needs_input",
                "render_json": "ready",
                "render_markdown": "ready",
            }
        ),
        empty,
        needs_you=PRIVACY_GATE,
        critical_path=("redact_notes", "wire_cli", "assemble", "verify"),
        unknowns=("No live Gemini or Cloud execution is established by this replay.",),
    )
    a_json = attempt(
        "attempt_render_json_1", "render_json", "worker_json", 1, "running"
    )
    a_markdown = attempt(
        "attempt_render_markdown_1", "render_markdown", "worker_markdown", 1, "running"
    )
    s2 = snapshot(
        2,
        tasks(
            {
                "redact_notes": "ready",
                "render_json": "running",
                "render_markdown": "running",
            },
            {
                "render_json": ("worker_json", a_json.attempt_id),
                "render_markdown": ("worker_markdown", a_markdown.attempt_id),
            },
        ),
        (a_json, a_markdown),
        gate=gate_decided,
        resources=pressure,
        critical_path=("render_markdown", "wire_cli", "assemble", "verify"),
    )
    denial = ref("command_denial", "interpreter_template_not_allowlisted")
    a_markdown_denied = a_markdown.model_copy(update={"evidence_refs": (denial,)})
    s3 = snapshot(
        3,
        tasks(
            {
                "redact_notes": "ready",
                "render_json": "running",
                "render_markdown": "blocked",
            },
            {
                "render_json": ("worker_json", a_json.attempt_id),
                "render_markdown": ("worker_markdown", a_markdown.attempt_id),
            },
            {
                "render_markdown": "Denied non-allowlisted interpreter template before execution."
            },
        ),
        (a_json, a_markdown_denied),
        gate=gate_decided,
        resources=pressure,
        critical_path=("render_markdown", "wire_cli", "assemble", "verify"),
    )
    failed_check = ref("test_check", "markdown_acceptance_failed")
    json_refs = (
        ref("changed_path", "json_renderer"),
        ref("test_check", "json_acceptance_passed"),
    )
    a_json_done = a_json.model_copy(
        update={
            "status": "committed",
            "result_code": "passed",
            "evidence_refs": json_refs,
        }
    )
    a_markdown_failed = a_markdown.model_copy(
        update={
            "status": "failed",
            "result_code": "check_failed",
            "evidence_refs": (denial, failed_check),
        }
    )
    a_redact = attempt(
        "attempt_redact_notes_1", "redact_notes", "worker_redact", 1, "running"
    )
    p_json = publication("render_json", ("wire_cli",))
    s4 = snapshot(
        4,
        tasks(
            {
                "redact_notes": "running",
                "render_json": "done",
                "render_markdown": "retrying",
            },
            {
                "redact_notes": ("worker_redact", a_redact.attempt_id),
                "render_json": ("worker_json", a_json.attempt_id),
                "render_markdown": ("worker_markdown", a_markdown.attempt_id),
            },
        ),
        (a_json_done, a_markdown_failed, a_redact),
        gate=gate_decided,
        publications=(p_json,),
        critical_path=("render_markdown", "wire_cli", "assemble", "verify"),
    )
    a_markdown_2 = attempt(
        "attempt_render_markdown_2",
        "render_markdown",
        "worker_markdown_retry",
        2,
        "running",
    )
    s5 = snapshot(
        5,
        tasks(
            {
                "redact_notes": "running",
                "render_json": "done",
                "render_markdown": "running",
            },
            {
                "redact_notes": ("worker_redact", a_redact.attempt_id),
                "render_json": ("worker_json", a_json.attempt_id),
                "render_markdown": ("worker_markdown_retry", a_markdown_2.attempt_id),
            },
        ),
        (a_json_done, a_markdown_failed, a_markdown_2, a_redact),
        gate=gate_decided,
        publications=(p_json,),
        resources=pressure,
        critical_path=("render_markdown", "wire_cli", "assemble", "verify"),
    )
    a_redact_done = a_redact.model_copy(
        update={
            "status": "committed",
            "result_code": "passed",
            "evidence_refs": (
                ref("changed_path", "redaction_module"),
                ref("test_check", "redaction_acceptance_passed"),
            ),
        }
    )
    a_markdown_done = a_markdown_2.model_copy(
        update={
            "status": "committed",
            "result_code": "passed_after_retry",
            "evidence_refs": (
                ref("changed_hunk", "markdown_retry_fix"),
                ref("test_check", "markdown_acceptance_passed"),
            ),
        }
    )
    p_redact = publication("redact_notes", ("wire_cli",))
    p_markdown = publication("render_markdown", ("wire_cli",))
    s6 = snapshot(
        6,
        tasks(
            {
                "redact_notes": "done",
                "render_json": "done",
                "render_markdown": "done",
                "wire_cli": "ready",
            }
        ),
        (a_json_done, a_markdown_failed, a_markdown_done, a_redact_done),
        gate=gate_decided,
        publications=(p_json, p_markdown, p_redact),
        critical_path=("wire_cli", "assemble", "verify"),
    )
    a_wire = attempt(
        "attempt_wire_cli_1",
        "wire_cli",
        "worker_cli",
        1,
        "running",
        ref("inherited_evidence", "accepted_dependency_patches"),
    )
    s7 = snapshot(
        7,
        tasks(
            {
                "redact_notes": "done",
                "render_json": "done",
                "render_markdown": "done",
                "wire_cli": "running",
            },
            {"wire_cli": ("worker_cli", a_wire.attempt_id)},
        ),
        (a_json_done, a_markdown_failed, a_markdown_done, a_redact_done, a_wire),
        gate=gate_decided,
        publications=(p_json, p_markdown, p_redact),
        critical_path=("wire_cli", "assemble", "verify"),
    )
    a_wire_done = a_wire.model_copy(
        update={
            "status": "committed",
            "result_code": "passed",
            "evidence_refs": (
                *a_wire.evidence_refs,
                ref("test_check", "cli_acceptance_passed"),
            ),
        }
    )
    p_wire = publication("wire_cli", ("assemble",))
    a_assemble = attempt(
        "attempt_assemble_1", "assemble", "worker_integrator", 1, "running"
    )
    s8 = snapshot(
        8,
        tasks(
            {
                "redact_notes": "done",
                "render_json": "done",
                "render_markdown": "done",
                "wire_cli": "done",
                "assemble": "running",
            },
            {"assemble": ("worker_integrator", a_assemble.attempt_id)},
        ),
        (
            a_json_done,
            a_markdown_failed,
            a_markdown_done,
            a_redact_done,
            a_wire_done,
            a_assemble,
        ),
        gate=gate_decided,
        publications=(p_json, p_markdown, p_redact, p_wire),
        integration=StageView(
            state="running",
            summary="Applying four accepted patches in the isolated integration workspace.",
            task_id="assemble",
            attempt_id=a_assemble.attempt_id,
        ),
        critical_path=("assemble", "verify"),
    )
    a_assemble_done = a_assemble.model_copy(
        update={
            "status": "committed",
            "result_code": "assembled",
            "evidence_refs": (ref("candidate_tree", "assembled_candidate"),),
        }
    )
    a_verify = attempt("attempt_verify_1", "verify", "worker_verifier", 1, "running")
    s9 = snapshot(
        9,
        tasks(
            {
                "redact_notes": "done",
                "render_json": "done",
                "render_markdown": "done",
                "wire_cli": "done",
                "assemble": "done",
                "verify": "verifying",
            },
            {"verify": ("worker_verifier", a_verify.attempt_id)},
        ),
        (
            a_json_done,
            a_markdown_failed,
            a_markdown_done,
            a_redact_done,
            a_wire_done,
            a_assemble_done,
            a_verify,
        ),
        gate=gate_decided,
        publications=(p_json, p_markdown, p_redact, p_wire),
        integration=StageView(
            state="done",
            summary="Accepted patches assembled without conflict.",
            task_id="assemble",
            attempt_id=a_assemble.attempt_id,
            evidence_refs=a_assemble_done.evidence_refs,
        ),
        verification=StageView(
            state="running",
            summary="Running the bound full verification against the assembled candidate.",
            task_id="verify",
            attempt_id=a_verify.attempt_id,
        ),
        critical_path=("verify",),
    )
    candidate_ref = ref("candidate_tree", "assembled_candidate")
    verification_ref = ref("test_check", "fixture_full_verification_passed")
    commit_ref = ref("simulated_isolated_commit", "fixture_result_commit_anchor")
    verify_refs = (verification_ref, candidate_ref)
    a_verify_done = a_verify.model_copy(
        update={
            "status": "committed",
            "result_code": "passed",
            "evidence_refs": verify_refs,
        }
    )
    healthy_resources = ResourceSummaryView(
        status="healthy",
        summary="Managed scripted workers completed within the fixture budget.",
        metrics=(
            ResourceMetricView(
                label="Managed worker slots",
                display_value="0 / 2 active",
                category="measured_runtime",
                attribution_quality="measured_bound",
            ),
            ResourceMetricView(
                label="Remote provider CPU/RAM",
                display_value="unavailable",
                category="provider",
                attribution_quality="unavailable",
            ),
        ),
    )
    s10 = snapshot(
        10,
        tasks({key: "done" for key in base}),
        (
            a_json_done,
            a_markdown_failed,
            a_markdown_done,
            a_redact_done,
            a_wire_done,
            a_assemble_done,
            a_verify_done,
        ),
        gate=gate_decided,
        extra_gates=(FINAL_RESULT_GATE,),
        needs_you=FINAL_RESULT_GATE,
        publications=(p_json, p_markdown, p_redact, p_wire),
        integration=StageView(
            state="done",
            summary="Accepted patches assembled without conflict.",
            task_id="assemble",
            attempt_id=a_assemble.attempt_id,
            evidence_refs=a_assemble_done.evidence_refs,
        ),
        verification=StageView(
            state="done",
            summary="All bound checks passed against the assembled candidate.",
            task_id="verify",
            attempt_id=a_verify.attempt_id,
            evidence_refs=verify_refs[:1],
        ),
        resources=healthy_resources,
        result=ResultView(
            state="awaiting_decision",
            summary=(
                "The exact verified fixture candidate awaits the recorded simulated "
                f"decision · candidate sha256:{candidate_ref.sha256}."
            ),
            evidence_refs=verify_refs,
        ),
        mission_status="awaiting_result",
        unknowns=(
            "This replay does not establish live agent, Gemini, Cloud, human-attested approval, or arbitrary-repository execution.",
        ),
    )
    final_gate = FINAL_RESULT_GATE.model_copy(
        update={"status": "decided", "resolution": "continue_recorded_simulated_approval"}
    )
    s11 = snapshot(
        11,
        tasks({key: "done" for key in base}),
        (
            a_json_done,
            a_markdown_failed,
            a_markdown_done,
            a_redact_done,
            a_wire_done,
            a_assemble_done,
            a_verify_done,
        ),
        gate=gate_decided,
        extra_gates=(final_gate,),
        publications=(p_json, p_markdown, p_redact, p_wire),
        integration=StageView(
            state="done",
            summary="Accepted patches assembled without conflict.",
            task_id="assemble",
            attempt_id=a_assemble.attempt_id,
            evidence_refs=a_assemble_done.evidence_refs,
        ),
        verification=StageView(
            state="done",
            summary="All bound checks passed against the assembled candidate.",
            task_id="verify",
            attempt_id=a_verify.attempt_id,
            evidence_refs=verify_refs[:1],
        ),
        resources=healthy_resources,
        result=ResultView(
            state="commit_created",
            summary="The generated fixture depicts a verified isolated local commit; it did not run Git, mutate a user branch, or contact a remote during replay.",
            evidence_refs=(*verify_refs, commit_ref),
        ),
        mission_status="completed",
        unknowns=(
            "This replay does not establish live agent, Gemini, Cloud, or arbitrary-repository execution.",
        ),
    )
    return (s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11)


def render() -> bytes:
    values = stages()
    deltas = tuple(
        {
            "type": "delta",
            "cursor": after.cursor,
            "delta": diff_snapshots(before, after).model_dump(mode="json"),
        }
        for before, after in zip(values, values[1:])
    )
    final = values[-1]
    payload = {
        "meta": {
            "mode": MISSION_REPLAY_TRUTH_LABEL,
            "truth_label": MISSION_REPLAY_TRUTH_LABEL,
            "driver": "mission-replay",
            "live_agent": False,
            "human_attestation": False,
            "new_test_execution": False,
            "gemini_calls": 0,
            "cloud_proof": False,
            "final_snapshot_sha256": final.snapshot_sha256,
            "final_head": final.head.model_dump(mode="json"),
        },
        "snapshot": values[0].model_dump(mode="json"),
        "deltas": deltas,
    }
    return canonical_json_bytes(payload) + b"\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the checked-in Mission Control replay."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = render()
    digest_value = sha256_hex(content)
    digest_path = args.output.with_suffix(".sha256")
    if args.check:
        if (
            args.output.read_bytes() != content
            or digest_path.read_text().strip() != digest_value
        ):
            raise SystemExit(f"mission replay differs: generated sha256={digest_value}")
        return 0
    args.output.write_bytes(content)
    digest_path.write_text(digest_value + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
