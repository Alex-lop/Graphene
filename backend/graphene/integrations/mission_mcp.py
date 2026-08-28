"""The durable `/graphene` MCP surface.

Starting a goal commits a private request and signals a detached Graphene
supervisor. Model latency and mission lifetime therefore never occupy the
STDIO request or depend on the controller process. Every argument is a
string, every key set is checked before dispatch, and errors are sanitised.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from typing import Any

from mcp import MCPError
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from mcp_types import INVALID_PARAMS

from .. import __version__

# name -> (required keys, optional keys); all values must be strings.
TOOL_ARGUMENTS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "start_goal": (
        frozenset({"repo", "goal", "request_id"}),
        frozenset(
            {
                "success_criterion",
                "success_criteria_json",
                "driver",
                "max_workers",
                "authorization_mode",
                "finalization_mode",
            }
        ),
    ),
    # Compatibility alias. New clients should supply their own request_id to
    # start_goal; this alias derives the same stable key as the CLI.
    "plan_goal": (
        frozenset({"repo", "goal"}),
        frozenset(
            {
                "driver",
                "success_criterion",
                "success_criteria_json",
                "max_workers",
                "authorization_mode",
                "finalization_mode",
            }
        ),
    ),
    "get_digest": (frozenset({"mission_id"}), frozenset()),
    "approve_plan": (
        frozenset({"mission_id", "digest"}),
        frozenset({"revision", "rationale"}),
    ),
    "approve_result": (
        frozenset({"mission_id", "bundle_id", "rationale"}),
        frozenset(),
    ),
    "reject_result": (
        frozenset({"mission_id", "bundle_id", "rationale"}),
        frozenset(),
    ),
    "mission_status": (frozenset({"mission_id"}), frozenset()),
    "why": (frozenset({"mission_id", "path"}), frozenset()),
    "mission_summary": (frozenset({"mission_id"}), frozenset()),
}

GOAL_PROMPT = """You are starting a durable Graphene mission for this goal:

    {goal}

Graphene is a control plane. It durably accepts the request, Gemini proposes
bounded work, Graphene validates the exact graph against checked-in policy,
and a detached supervisor continues if this controller disconnects.

1. Call `start_goal` with an absolute initialized repository path, a unique
   stable request_id, and either one `success_criterion` or a JSON-array string
   in `success_criteria_json`. The default is live `gemini-adk`; it never falls
   back to a fixture.
2. The call returns after durable acceptance, normally within five seconds.
   Poll `mission_status`; do not keep the start request open or restart the goal.
3. A `plan_review` decision is about permission to execute. Show its exact plan
   digest and call `approve_plan` only with the digest the reviewer supplied.
4. A later `result_review` decision is about the verified output. Show its exact
   bundle ID and call `approve_result` or `reject_result` only with that bundle
   ID and the reviewer's bounded rationale. These are separate decisions.
5. `policy_pre_authorized` work runs only after the exact compiled plan is
   validated inside policy and may auto-finalize to an isolated internal result
   ref only when policy explicitly permits it. Otherwise poll until `completed`,
   `failed`, `cancelled`, or `needs_you` names a bounded decision. Graphene never
   pushes, merges, deploys, or mutates the supplied checkout.
6. Report with receipts. Call `mission_summary` and relay it: goal, every node's
   outcome, artifacts touched, the result state, and the receipts line. If the
   human asks why a file looks the way it does, call `why` with that path.

