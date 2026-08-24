"""Tests for graphene.demo_live: no provider, no real mission, no sleeping.

Every collaborator with a cost is a monkeypatched seam on the module itself;
the injected runner, sleeper, and clock mean nothing here spawns or waits.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console

from graphene import demo_live


class StubProcess:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode

    def poll(self) -> int:
        return self.returncode

    def wait(self) -> int:
        return self.returncode


def _task(task_id: str, kind: str, dependencies: list[str], writes: list[str]) -> dict:
    """A task shaped like a real `Plan` dump, so the renderers see real keys."""
    return {
        "task_id": task_id,
        "kind": kind,
        "state": "queued",
        "title": task_id,
        "contract": f"Complete {task_id}.",
        "dependencies": dependencies,
        "assigned_role": "worker",
        "read_paths": ["ledger_service/report.py"],
        "write_paths": writes,
        "allowed_commands": ["fixture-tests"],
        "acceptance_checks": ["fixture-tests"],
        "inputs": [],
        "expected_outputs": [{"name": "patch", "kind": "patch", "paths": writes}],
        "attempt_count": 0,
        "attempt_limit": 2,
        "priority": 1,
        "evidence_adapter": "generic_v1",
    }


PLAN = {
    "revision": 1,
    "tasks": [
        _task("work_json", "work", [], ["ledger_service/report_json.py"]),
        _task("work_markdown", "work", [], ["ledger_service/report_markdown.py"]),
        _task("verify", "verification", ["work_json", "work_markdown"], []),
    ],
    "criteria": [
        {
            "criterion_id": "criterion-reports",
            "description": "Both renderers exist and the target tests pass.",
            "producer_task_ids": ["work_json", "work_markdown"],
            "verification_kind": "deterministic_check",
            "verifier_task_id": "verify",
            "verifier_id": "fixture-tests",
        }
    ],
}


PLAN_VIEW = {
    "mission_id": "mission_start_demo",
    "base_sha": "b" * 40,
    "goal": "Add the two report renderers",
    "mission_status": "proposed",
    "plan_revision": 1,
    "previous_plan_revision": None,
    "plan_sha256": "e" * 64,
    "approved_revision": None,
    "critical_path": ["work_json", "verify"],
    "resource_budget": {},
    "ready_frontier": ["work_json", "work_markdown"],
    "frontier_is_projected": True,
    "needs_you": None,
    "task_states": {},
    "task_blockers": {},
    "plan": PLAN,
}


def _console() -> Console:
    # No file argument: rich resolves sys.stdout at print time, so capsys sees
    # every line the demo prints.
    return Console(force_terminal=False, width=200)


def _drive(
    monkeypatch, tmp_path: Path, *, status: str = "awaiting_result"
) -> tuple[int, Path, list[list[str]], list[str]]:
    """Run the whole story with every expensive seam faked out."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    target_repo = tmp_path / "target"
    target = SimpleNamespace(
        repository=target_repo,
        base_sha="b" * 40,
        policy=None,
        goal="Add the two report renderers",
        success_criteria=("both renderers exist",),
    )
    monkeypatch.setattr(demo_live, "_preflight", lambda: None)
    monkeypatch.setattr(demo_live, "_materialize", lambda dest, out: target)
    monkeypatch.setattr(demo_live, "_doctor_ready", lambda repository: None)
    monkeypatch.setattr(
        demo_live,
        "_trigger_mission",
        lambda inbox_dir, fault: ("mission_start_demo", "a" * 64),
    )
    monkeypatch.setattr(demo_live, "_plan", lambda mission_id: PLAN)
    monkeypatch.setattr(demo_live, "_plan_view", lambda mission_id: PLAN_VIEW)
    monkeypatch.setattr(demo_live, "_print_node", lambda *args: None)
    edit_calls: list[str] = []

    def fake_edit(console, mission_id, *, edited_plan, prompt):
        edit_calls.append(mission_id)
        console.print("PLAN REVISED mission_start_demo v1 -> v2", markup=False)
        return 2

    monkeypatch.setattr(demo_live, "_edit_plan", fake_edit)
    monkeypatch.setattr(demo_live, "_follow", lambda *args, **kwargs: None)
    monkeypatch.setattr(demo_live, "_mission_status", lambda mission_id: status)
    monkeypatch.setattr(demo_live, "_fault_fired", lambda mission_id: True)
    monkeypatch.setattr(
        demo_live,
        "_finalize",
        lambda mission_id: {
            "local_commit_sha": "c" * 40,
            "result_ref": "refs/graphene/results/demo",
            "bundle_id": "final_result_" + "d" * 32,
        },
    )
    feature_calls: list[str] = []

    def fake_feature(mission_id: str, commit_sha: str, console: Console) -> None:
        feature_calls.append(commit_sha)
        console.print("  | BOLT-M8 | 60 | below reorder |", markup=False)

    monkeypatch.setattr(demo_live, "_run_generated_feature", fake_feature)
    monkeypatch.setattr(
        demo_live,
        "_why_text",
        lambda mission_id, path: f"WHY {mission_id} {path} matched_by=write_path\n",
    )
    runner_calls: list[list[str]] = []

    def runner(argv):
        runner_calls.append(list(argv))
        return StubProcess(0 if status == "awaiting_result" else 1)

    code = demo_live.run_live_demo(
        target_root=target_repo,
        inbox=inbox,
        console=_console(),
        runner=runner,
        sleeper=lambda seconds: None,
        clock=lambda: 0.0,
    )
    assert edit_calls == ["mission_start_demo"], "the edit beat must always run"
    return code, inbox, runner_calls, feature_calls


