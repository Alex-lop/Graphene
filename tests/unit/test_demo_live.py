"""Tests for graphene.demo_live: no provider, no real mission, no sleeping.

Every collaborator with a cost is a monkeypatched seam on the module itself;
the injected runner, sleeper, and clock mean nothing here spawns or waits.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

from graphene import demo_live


class StubProcess:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode

    def poll(self) -> int:
        return self.returncode

    def wait(self) -> int:
        return self.returncode


PLAN = {
    "revision": 1,
    "tasks": [
        {
            "task_id": "work_json",
            "kind": "work",
            "dependencies": [],
            "write_paths": ["ledger_service/report_json.py"],
        },
        {
            "task_id": "work_markdown",
            "kind": "work",
            "dependencies": [],
            "write_paths": ["ledger_service/report_markdown.py"],
        },
        {
            "task_id": "verify",
            "kind": "verification",
            "dependencies": ["work_json", "work_markdown"],
            "write_paths": [],
        },
    ],
    "criteria": [{"description": "Both renderers exist and the target tests pass."}],
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
            "1",
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
