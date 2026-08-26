from __future__ import annotations

import pytest
from pydantic import ValidationError

from graphene.hashing import canonical_json_sha256
from graphene.orchestration.mission_models import (
    ArtifactContract,
    ArtifactRequirement,
    CommandTemplate,
    Criterion,
    CriterionVerificationKind,
    Plan,
    ProjectPolicy,
    ResourceBudget,
    RetentionPolicy,
    Task,
    TaskKind,
)
from graphene.orchestration.validation import (
    PlanValidationError,
    require_valid_plan,
    validate_plan,
)


def _policy() -> ProjectPolicy:
    return ProjectPolicy(
        policy_id="policy-1",
        revision=1,
        repo_id="repo-1",
        base_ref="main",
        base_sha="a" * 40,
        allowed_read_globs=("app/**", "out/**", "tests/**"),
        allowed_write_globs=("app/**", "out/**", "tests/**"),
        command_templates=(
            CommandTemplate(template_id="check", argv=("pytest",), timeout_seconds=60),
            CommandTemplate(
                template_id="edit", argv=("python", "edit.py"), timeout_seconds=60
            ),
        ),
        agent_roles=("assembler", "verifier", "worker"),
        max_concurrency=4,
        retry_limit=1,
        resource_budget=ResourceBudget(
            max_worker_seconds=600,
            max_attempts=8,
            max_artifact_bytes=1_000_000,
        ),
        retention=RetentionPolicy(retain_days=7),
    )


def _task(
    task_id: str,
    output_name: str,
    output_kind: str,
    output_path: str,
    *,
    kind: TaskKind = TaskKind.WORK,
    role: str = "worker",
    dependencies: tuple[str, ...] = (),
    inputs: tuple[ArtifactRequirement, ...] = (),
) -> Task:
    return Task(
        task_id=task_id,
        title=task_id,
        contract=f"Produce {output_name}.",
        kind=kind,
        dependencies=dependencies,
        assigned_role=role,
        read_paths=("app/source.py",),
        write_paths=(output_path,),
        allowed_commands=("edit",),
        inputs=inputs,
        expected_outputs=(
            ArtifactContract(
                name=output_name,
                kind=output_kind,
                paths=(output_path,),
            ),
        ),
        acceptance_checks=("check",),
        priority=1,
        attempt_limit=2,
    )


def _plan() -> Plan:
    work_a = _task("work-a", "patch-a", "patch", "app/a.py")
    work_b = _task("work-b", "patch-b", "patch", "app/b.py")
    assembly = _task(
        "assemble",
        "candidate",
        "patch",
        "out/candidate.patch",
        kind=TaskKind.ASSEMBLY,
        role="assembler",
        dependencies=("work-a", "work-b"),
        inputs=(
            ArtifactRequirement(
                producer_task_id="work-a", name="patch-a", kind="patch"
            ),
            ArtifactRequirement(
                producer_task_id="work-b", name="patch-b", kind="patch"
            ),
        ),
    )
    verify = _task(
        "verify",
        "verification",
        "test-receipt",
        "out/verification.json",
        kind=TaskKind.VERIFICATION,
        role="verifier",
        dependencies=("assemble",),
        inputs=(
            ArtifactRequirement(
                producer_task_id="assemble",
                name="candidate",
                kind="patch",
            ),
        ),
    )
    return Plan(
        mission_id="mission-1",
        revision=1,
        criteria=(
            Criterion(
                criterion_id="criterion-checks",
                description="The bound checks pass.",
                producer_task_ids=("work-a", "work-b"),
                verification_kind=CriterionVerificationKind.DETERMINISTIC_CHECK,
                verifier_task_id="verify",
                verifier_id="check",
            ),
        ),
        tasks=tuple(
            sorted((assembly, verify, work_a, work_b), key=lambda item: item.task_id)
        ),
        max_concurrency=2,
    )


def _replace(plan: Plan, task_id: str, **updates: object) -> Plan:
    tasks = []
    for task in plan.tasks:
        values = task.model_dump(mode="json")
        tasks.append(
            Task.model_validate({**values, **updates})
            if task.task_id == task_id
            else task
        )
    return Plan.model_validate({**plan.model_dump(mode="json"), "tasks": tasks})


def _replace_criterion(plan: Plan, **updates: object) -> Plan:
    criterion = plan.criteria[0]
    return Plan.model_validate(
        {
            **plan.model_dump(mode="json"),
            "criteria": [{**criterion.model_dump(mode="json"), **updates}],
        }
    )


def test_valid_plan_is_pure_deterministic_and_topological() -> None:
    policy, plan = _policy(), _plan()
    before = canonical_json_sha256(plan.model_dump(mode="json"))

    first = validate_plan(policy, plan)
    second = require_valid_plan(policy, plan)

    assert first == second
    assert first.valid
    assert first.topological_order == ("work-a", "work-b", "assemble", "verify")
    assert canonical_json_sha256(plan.model_dump(mode="json")) == before


