"""The `/graphene` loop over MCP: plan, show the digest, stop for the signature, run, summarise.

Six tools and one prompt over the same CLI functions the terminal uses, so
the agent and the operator see one store. `approve_plan` requires the digest
string — the signature stays load-bearing: an agent cannot approve a plan it
has not shown, and a plan that moved between showing and signing fails
closed in the store. Every tool argument is a string, every tool's key set is
checked before dispatch, and nothing here prints to stdout or stderr.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import Any

from mcp import MCPError
from mcp.server import MCPServer
from mcp_types import INVALID_PARAMS

from .. import __version__

# name -> (required keys, optional keys); all values must be strings.
TOOL_ARGUMENTS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "plan_goal": (frozenset({"repo", "goal"}), frozenset({"driver", "success_criterion", "max_workers"})),
    "get_digest": (frozenset({"mission_id"}), frozenset()),
    "approve_plan": (frozenset({"mission_id", "digest"}), frozenset({"revision", "rationale"})),
    "mission_status": (frozenset({"mission_id"}), frozenset()),
    "why": (frozenset({"mission_id", "path"}), frozenset()),
    "mission_summary": (frozenset({"mission_id"}), frozenset()),
}

GOAL_PROMPT = """You are running the Graphene loop for this goal:

    {goal}

Graphene is a control plane, not an agent: it compiles the goal into a typed
mission graph, a human signs one exact revision, and work happens only inside
that signed map. Follow these steps in order and do not skip the signature.

1. Compile. Call `plan_goal` with `repo` set to the absolute path of the
   repository you are working in (it must already have `.graphene/project.json`
   from `graphene init`) and `goal` set to the text above. Use
   `driver="scripted-local"` unless the human asked for a live model run.
2. Show the map. Print the mission id, plan revision, `base_sha`, the digest,
   and every node of `task_graph` with its dependencies, exactly as returned.
   Tell the human they can watch it live with `graphene ui`.
3. STOP AND ASK THE HUMAN TO SIGN. Do not call `approve_plan` yet. Ask the
   human to reply with the digest (or "sign <digest>") if they approve the
   map, or with changes if they do not. Wait for their reply. If they want
   changes, tell them how to edit the plan (`graphene plan export`, edit,
   `graphene plan revise`) and start again from step 1 with the new revision.
4. Sign only what they signed. Call `approve_plan` with the mission id and the
   digest the human typed, never one you copied for them. If the store refuses
   because the digest does not match the committed revision, show the human
   the current digest and go back to step 3.