Never claim a step happened that a tool did not confirm. Where a tool reports
unknowns, say so.
"""


def _sanitised(error: Exception) -> str:
    """Operator-facing CLI messages are safe to relay; anything else is a type name."""

    from ..cli.mission import MissionCliError

    if isinstance(error, MissionCliError):
        return str(error)
    return f"graphene refused the request ({type(error).__name__})"


def create_mission_mcp_server(*, operator_label: str = "mcp-agent") -> MCPServer:
    """The mission control plane as an MCP server."""

    lock = threading.Lock()

    async def reject_forged_arguments(ctx: Any, call_next: Any) -> Any:
        if ctx.method == "tools/call":
            params = ctx.params
            name = params.get("name") if isinstance(params, Mapping) else None
            arguments = params.get("arguments") if isinstance(params, Mapping) else None
            arguments = {} if arguments is None else arguments
            spec = TOOL_ARGUMENTS.get(name)
            if (
                spec is None
                or not isinstance(arguments, Mapping)
                or not spec[0] <= set(arguments) <= (spec[0] | spec[1])
                or any(not isinstance(value, str) for value in arguments.values())
            ):
                raise MCPError(INVALID_PARAMS, "Invalid tool request")
        return await call_next(ctx)

    server = MCPServer(
        name="graphene",
        description="Graphene durable mission control: agents stop; the mission does not",
        version=__version__,
        instructions=(
            "Start with start_goal and a stable request_id; it returns after durable acceptance. "
            "Poll mission_status. Policy-pre-authorized work continues in a detached supervisor "
            "and auto-finalizes only to an isolated local result; review_required plans use "
            "approve_plan with the exact displayed digest. Graphene never pushes or mutates the "
            "supplied checkout. Use mission_summary and why for committed proof."
        ),
        middleware=(reject_forged_arguments,),
    )

    def dispatch(argv: list[str]) -> Any:
        from ..cli import mission as mission_cli
        from ..cli.main import build_parser

        args = build_parser().parse_args(argv)
        try:
            code, value = mission_cli._dispatch(args)
        except Exception as error:  # noqa: BLE001 - relayed as a tool error, sanitised
            raise RuntimeError(_sanitised(error)) from None
        if code != 0:
            raise RuntimeError("graphene refused the request")
        return value

    def approval_of(
        mission_id: str, *, revision: int | None, digest: str | None
    ) -> dict[str, Any]:
        """Return the committed approval binding, without calling it a signature."""
        from ..cli.mission import _store_for_mission
        from ..orchestration.mission_models import MissionEventType

        if revision is None or digest is None:
            return {
                "approved_revision": None,
                "approved_digest": None,
                "approval_truth": None,
                "approval_authority": None,
                "signed": False,
                "signed_digest": None,
            }
        store = _store_for_mission(mission_id)
        try:
            snapshot = store.snapshot(mission_id)
            events = []
            after = 0
            while after < snapshot.head.seq:
                batch = store.tail(
                    mission_id, after, min(256, snapshot.head.seq - after)
                )
                if not batch:
                    raise RuntimeError("mission event history is incomplete")
                events.extend(batch)
                after = batch[-1].seq
        finally:
            store.close()
        for event in reversed(events):
            if (
                event.event_type == MissionEventType.PLAN_APPROVED
                and event.payload.get("plan_revision") == revision
                and event.payload.get("plan_sha256") == digest
            ):
                return {
                    "approved_revision": revision,
                    "approved_digest": digest,
                    "approval_truth": str(event.truth_kind),
                    "approval_authority": str(event.authority),
                    # Compatibility only: Graphene records approval authority,
                    # not an attested cryptographic signature.
                    "signed": False,
                    "signed_digest": None,
                }
        return {
            "approved_revision": None,
            "approved_digest": None,
            "approval_truth": None,
            "approval_authority": None,
            "signed": False,
            "signed_digest": None,
        }

    def digest_of(mission_id: str) -> dict[str, Any]:
        from ..orchestration.supervisor import supervisor_acceptance

        try:
            shown = dispatch(["plan", "show", mission_id])
        except RuntimeError as error:
            # Before the detached planner commits a mission aggregate, the
            # private acceptance journal is the honest read model.
            try:
                request, accepted = supervisor_acceptance(mission_id)
            except Exception:
                raise error
            return {
                "mission_id": mission_id,
                "mission_status": accepted.phase,
                "goal": request.goal,
                "base_sha": request.base_sha,
                "plan_revision": None,
                "digest": None,
                "approved_revision": None,
                "approved_digest": None,
                "approval_truth": None,
                "approval_authority": None,
                "signed": False,
                "signed_digest": None,
                "task_states": {},
                "critical_path": [],
                "requested_authorization_mode": request.requested_mode,
                "effective_authorization_mode": None,
                "finalization_mode": request.finalization_mode,
                "policy_decision_sha256": None,
            }
        approval = approval_of(
            mission_id,
            revision=shown["plan_revision"],
            digest=shown["plan_sha256"],
        )
        return {
            "mission_id": shown["mission_id"],
            "mission_status": shown["mission_status"],
            "goal": shown["goal"],
            "base_sha": shown["base_sha"],
            "plan_revision": shown["plan_revision"],
            "digest": shown["plan_sha256"],
            **approval,
            "task_states": shown["task_states"],
            "critical_path": shown["critical_path"],
            "requested_authorization_mode": shown["requested_authorization_mode"],
            "effective_authorization_mode": shown["effective_authorization_mode"],
            "finalization_mode": shown["finalization_mode"],
            "policy_decision_sha256": shown["policy_decision_sha256"],
        }

    def accepted_value(request: Any, state: Any) -> dict[str, Any]:
        return {
            "mission_id": request.mission_id,
            "mission_status": state.phase,
            "goal": request.goal,
            "plan_revision": None,
            "digest": None,
            "approved_revision": None,
            "approved_digest": None,
            "approval_truth": None,
            "approval_authority": None,
            "signed": False,
            "signed_digest": None,
            "task_states": {},
            "critical_path": [],
            "accepted_request_id": request.command_id,
            "requested_authorization_mode": request.requested_mode,
            "effective_authorization_mode": None,
            "authorization_mode": None,
            "finalization_mode": request.finalization_mode,
            "committed_policy_revision": request.policy_revision,
            "committed_policy_digest": request.policy_sha256,
            "base_sha": request.base_sha,
            "driver": request.driver,
            "state": state.phase,
            "proof": (
                "simulated fixture; no Gemini or cloud execution"
                if request.driver == "scripted-local"
                else "durably accepted live Gemini mission; provider work is asynchronous"
            ),
            "task_graph": [],
            "review_required": state.phase == "review_required",
            "next": f"poll mission_status with mission_id {request.mission_id}",
        }

    def review_need(value: dict[str, Any]) -> dict[str, Any] | None:
        mission = value["mission"]
        if (
            mission["status"] == "proposed"
            and mission.get("effective_authorization_mode", "review_required") is None
        ):
            return None
        pending = value.get("needs_you")
        if isinstance(pending, dict):
            gate_id = str(pending.get("gate_id") or "")
            return {
                **pending,
                "decision_kind": (
                    "result_review" if gate_id.startswith("final_result_") else "gate"
                ),
                **(
                    {"bundle_id": gate_id}
                    if gate_id.startswith("final_result_")
                    else {}
                ),
            }
        if (
            mission["status"] == "proposed"
            and mission.get("approved_plan_revision") is None
        ):
            return {
                "decision_kind": "plan_review",
                "plan_revision": mission["plan_revision"],
                "digest": mission["plan_sha256"],
            }
        return None

    def criteria_from(single: str, encoded: str, *, driver: str) -> tuple[str, ...]:
        if not single and not encoded:
            if driver == "scripted-local":
                return ()
            raise RuntimeError("Gemini goals require explicit success criteria")
        if single and encoded:
            raise RuntimeError(
                "supply exactly one of success_criterion or success_criteria_json"
            )
        if single:
            return (single,)
        try:
            values = json.loads(encoded)
        except ValueError as error:
            raise RuntimeError("success_criteria_json is not valid JSON") from error
        if (
            not isinstance(values, list)
            or not 1 <= len(values) <= 32
            or any(not isinstance(item, str) or not item.strip() for item in values)
            or len(set(values)) != len(values)
        ):
            raise RuntimeError(
                "success_criteria_json must be 1-32 unique non-empty strings"
            )
        return tuple(values)

    @server.tool(
        structured_output=True,
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        ),
    )
    async def start_goal(
        repo: str,
        goal: str,
        request_id: str,
        success_criterion: str = "",
        success_criteria_json: str = "",
        driver: str = "gemini-adk",
        max_workers: str = "2",
        authorization_mode: str = "policy_pre_authorized",
        finalization_mode: str = "auto_finalize_isolated",
    ) -> dict[str, Any]:
        """Durably accept GOAL and return without awaiting planning or execution."""
        from pathlib import Path

        from ..orchestration.supervisor import accept_goal

        with lock:
            request, state = accept_goal(
                repository=Path(repo),
                goal=goal,
                success_criteria=criteria_from(
                    success_criterion, success_criteria_json, driver=driver
                ),
                driver=driver,
                max_workers=int(max_workers),
                command_id=request_id,
                requested_mode=authorization_mode,
                finalization_mode=finalization_mode,
            )
        return accepted_value(request, state)

    @server.tool(
        structured_output=True,
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        ),
    )
    async def plan_goal(
        repo: str,
        goal: str,
        driver: str = "gemini-adk",
        success_criterion: str = "",
        success_criteria_json: str = "",
        max_workers: str = "2",
        authorization_mode: str = "policy_pre_authorized",
        finalization_mode: str = "auto_finalize_isolated",
    ) -> dict[str, Any]:
        """Deprecated nonblocking alias for start_goal with a derived request ID."""
        from argparse import Namespace
        from pathlib import Path

        from ..cli.mission import _start_identity
        from ..orchestration.supervisor import accept_goal

        criteria = criteria_from(
            success_criterion, success_criteria_json, driver=driver
        )
        identity_args = Namespace(
            repo=Path(repo),
            goal=goal,
            success_criteria=list(criteria),
            driver=driver,
            max_workers=int(max_workers),
            auto_approve=False,
            command_id=None,
            open_viewer=False,
            json_mode=True,
            demo_injected_check_fault=False,
        )
        command_id = _start_identity(identity_args)[0]
        with lock:
            request, state = accept_goal(
                repository=Path(repo),
                goal=goal,
                success_criteria=criteria,
                driver=driver,
                max_workers=int(max_workers),
                command_id=command_id,
                requested_mode=authorization_mode,
                finalization_mode=finalization_mode,
            )
        return {**accepted_value(request, state), "deprecated_alias": True}

    @server.tool(
        structured_output=True,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def get_digest(mission_id: str) -> dict[str, Any]:
        """The committed plan revision, digest, and exact approval authority."""
        return digest_of(mission_id)

    @server.tool(
        structured_output=True,
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        ),
    )
    async def approve_plan(
        mission_id: str,
        digest: str,
        revision: str = "",
        rationale: str = "",
    ) -> dict[str, Any]:
        """Approve an exact review-mode plan and signal its detached supervisor."""
        current = digest_of(mission_id)
        if current["digest"] is None:
            raise RuntimeError("graphene plan is not materialized yet")
        target = revision or str(current["plan_revision"])
        from datetime import UTC, datetime

        from ..cli.mission import _command_id, _store_for_mission
        from ..core_models import TruthKind
        from ..hashing import canonical_json_sha256
        from ..orchestration.supervisor import (
            SupervisorError,
            ensure_supervisor,
            supervisor_status,
        )

        store = _store_for_mission(mission_id)
        try:
            snapshot = store.snapshot(mission_id)
            plan_sha = canonical_json_sha256(snapshot.plan.model_dump(mode="json"))
            if int(target) != snapshot.plan.revision or digest != plan_sha:
                raise RuntimeError(
                    "plan approval digest does not match the committed revision"
                )
            label = f"{operator_label}-relay"
            reason = rationale or "review approval relayed by the MCP controller"
            with lock:
                try:
                    supervisor_status(mission_id)
                except SupervisorError:
                    # Legacy missions predate the detached request journal. Keep
                    # their old synchronous compatibility path explicit.
                    result = dispatch(
                        [
                            "mission",
                            "approve-plan",
                            mission_id,
                            "--revision",
                            target,
                            "--plan-sha256",
                            digest,
                            "--operator-label",
                            label,
                            "--rationale",
                            reason,
                        ]
                    )
                    value = result if isinstance(result, dict) else {"result": result}
                else:
                    store.approve_plan(
                        mission_id,
                        _command_id("approve-plan", mission_id, target, label, reason),
                        expected_revision=int(target),
                        expected_head=snapshot.head,
                        operator_label=label,
                        rationale=reason,
                        truth_kind=TruthKind.SERVER_DERIVED,
                        recorded_at=datetime.now(UTC),
                        expected_plan_sha256=digest,
                    )
                    supervisor = ensure_supervisor(mission_id, recover_failed=True)
                    value = {
                        "status": supervisor.phase,
                        "supervisor_generation": supervisor.generation,
                    }
        finally:
            store.close()
        approval = approval_of(mission_id, revision=int(target), digest=digest)
        return {
            "mission_id": mission_id,
            **approval,
            **{
                key: value[key] for key in ("status", "driver", "proof") if key in value
            },
            "run": value,
        }

    def decide_result(
        mission_id: str, bundle_id: str, rationale: str, *, approved: bool
    ) -> dict[str, Any]:
        reason = rationale.strip()
        if not reason or len(reason) > 280 or "\x00" in reason:
            raise RuntimeError("result rationale must be 1-280 public characters")
        current = dispatch(["mission", "status", mission_id])
        current_bundle = current["result"].get("bundle_id")
        if current_bundle is None:
            raise RuntimeError("final result bundle is not available")
        if bundle_id != current_bundle:
            raise RuntimeError(
                "result decision bundle does not match the current bundle"
            )
        label = f"{operator_label}-result-relay"
        with lock:
            value = dispatch(
                [
                    "mission",
                    "approve-result" if approved else "reject-result",
                    mission_id,
                    "--bundle-id",
                    bundle_id,
                    "--operator-label",
                    label,
                    "--rationale",
                    reason,
                ]
            )
        return {
            **value,
            "decision_truth": "server_derived",
            "decision_authority": "mission_service",
            "decision_operator": label,
        }

    @server.tool(
        structured_output=True,
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def approve_result(
        mission_id: str, bundle_id: str, rationale: str
    ) -> dict[str, Any]:
        """Approve the exact current verified bundle as an isolated local result."""
        return decide_result(mission_id, bundle_id, rationale, approved=True)

    @server.tool(
        structured_output=True,
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def reject_result(
        mission_id: str, bundle_id: str, rationale: str
    ) -> dict[str, Any]:
        """Reject the exact current verified bundle without creating a commit."""
        return decide_result(mission_id, bundle_id, rationale, approved=False)

    @server.tool(
        structured_output=True,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def mission_status(mission_id: str) -> dict[str, Any]:
        """Status, approval authority, node states, needs-you, and legal next commands."""
        from ..cli.mission import _next_legal_actions

        from ..orchestration.supervisor import (
            SupervisorError,
            supervisor_acceptance,
        )

        try:
            request, supervisor = supervisor_acceptance(mission_id)
        except SupervisorError:
            request = None
            supervisor = None
        try:
            value = dispatch(["mission", "status", mission_id])
        except RuntimeError:
            if supervisor is None:
                raise
            return {
                "mission_id": mission_id,
                "status": supervisor.phase,
                "goal": request.goal,
                "plan_revision": None,
                "digest": None,
                "approved_plan_revision": None,
                "approved_revision": None,
                "approved_digest": None,
                "approval_truth": None,
                "approval_authority": None,
                "signed": False,
                "signed_digest": None,
                "tasks": [],
                "needs_you": None,
                "result": {"state": "pending", "bundle_id": None},
                "head_seq": 0,
                "supervisor": supervisor.model_dump(mode="json"),
                "requested_authorization_mode": request.requested_mode,
                "effective_authorization_mode": None,
                "finalization_mode": request.finalization_mode,
                "policy_decision_sha256": None,
                "next_actions": [f"mission_status {mission_id}"],
            }
        mission = value["mission"]
        approval = approval_of(
            mission_id,
            revision=mission["plan_revision"],
            digest=mission["plan_sha256"],
        )
        return {
            "mission_id": mission["mission_id"],
            "status": mission["status"],
            "goal": mission["goal"],
            "plan_revision": mission["plan_revision"],
            "digest": mission["plan_sha256"],
            "approved_plan_revision": mission["approved_plan_revision"],
            **approval,
            "tasks": [
                {"task_id": t["task_id"], "state": t["state"], "title": t["title"]}
                for t in value["tasks"]
            ],
            "needs_you": review_need(value),
            "result": {
                "state": value["result"]["state"],
                "bundle_id": value["result"].get("bundle_id"),
            },
            "head_seq": value["head"]["seq"],
            "requested_authorization_mode": mission.get(
                "requested_authorization_mode", "review_required"
            ),
            "effective_authorization_mode": mission.get(
                "effective_authorization_mode", "review_required"
            ),
            "finalization_mode": mission.get("finalization_mode", "review_required"),
            "policy_decision_sha256": mission.get("policy_decision_sha256"),
            "supervisor": (
                None if supervisor is None else supervisor.model_dump(mode="json")
            ),
            "next_actions": _next_legal_actions(value),
        }

    @server.tool(
        structured_output=True,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def why(mission_id: str, path: str) -> dict[str, Any]:
        """The lineage of PATH in this mission: trigger, target, producer attempt, prior attempts, checks, approval — with receipts."""
        return dispatch(["why", path, "--mission", mission_id])

    @server.tool(
        structured_output=True,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def mission_summary(mission_id: str) -> dict[str, Any]:
        """What was done: goal, every node's outcome, artifacts touched, the result, and one receipts line."""
        from ..cli.mission import _projection
        from ..orchestration.mission_projection import task_detail
        from ..ui.sources import summary_pane

        projection = _projection(mission_id)
        try:
            snapshot = projection.snapshot(mission_id)
            nodes = []
            receipts = 0
            for task in snapshot.tasks:
                detail = task_detail(snapshot, task.task_id)
                receipts += (
                    len(detail.test_receipts)
                    + len(detail.command_receipts)
                    + len(detail.resource_receipts)
                )
                last = detail.attempts[-1] if detail.attempts else None
                nodes.append(
                    {
                        "task_id": task.task_id,
                        "state": str(task.state),
                        "outcome": (
                            (last.result_code or last.status) if last else "no attempt"
                        ),
                        "attempts": len(detail.attempts),
                    }
                )
            touched = sorted(
                {
                    path
                    for item in snapshot.publications
                    if item.state == "accepted"
                    for path in item.paths
                }
            )
            return {
                "mission_id": snapshot.mission.mission_id,
                "goal": snapshot.mission.goal,
                "status": str(snapshot.mission.status),
                "outcome": snapshot.mission.outcome,
                "nodes": nodes,
                "artifacts_touched": touched,
                "result": {
                    "state": str(snapshot.result.state),
                    "bundle_id": snapshot.result.bundle_id,
                    "summary": snapshot.result.summary,
                },
                "receipts": receipts,
                "head_seq": snapshot.head.seq,
                "unknowns": list(snapshot.unknowns),
                "requested_authorization_mode": str(
                    snapshot.mission.requested_authorization_mode
                ),
                "effective_authorization_mode": (
                    None
                    if snapshot.mission.effective_authorization_mode is None
                    else str(snapshot.mission.effective_authorization_mode)
                ),
                "finalization_mode": str(snapshot.mission.finalization_mode),
                "policy_decision_sha256": snapshot.mission.policy_decision_sha256,
                "text": summary_pane(snapshot).plain,
            }
        finally:
            close = getattr(projection.store, "close", None)
            if callable(close):
                close()

    @server.prompt(
        name="goal", description="Start and follow one durable bounded coding mission"
    )
    def goal(goal: str) -> str:
        return GOAL_PROMPT.format(goal=goal)

    for tool in server._tool_manager.list_tools():
        tool.parameters["additionalProperties"] = False
    return server


__all__ = ["GOAL_PROMPT", "TOOL_ARGUMENTS", "create_mission_mcp_server"]
