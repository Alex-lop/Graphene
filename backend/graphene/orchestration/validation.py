from __future__ import annotations

from pathlib import PurePosixPath

from pydantic import Field

from ..core_models import FrozenModel
from ..hashing import canonical_json_sha256
from .mission_models import (
    AuthorizationMode,
    CriterionVerificationKind,
    FinalizationMode,
    Plan,
    PlanPolicyDecisionV1,
    ProjectPolicy,
    Task,
    TaskKind,
    TaskState,
)


class PlanValidationIssue(FrozenModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    task_id: str | None = None
    detail: str = Field(min_length=1, max_length=512)


class PlanValidationResult(FrozenModel):
    valid: bool
    topological_order: tuple[str, ...]
    issues: tuple[PlanValidationIssue, ...]


class PlanValidationError(ValueError):
    def __init__(self, result: PlanValidationResult) -> None:
        self.result = result
        super().__init__("; ".join(item.code for item in result.issues))


def _matches(path: str, globs: tuple[str, ...]) -> bool:
    candidate = PurePosixPath(path)
    return any(candidate.full_match(pattern) for pattern in globs)


def _read_scope_allowed(
    scope: str,
    allowed_globs: tuple[str, ...],
    exclusions: tuple[str, ...],
) -> bool:
    if any(character in scope for character in "*?["):
        # Pattern-to-pattern containment is not established by matching the
        # pattern strings. Keep wildcard scopes identical to an authority
        # scope, and fail closed when that authority has narrower exclusions.
        return scope in allowed_globs and not exclusions
    return _matches(scope, allowed_globs) and not _matches(scope, exclusions)


def _topological(tasks: dict[str, Task]) -> tuple[tuple[str, ...], bool]:
    indegree = {task_id: 0 for task_id in tasks}
    consumers = {task_id: [] for task_id in tasks}
    for task in tasks.values():
        for dependency in task.dependencies:
            if dependency in tasks:
                indegree[task.task_id] += 1
                consumers[dependency].append(task.task_id)
    ready = sorted(task_id for task_id, count in indegree.items() if count == 0)
    ordered: list[str] = []
    while ready:
        task_id = ready.pop(0)
        ordered.append(task_id)
        for consumer in sorted(consumers[task_id]):
            indegree[consumer] -= 1
            if indegree[consumer] == 0:
                ready.append(consumer)
                ready.sort()
    return tuple(ordered), len(ordered) != len(tasks)


def _ancestors(tasks: dict[str, Task]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}

    def visit(task_id: str, pending: set[str]) -> set[str]:
        if task_id in result:
            return result[task_id]
        if task_id in pending:
            return set()
        found: set[str] = set()
        for dependency in tasks[task_id].dependencies:
            if dependency not in tasks:
                continue
            found.add(dependency)
            found.update(visit(dependency, pending | {task_id}))
        result[task_id] = found
        return found

    for task_id in tasks:
        visit(task_id, set())
    return result


def validate_plan(policy: ProjectPolicy, plan: Plan) -> PlanValidationResult:
    """Validate a model-proposed plan without mutating it or repository state."""

    issues: list[PlanValidationIssue] = []
    tasks = {task.task_id: task for task in plan.tasks}
    templates = {item.template_id for item in policy.command_templates}

    def issue(code: str, detail: str, task_id: str | None = None) -> None:
        issues.append(PlanValidationIssue(code=code, task_id=task_id, detail=detail))

    if plan.max_concurrency > policy.max_concurrency:
        issue("concurrency_exceeds_policy", "plan concurrency exceeds project policy")
    if sum(task.attempt_limit for task in plan.tasks) > policy.resource_budget.max_attempts:
        issue(
            "attempt_budget_too_small",
            "mission attempt budget cannot cover every declared task attempt",
        )

    for task in plan.tasks:
        missing = sorted(set(task.dependencies) - set(tasks))
        if missing:
            issue(
                "missing_dependency",
                f"dependencies are absent: {', '.join(missing)}",
                task.task_id,
            )
        if task.state != TaskState.QUEUED or task.attempt_count != 0:
            issue(
                "non_initial_task_state", "new plan tasks must be queued", task.task_id
            )
        if task.attempt_limit > policy.retry_limit + 1:
            issue(
                "attempt_limit_exceeds_policy",
                "attempt limit exceeds policy",
                task.task_id,
            )
        if task.assigned_role not in policy.agent_roles:
            issue("role_not_allowed", "assigned role is not allowlisted", task.task_id)
        if task.evidence_adapter != "generic_v1":
            issue(
                "legacy_adapter_unavailable",
                "legacy evidence requires a trusted adapter that is not configured",
                task.task_id,
            )
        if len(task.acceptance_checks) != 1:
            issue(
                "acceptance_check_count_unsupported",
                "this evidence contract requires exactly one acceptance check",
                task.task_id,
            )
        unknown_commands = sorted(
            (set(task.allowed_commands) | set(task.acceptance_checks)) - templates
        )
        if unknown_commands:
            issue(
                "command_not_allowed",
                f"command templates are absent: {', '.join(unknown_commands)}",
                task.task_id,
            )
        for path in task.read_paths:
            if not _read_scope_allowed(
                path, policy.allowed_read_globs, policy.exclusions
            ):
                issue(
                    "read_path_not_allowed",
                    f"read path is forbidden: {path}",
                    task.task_id,
                )
        for path in task.write_paths:
            if not _matches(path, policy.allowed_write_globs) or _matches(
                path, policy.exclusions
            ):
                issue(
                    "write_path_not_allowed",
                    f"write path is forbidden: {path}",
                    task.task_id,
                )
        for output in task.expected_outputs:
            if any(path not in task.write_paths for path in output.paths):
                issue(
                    "output_outside_write_scope",
                    f"output {output.name} contains a path outside the task lease",
                    task.task_id,
                )
        output_names = tuple(item.name for item in task.expected_outputs)
        if len(output_names) != len(set(output_names)):
            issue(
                "duplicate_output_name",
                "task output names must identify one publication each",
                task.task_id,
            )
        for requirement in task.inputs:
            if requirement.producer_task_id not in task.dependencies:
                issue(
                    "input_without_dependency",
                    f"input producer {requirement.producer_task_id} is not a dependency",
                    task.task_id,
                )
                continue
            producer = tasks.get(requirement.producer_task_id)
            if producer is not None and not any(
                output.name == requirement.name and output.kind == requirement.kind
                for output in producer.expected_outputs
            ):
                issue(
                    "missing_artifact_contract",
                    f"dependency {requirement.producer_task_id} does not publish {requirement.name}",
                    task.task_id,
                )
        input_producers = {item.producer_task_id for item in task.inputs}
        for dependency in task.dependencies:
            if dependency in tasks and dependency not in input_producers:
                issue(
                    "dependency_without_artifact",
                    f"dependency {dependency} has no declared input artifact",
                    task.task_id,
                )

    order, cyclic = _topological(tasks)
    if cyclic:
        issue("cycle", "task dependency graph contains a cycle")
    ancestors = _ancestors(tasks)

    work_tasks = tuple(task for task in plan.tasks if task.kind == TaskKind.WORK)
    for index, left in enumerate(work_tasks):
        for right in work_tasks[index + 1 :]:
            if not set(left.write_paths) & set(right.write_paths):
                continue
            ordered = left.task_id in ancestors.get(
                right.task_id, set()
            ) or right.task_id in ancestors.get(left.task_id, set())
            issue(
                "ordered_write_conflict" if ordered else "parallel_write_conflict",
                f"tasks {left.task_id} and {right.task_id} overlap write scope",
            )

    if not plan.criteria:
        issue("criterion_uncovered", "plan declares no success-criterion coverage")
    for criterion in plan.criteria:
        producers = set(criterion.producer_task_ids)
        if not producers:
            issue(
                "criterion_uncovered",
                "criterion has no producing task",
                criterion.criterion_id,
            )
        missing_producers = sorted(producers - set(tasks))
        if missing_producers:
            issue(
                "criterion_missing_producer",
                f"criterion producers are absent: {', '.join(missing_producers)}",
                criterion.criterion_id,
            )
        if criterion.verification_kind == CriterionVerificationKind.MODEL_ASSERTION:
            issue(
                "criterion_model_assertion",
                "a model assertion cannot verify a success criterion",
                criterion.criterion_id,
            )
            continue
        if criterion.verification_kind == CriterionVerificationKind.HUMAN_GATE:
            if (
                criterion.verifier_task_id is not None
                or criterion.verifier_id not in policy.risk_gates
            ):
                issue(
                    "criterion_no_verifier",
                    "human verification requires a typed policy gate",
                    criterion.criterion_id,
                )
            continue
        verifier = tasks.get(criterion.verifier_task_id or "")
        if (
            verifier is None
            or verifier.kind != TaskKind.VERIFICATION
            or criterion.verifier_id not in verifier.acceptance_checks
        ):
            issue(
                "criterion_no_verifier",
                "deterministic verification requires a verification task check",
                criterion.criterion_id,
            )
            continue
        if verifier.task_id in producers:
            issue(
                "criterion_self_verification",
                "a producing task cannot verify its own criterion",
                criterion.criterion_id,
            )
        elif any(
            producer in tasks
            and producer not in ancestors.get(verifier.task_id, set())
            for producer in producers
        ):
            issue(
                "criterion_verifier_not_downstream",
                "criterion verifier is not downstream of every producer",
                criterion.criterion_id,
            )

    assemblies = [task for task in plan.tasks if task.kind == TaskKind.ASSEMBLY]
    verifiers = [task for task in plan.tasks if task.kind == TaskKind.VERIFICATION]
    if len(assemblies) != 1:
        issue("assembly_count", "plan requires exactly one assembly task")
    if len(verifiers) != 1:
        issue("verification_count", "plan requires exactly one verification task")
    if len(assemblies) == len(verifiers) == 1:
        assembly, verifier = assemblies[0], verifiers[0]
        required = {task.task_id for task in plan.tasks if task.kind == TaskKind.WORK}
        if not required <= ancestors.get(assembly.task_id, set()):
            issue("assembly_not_reachable", "assembly does not consume every work task")
        if assembly.task_id not in ancestors.get(verifier.task_id, set()):
            issue(
                "verification_not_bound", "verification is not downstream of assembly"
            )
        work_outputs = {
            (task.task_id, output.name, output.kind)
            for task in plan.tasks
            if task.kind == TaskKind.WORK
            for output in task.expected_outputs
        }
        frontier = {
            (item.producer_task_id, item.name, item.kind) for item in assembly.inputs
        }
        missing_frontier = sorted(work_outputs - frontier)
        if missing_frontier:
            issue(
                "artifact_frontier_missing",
                "assembly omits work outputs: "
                + ", ".join(f"{task_id}/{name}" for task_id, name, _ in missing_frontier),
                assembly.task_id,
            )
        extra_frontier = sorted(frontier - work_outputs)
        if extra_frontier:
            issue(
                "artifact_frontier_ambiguous",
                "assembly contains unsupported frontier inputs",
                assembly.task_id,
            )

        if len(assembly.expected_outputs) != 1:
            issue(
                "assembly_output_shape_unsupported",
                "assembly must publish exactly one candidate patch",
                assembly.task_id,
            )
        elif assembly.expected_outputs[0].kind != "patch":
            issue(
                "assembly_output_kind_unsupported",
                "assembly candidate kind must be patch",
                assembly.task_id,
            )

        expected_candidate = (
            None
            if len(assembly.expected_outputs) != 1
            else (
                assembly.task_id,
                assembly.expected_outputs[0].name,
                assembly.expected_outputs[0].kind,
            )
        )
        verifier_inputs = tuple(
            (item.producer_task_id, item.name, item.kind) for item in verifier.inputs
        )
        if (
            expected_candidate is None
            or verifier.dependencies != (assembly.task_id,)
            or verifier_inputs != (expected_candidate,)
        ):
            issue(
                "verification_input_shape_unsupported",
                "verification must consume only the exact assembly candidate",
                verifier.task_id,
            )
        if len(verifier.expected_outputs) != 1:
            issue(
                "verification_output_shape_unsupported",
                "verification must publish exactly one receipt",
                verifier.task_id,
            )
        elif verifier.expected_outputs[0].kind != "test-receipt":
            issue(
                "verification_output_kind_unsupported",
                "verification output kind must be test-receipt",
                verifier.task_id,
            )

    canonical_issues = tuple(
        sorted(issues, key=lambda item: (item.code, item.task_id or "", item.detail))
    )
    return PlanValidationResult(
        valid=not canonical_issues,
        topological_order=order if not cyclic else (),
        issues=canonical_issues,
    )


def require_valid_plan(policy: ProjectPolicy, plan: Plan) -> PlanValidationResult:
    result = validate_plan(policy, plan)
    if not result.valid:
        raise PlanValidationError(result)
    return result


def evaluate_plan_policy(
    policy: ProjectPolicy,
    plan: Plan,
    *,
    goal_request_id: str,
    requested_mode: AuthorizationMode,
    requested_finalization_mode: FinalizationMode | None = None,
) -> PlanPolicyDecisionV1:
    """Bind a valid plan to the narrowest effective authorization and result mode."""

    require_valid_plan(policy, plan)
    pre_authorized = (
        requested_mode == AuthorizationMode.POLICY_PRE_AUTHORIZED
        and policy.authorization_mode == AuthorizationMode.POLICY_PRE_AUTHORIZED
    )
    effective_mode = (
        AuthorizationMode.POLICY_PRE_AUTHORIZED
        if pre_authorized
        else AuthorizationMode.REVIEW_REQUIRED
    )
    requested_finalization = requested_finalization_mode or policy.finalization_mode
    finalization_mode = (
        FinalizationMode.AUTO_FINALIZE_ISOLATED
        if pre_authorized
        and requested_finalization == FinalizationMode.AUTO_FINALIZE_ISOLATED
        and policy.finalization_mode == FinalizationMode.AUTO_FINALIZE_ISOLATED
        else FinalizationMode.REVIEW_REQUIRED
    )
    reasons = ["plan_within_policy"]
    if requested_mode == AuthorizationMode.REVIEW_REQUIRED:
        reasons.append("review_requested")
    elif not pre_authorized:
        reasons.append("policy_requires_review")
    if finalization_mode == FinalizationMode.AUTO_FINALIZE_ISOLATED:
        reasons.append("isolated_result_pre_authorized")
    elif pre_authorized:
        reasons.append("final_review_required")
    return PlanPolicyDecisionV1.create(
        goal_request_id=goal_request_id,
        requested_mode=requested_mode,
        effective_mode=effective_mode,
        finalization_mode=finalization_mode,
        policy_id=policy.policy_id,
        policy_revision=policy.revision,
        policy_sha256=canonical_json_sha256(policy.model_dump(mode="json")),
        base_sha=policy.base_sha,
        plan_revision=plan.revision,
        plan_sha256=canonical_json_sha256(plan.model_dump(mode="json")),
        reason_codes=tuple(sorted(reasons)),
    )