5. Run inside the map. Approval starts execution. Poll `mission_status` until
   the status is `awaiting_result`, `completed`, `failed`, or `cancelled`, or
   until `needs_you` names a decision only the human can make; relay that
   decision request verbatim and stop.
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
    """The mission control plane as an MCP server: six tools, one prompt."""

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
        description="Graphene mission control plane: compile a goal into a map, sign it, run inside it",
        version=__version__,
        instructions=(
            "Plan with plan_goal, show the digest, stop and ask the human to sign, "
            "approve_plan with the digest they typed, poll mission_status, then mission_summary."
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

    def digest_of(mission_id: str) -> dict[str, Any]:
        shown = dispatch(["plan", "show", mission_id])
        return {
            "mission_id": shown["mission_id"],
            "mission_status": shown["mission_status"],
            "goal": shown["goal"],
            "base_sha": shown["base_sha"],
            "plan_revision": shown["plan_revision"],
            "digest": shown["plan_sha256"],
            "approved_revision": shown["approved_revision"],
            "signed": shown["approved_revision"] == shown["plan_revision"],
            "task_states": shown["task_states"],
            "critical_path": shown["critical_path"],
        }

    @server.tool(structured_output=True)
    async def plan_goal(
        repo: str,
        goal: str,
        driver: str = "scripted-local",
        success_criterion: str = "",
        max_workers: str = "2",
    ) -> dict[str, Any]:
        """Compile GOAL into a mission map bound to REPO's HEAD; nothing runs until a human signs its digest."""
        argv = ["mission", "start", "--repo", repo, "--goal", goal, "--driver", driver, "--max-workers", max_workers]
        if success_criterion:
            argv += ["--success-criterion", success_criterion]
        with lock:
            proposed = dispatch(argv)
        digest = digest_of(str(proposed["mission_id"]))
        return {
            **digest,
            "driver": proposed.get("driver"),
            "proof": proposed.get("proof"),
            "task_graph": proposed.get("task_graph", []),
            "review_required": True,
            "next": "show the digest and task graph to the human and stop until they sign",
        }

    @server.tool(structured_output=True)
    async def get_digest(mission_id: str) -> dict[str, Any]:
        """The committed plan revision, its digest, and whether that revision is signed."""
        return digest_of(mission_id)

    @server.tool(structured_output=True)
    async def approve_plan(
        mission_id: str,
        digest: str,
        revision: str = "",
        rationale: str = "",
    ) -> dict[str, Any]:
        """Sign the plan whose digest the human typed; the store refuses any other digest. Approval starts execution."""
        current = digest_of(mission_id)
        target = revision or str(current["plan_revision"])
        argv = [
            "mission", "approve-plan", mission_id,
            "--revision", target,
            "--plan-sha256", digest,
            "--operator-label", f"{operator_label}-relay",
            "--rationale", rationale or "the human signed this digest in the agent session; relayed by the agent",
        ]
        with lock:
            result = dispatch(argv)
        value = result if isinstance(result, dict) else {"result": result}
        return {
            "mission_id": mission_id,
            "signed_digest": digest,
            "revision": int(target),
            "approval_truth": "server_derived: relayed by the agent, not TTY-attested",
            **{key: value[key] for key in ("status", "driver", "proof", "approval_truth") if key in value and key != "approval_truth"},
            "run": value,
        }

    @server.tool(structured_output=True)
    async def mission_status(mission_id: str) -> dict[str, Any]:
        """Where the mission is: status, signed state, every node's state, what needs a person, and the legal next commands."""
        from ..cli.mission import _next_legal_actions

        value = dispatch(["mission", "status", mission_id])
        mission = value["mission"]
        return {
            "mission_id": mission["mission_id"],
            "status": mission["status"],
            "goal": mission["goal"],
            "plan_revision": mission["plan_revision"],
            "digest": mission["plan_sha256"],
            "approved_plan_revision": mission["approved_plan_revision"],
            "signed": mission["approved_plan_revision"] == mission["plan_revision"],
            "tasks": [{"task_id": t["task_id"], "state": t["state"], "title": t["title"]} for t in value["tasks"]],
            "needs_you": value.get("needs_you"),
            "result": {"state": value["result"]["state"], "bundle_id": value["result"].get("bundle_id")},
            "head_seq": value["head"]["seq"],
            "next_actions": _next_legal_actions(value),
        }

    @server.tool(structured_output=True)
    async def why(mission_id: str, path: str) -> dict[str, Any]:
        """The lineage of PATH in this mission: trigger, target, producer attempt, prior attempts, checks, approval — with receipts."""
        return dispatch(["why", path, "--mission", mission_id])

    @server.tool(structured_output=True)
    async def mission_summary(mission_id: str) -> dict[str, Any]:
        """What was done: goal, every node's outcome, artifacts touched, the result, and one receipts line."""
        from ..cli.mission import _projection
        from ..orchestration.mission_projection import task_detail
        from ..ui.sources import summary_pane

        snapshot = _projection(mission_id).snapshot(mission_id)
        nodes = []
        receipts = 0
        for task in snapshot.tasks:
            detail = task_detail(snapshot, task.task_id)
            receipts += len(detail.test_receipts) + len(detail.command_receipts) + len(detail.resource_receipts)
            last = detail.attempts[-1] if detail.attempts else None
            nodes.append({
                "task_id": task.task_id,
                "state": str(task.state),
                "outcome": (last.result_code or last.status) if last else "no attempt",
                "attempts": len(detail.attempts),
            })
        touched = sorted({p for item in snapshot.publications if item.state == "accepted" for p in item.paths})
        return {
            "mission_id": snapshot.mission.mission_id,
            "goal": snapshot.mission.goal,
            "status": str(snapshot.mission.status),
            "outcome": snapshot.mission.outcome,
            "nodes": nodes,
            "artifacts_touched": touched,
            "result": {"state": str(snapshot.result.state), "bundle_id": snapshot.result.bundle_id, "summary": snapshot.result.summary},
            "receipts": receipts,
            "head_seq": snapshot.head.seq,
            "unknowns": list(snapshot.unknowns),
            "text": summary_pane(snapshot).plain,
        }

    @server.prompt(name="goal", description="Plan, sign, and run a goal inside the map: the /graphene loop")
    def goal(goal: str) -> str:
        return GOAL_PROMPT.format(goal=goal)

    for tool in server._tool_manager.list_tools():
        tool.parameters["additionalProperties"] = False
    return server


__all__ = ["GOAL_PROMPT", "TOOL_ARGUMENTS", "create_mission_mcp_server"]