def test_preflight_failure_is_one_sentence_no_traceback(
    monkeypatch, tmp_path, capsys
) -> None:
    monkeypatch.setattr(demo_live.shutil, "which", lambda name: None)
    code = demo_live.run_live_demo(
        target_root=tmp_path / "target",
        inbox=tmp_path,
        console=_console(),
        runner=lambda argv: StubProcess(),
        sleeper=lambda seconds: None,
        clock=lambda: 0.0,
    )
    out = capsys.readouterr().out
    assert code != 0
    assert "git" in out
    assert "Traceback" not in out
    assert len([line for line in out.splitlines() if line.strip()]) == 1


def test_trigger_file_written_with_placeholder_replaced(
    monkeypatch, tmp_path, capsys
) -> None:
    code, inbox, _runner_calls, _feature_calls = _drive(monkeypatch, tmp_path)
    assert code == 0
    text = (inbox / "north-star.yaml").read_text(encoding="utf-8")
    assert str(tmp_path / "target") in text
    assert "/ABSOLUTE/PATH/TO/north-star-target" not in text


def test_human_mode_prints_no_raw_json(monkeypatch, tmp_path, capsys) -> None:
    code, _inbox, _runner_calls, _feature_calls = _drive(monkeypatch, tmp_path)
    out = capsys.readouterr().out
    assert code == 0
    assert out.strip()
    for line in out.splitlines():
        assert not line.lstrip().startswith("{")
    assert "{'" not in out
    assert '{"' not in out


def test_mission_subprocess_argv_is_exact(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(
        demo_live.shutil, "which", lambda name: "/usr/local/bin/graphene"
    )
    code, _inbox, runner_calls, _feature_calls = _drive(monkeypatch, tmp_path)
    assert code == 0
    assert runner_calls == [
        [
            "/usr/local/bin/graphene",
            "--json",
            "mission",
            "approve-plan",
            "mission_start_demo",
            "--revision",
            "2",
            "--operator-label",
            "demo",
            "--rationale",
            demo_live._RATIONALE,
        ]
    ]


def test_incomplete_mission_skips_feature_beat_honestly(
    monkeypatch, tmp_path, capsys
) -> None:
    code, _inbox, _runner_calls, feature_calls = _drive(
        monkeypatch, tmp_path, status="failed"
    )
    out = capsys.readouterr().out
    assert code == 1
    assert feature_calls == []
    assert "The mission ended failed" in out
    assert "skipping the result and feature beats" in out
    assert "generated feature" not in out


def test_the_edit_beat_revises_lints_diffs_and_never_approves_by_itself(
    monkeypatch, tmp_path, capsys
) -> None:
    """The demo's own edit beat, with the real CLI value functions behind it.

    What matters on film is the order: the plan is exported, the user's edit
    becomes revision 2 with a new digest, lint and diff are shown, and the
    approval is a separate act — `_edit_plan` returns a revision number and
    approves nothing.
    """
    from graphene.cli import mission as mission_cli

    calls: list[str] = []
    supplied = tmp_path / "edited.yaml"
    supplied.write_text("edited-plan-document\n")

    def fake_export(mission_id: str, output):
        calls.append("export")
        Path(output).write_text("exported-plan-document\n")
        return {"status": "exported", "plan_revision": 1, "exported_to": str(output)}

    def fake_revise(source):
        calls.append("revise")
        # The demo must hand the compiler the *edited* bytes, not the export.
        assert Path(source).read_text() == "edited-plan-document\n"
        return {
            "status": "revised",
            "mission_id": "mission_start_demo",
            "previous_plan_revision": 1,
            "plan_revision": 2,
            "plan_sha256": "f" * 64,
            "needs_approval": True,
        }

    monkeypatch.setattr(demo_live, "_plan_view", lambda mission_id: PLAN_VIEW)
    monkeypatch.setattr(mission_cli, "_plan_export_value", fake_export)
    monkeypatch.setattr(mission_cli, "_plan_revise_value", fake_revise)
    monkeypatch.setattr(
        mission_cli,
        "_plan_lint_value",
        lambda mission_id: {
            "status": "valid",
            "valid": True,
            "mission_id": mission_id,
            "plan_revision": 2,
            "plan_sha256": "f" * 64,
            "criterion_coverage": [],
            "topological_order": [],
            "issues": [],
        },
    )
    monkeypatch.setattr(
        mission_cli,
        "_plan_diff_value",
        lambda mission_id, previous, current: {
            "mission_id": mission_id,
            "previous_plan_revision": previous,
            "plan_revision": current,
            "previous_plan_sha256": "e" * 64,
            "plan_sha256": "f" * 64,
            "max_concurrency": {"before": 2, "after": 2},
            "criteria": {"added": [], "removed": [], "changed": []},
            "tasks": {
                "added": [],
                "removed": [],
                "changed": [
                    {
                        "before": {"task_id": "work_json", "read_paths": ["a.py"]},
                        "after": {"task_id": "work_json", "read_paths": ["a.py", "b.py"]},
                    }
                ],
            },
        },
    )

    revision = demo_live._edit_plan(
        _console(),
        "mission_start_demo",
        edited_plan=supplied,
        prompt=lambda text: pytest.fail("a supplied edit must not wait on a person"),
    )

    out = capsys.readouterr().out
    assert revision == 2
    assert calls == ["export", "revise"]
    assert "PLAN v2" in out or "revision 2" in out
    assert "SCOPE EXPANSION" in out
    assert "PLAN DIFF mission_start_demo v1 -> v2" in out
    # The beat stops at the diff. Approval is the next, separate act.
    assert "approve this revision" in out
    for line in out.splitlines():
        assert not line.lstrip().startswith("{")