@pytest.mark.parametrize(
    ("changed", "code"),
    (
        (
            lambda plan: _replace(
                plan, "assemble", dependencies=("ghost", "work-a", "work-b")
            ),
            "missing_dependency",
        ),
        (
            lambda plan: _replace(
                plan,
                "assemble",
                inputs=(
                    ArtifactRequirement(
                        producer_task_id="work-a", name="wrong", kind="patch"
                    ),
                    ArtifactRequirement(
                        producer_task_id="work-b", name="patch-b", kind="patch"
                    ),
                ),
            ),
            "missing_artifact_contract",
        ),
        (
            lambda plan: _replace(
                plan,
                "work-b",
                write_paths=("app/a.py",),
                expected_outputs=(
                    ArtifactContract(name="patch-b", kind="patch", paths=("app/a.py",)),
                ),
            ),
            "parallel_write_conflict",
        ),
    ),
)
def test_plan_validator_reports_structured_failures(changed, code: str) -> None:
    result = validate_plan(_policy(), changed(_plan()))

    assert not result.valid
    assert code in {item.code for item in result.issues}
    with pytest.raises(PlanValidationError):
        require_valid_plan(_policy(), changed(_plan()))


def test_plan_validator_rejects_cycles() -> None:
    plan = _plan()
    cyclic = _replace(
        plan,
        "work-a",
        dependencies=("verify",),
        inputs=(
            ArtifactRequirement(
                producer_task_id="verify",
                name="verification",
                kind="test-receipt",
            ),
        ),
    )

    result = validate_plan(_policy(), cyclic)

    assert not result.valid
    assert result.topological_order == ()
    assert "cycle" in {item.code for item in result.issues}


def test_plan_rejects_legacy_evidence_without_a_trusted_adapter() -> None:
    plan = _replace(_plan(), "work-a", evidence_adapter="legacy_auth_v2")

    assert "legacy_adapter_unavailable" in {
        item.code for item in validate_plan(_policy(), plan).issues
    }


def test_plan_rejects_checks_the_completion_receipt_cannot_prove() -> None:
    plan = _replace(_plan(), "work-a", acceptance_checks=("check", "edit"))

    assert "acceptance_check_count_unsupported" in {
        item.code for item in validate_plan(_policy(), plan).issues
    }


def test_write_leases_are_exact_and_policy_globs_use_full_path_matching() -> None:
    with pytest.raises(ValidationError, match="must be exact"):
        Task.model_validate(
            {
                **_plan().tasks[-1].model_dump(mode="json"),
                "write_paths": ("app/**",),
                "expected_outputs": (
                    ArtifactContract(name="patch-a", kind="patch", paths=("app/**",)),
                ),
            }
        )

    policy = ProjectPolicy.model_validate(
        {
            **_policy().model_dump(mode="json"),
            "allowed_write_globs": ("app/*", "out/**", "tests/**"),
        }
    )
    nested = _replace(
        _plan(),
        "work-a",
        write_paths=("app/nested/a.py",),
        expected_outputs=(
            ArtifactContract(name="patch-a", kind="patch", paths=("app/nested/a.py",)),
        ),
    )

    assert "write_path_not_allowed" in {
        item.code for item in validate_plan(policy, nested).issues
    }


def test_read_glob_must_equal_policy_scope_and_cannot_hide_exclusions() -> None:
    broad_read = _replace(_plan(), "work-a", read_paths=("app/**",))
    narrow_policy = ProjectPolicy.model_validate(
        {
            **_policy().model_dump(mode="json"),
            "allowed_read_globs": ("app/*", "out/**", "tests/**"),
        }
    )
    excluded_policy = ProjectPolicy.model_validate(
        {
            **_policy().model_dump(mode="json"),
            "exclusions": ("app/secrets/**",),
        }
    )

    assert "read_path_not_allowed" in {
        item.code for item in validate_plan(narrow_policy, broad_read).issues
    }
    assert "read_path_not_allowed" in {
        item.code for item in validate_plan(excluded_policy, broad_read).issues
    }


def test_plan_requires_global_budget_for_declared_retry_limits() -> None:
    policy = _policy()
    policy = ProjectPolicy.model_validate(
        {
            **policy.model_dump(mode="json"),
            "resource_budget": {
                **policy.resource_budget.model_dump(mode="json"),
                "max_attempts": 7,
            },
        }
    )

    assert "attempt_budget_too_small" in {
        item.code for item in validate_plan(policy, _plan()).issues
    }


@pytest.mark.parametrize(
    ("changed", "code"),
    (
        (lambda plan: plan.model_copy(update={"criteria": ()}), "criterion_uncovered"),
        (
            lambda plan: _replace_criterion(
                plan, verifier_task_id=None, verifier_id=None
            ),
            "criterion_no_verifier",
        ),
        (
            lambda plan: _replace_criterion(
                plan,
                verification_kind=CriterionVerificationKind.MODEL_ASSERTION,
                verifier_task_id=None,
                verifier_id=None,
            ),
            "criterion_model_assertion",
        ),
        (
            lambda plan: _replace_criterion(plan, producer_task_ids=("verify",)),
            "criterion_self_verification",
        ),
    ),
)
def test_plan_rejects_unverifiable_criterion_coverage(changed, code: str) -> None:
    assert code in {item.code for item in validate_plan(_policy(), changed(_plan())).issues}


def test_assembly_frontier_must_name_transitive_leaf_outputs() -> None:
    chained = _replace(
        _plan(),
        "work-b",
        dependencies=("work-a",),
        inputs=(
            ArtifactRequirement(
                producer_task_id="work-a", name="patch-a", kind="patch"
            ),
        ),
    )
    chained = _replace(
        chained,
        "assemble",
        dependencies=("work-b",),
        inputs=(
            ArtifactRequirement(
                producer_task_id="work-b", name="patch-b", kind="patch"
            ),
        ),
    )

    assert "artifact_frontier_missing" in {
        item.code for item in validate_plan(_policy(), chained).issues
    }


def test_ordered_tasks_cannot_share_a_base_relative_write_scope() -> None:
    ordered = _replace(
        _plan(),
        "work-b",
        dependencies=("work-a",),
        inputs=(
            ArtifactRequirement(
                producer_task_id="work-a", name="patch-a", kind="patch"
            ),
        ),
        write_paths=("app/a.py",),
        expected_outputs=(
            ArtifactContract(name="patch-b", kind="patch", paths=("app/a.py",)),
        ),
    )

    assert "ordered_write_conflict" in {
        item.code for item in validate_plan(_policy(), ordered).issues
    }


def test_assembly_merge_workspace_may_cover_work_output_paths() -> None:
    merged = _replace(
        _plan(),
        "assemble",
        write_paths=("app/a.py", "app/b.py"),
        expected_outputs=(
            ArtifactContract(
                name="candidate",
                kind="patch",
                paths=("app/a.py", "app/b.py"),
            ),
        ),
    )

    assert not {
        item.code for item in validate_plan(_policy(), merged).issues
    } & {"ordered_write_conflict", "parallel_write_conflict"}


@pytest.mark.parametrize(
    ("changed", "code"),
    (
        (
            lambda plan: _replace(
                plan,
                "assemble",
                write_paths=("out/candidate.patch", "out/manifest.json"),
                expected_outputs=(
                    ArtifactContract(
                        name="candidate", kind="patch", paths=("out/candidate.patch",)
                    ),
                    ArtifactContract(
                        name="manifest", kind="report", paths=("out/manifest.json",)
                    ),
                ),
            ),
            "assembly_output_shape_unsupported",
        ),
        (
            lambda plan: _replace(
                plan,
                "assemble",
                expected_outputs=(
                    ArtifactContract(
                        name="candidate",
                        kind="snapshot",
                        paths=("out/candidate.patch",),
                    ),
                ),
            ),
            "assembly_output_kind_unsupported",
        ),
        (
            lambda plan: _replace(
                plan,
                "verify",
                dependencies=("assemble", "work-a"),
                inputs=(
                    ArtifactRequirement(
                        producer_task_id="assemble", name="candidate", kind="patch"
                    ),
                    ArtifactRequirement(
                        producer_task_id="work-a", name="patch-a", kind="patch"
                    ),
                ),
            ),
            "verification_input_shape_unsupported",
        ),
        (
            lambda plan: _replace(
                plan,
                "verify",
                expected_outputs=(
                    ArtifactContract(
                        name="verification",
                        kind="model-review",
                        paths=("out/verification.json",),
                    ),
                ),
            ),
            "verification_output_kind_unsupported",
        ),
    ),
)
def test_final_stage_shape_matches_runtime_protocol(changed, code: str) -> None:
    assert code in {item.code for item in validate_plan(_policy(), changed(_plan())).issues}


def test_output_name_is_the_publication_identity() -> None:
    duplicate = _replace(
        _plan(),
        "work-a",
        expected_outputs=(
            ArtifactContract(name="patch-a", kind="patch", paths=("app/a.py",)),
            ArtifactContract(name="patch-a", kind="report", paths=("app/a.py",)),
        ),
    )

    assert "duplicate_output_name" in {
        item.code for item in validate_plan(_policy(), duplicate).issues
    }
