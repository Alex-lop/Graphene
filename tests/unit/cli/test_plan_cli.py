"""The `graphene plan` surface, driven through the real parser.

Every test here goes `main([...])` -> parser -> dispatch -> value -> renderer
against a real `SQLiteMissionStore`, because that is the path a person uses and
the path the filmed demo uses. Unit-testing the renderers alone would not have
caught an action wired to the wrong value function, an option accepted where it
should be refused, or a renderer that prints JSON at a human.

No repository, no policy on disk, no provider: the mission is built with the
store fixtures, so these run wherever the tests run rather than on macOS only.
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest

import graphene.cli.mission as mission_cli
from graphene.cli.main import main
from graphene.orchestration.plan_yaml import plan_from_yaml, plan_to_yaml
from graphene.orchestration.sqlite_mission_store import SQLiteMissionStore
from tests.unit.orchestration.test_store import _create, _policy

MISSION = "mission-1"


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SQLiteMissionStore:
    """A real, unapproved mission: the state the plan surface exists for."""
    value = SQLiteMissionStore(tmp_path / "missions.sqlite")
    _create(value, approve=False)
    monkeypatch.setattr(mission_cli, "_store_for_mission", lambda _mission_id: value)
    monkeypatch.setattr(mission_cli, "_store", lambda *args, **kwargs: value)
    monkeypatch.setattr(
        mission_cli,
        "_gemini_source",
        lambda _mission_id, _snapshot: (tmp_path, _policy(), 2),
    )
    return value


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    assert captured.err == "", captured.err
    return code, captured.out


def _no_raw_json(text: str) -> None:
    """Human mode never dumps a structure at the reader."""
    for line in text.splitlines():
        stripped = line.lstrip()
        assert not stripped.startswith(("{", "[")), line
    assert '{"' not in text and "{'" not in text


def test_show_prints_the_mission_table_and_detail_prints_node_contracts(
    store: SQLiteMissionStore, capsys: pytest.CaptureFixture[str]
) -> None:
    code, table = _run(capsys, "plan", "show", MISSION)
    assert code == 0
    _no_raw_json(table)
    assert table.startswith("Mission: mission-1")
    assert "ID" in table and "STATE" in table and "READ/WRITE" in table
    assert "Critical path:" in table
    # Nothing is approved, and the table says so rather than implying it.
    assert "Needs approval: plan v1" in table
    assert "Frontier on approval:" in table

    code, detail = _run(capsys, "plan", "show", MISSION, "--detail")
    assert code == 0
    _no_raw_json(detail)
    for field in (
        "outcome owned",
        "requires",
        "consumes",
        "read scope",
        "write scope",
        "allowed commands",
        "acceptance",
        "attempts",
        "bound to",
        "mission budget",
    ):
        assert field in detail, field
    assert "cannot dispatch until revision 1 is approved" in detail


def test_export_writes_canonical_yaml_that_revise_accepts(
    store: SQLiteMissionStore, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "plan.yaml"
    code, out = _run(capsys, "plan", "export", MISSION, "--output", str(target))
    assert code == 0
    _no_raw_json(out)
    assert "PLAN EXPORTED mission-1 v1" in out
    assert str(target) in out

    document = target.read_text()
    assert "graphene plan revise" in document, "the export tells you what to do next"
    assert plan_to_yaml(plan_from_yaml(document)) == document

    # The user's edit: one node gains a read path.
    plan = plan_from_yaml(document)
    tasks = [item.model_dump(mode="json") for item in plan.tasks]
    tasks[0]["read_paths"] = sorted({*tasks[0]["read_paths"], "app/source.py", "out/candidate.patch"})
    target.write_text(
        plan_to_yaml(plan.__class__.model_validate({**plan.model_dump(mode="json"), "tasks": tasks}))
    )

    code, revised = _run(capsys, "plan", "revise", str(target))
    assert code == 0
    _no_raw_json(revised)
    assert "PLAN REVISED mission-1 v1 -> v2" in revised
    assert "Not approved yet" in revised
    assert store.snapshot(MISSION).plan.revision == 2


def test_diff_names_the_change_and_flags_a_widened_scope(
    store: SQLiteMissionStore, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "plan.yaml"
    _run(capsys, "plan", "export", MISSION, "--output", str(target))
    plan = plan_from_yaml(target.read_text())
    tasks = [item.model_dump(mode="json") for item in plan.tasks]
    tasks[0]["read_paths"] = sorted({*tasks[0]["read_paths"], "out/candidate.patch"})
    target.write_text(
        plan_to_yaml(plan.__class__.model_validate({**plan.model_dump(mode="json"), "tasks": tasks}))
    )
    _run(capsys, "plan", "revise", str(target))

    code, diff = _run(capsys, "plan", "diff", MISSION, "1", "2")
    assert code == 0
    _no_raw_json(diff)
    assert "PLAN DIFF mission-1 v1 -> v2" in diff
    assert "read_paths" in diff
    # The line a reviewer must not be able to miss.
    assert "** SCOPE EXPANSION **" in diff
    assert "graphene plan approve mission-1 --revision 2" in diff


def test_lint_reports_the_criterion_matrix_and_exits_zero_when_valid(
    store: SQLiteMissionStore, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = _run(capsys, "plan", "lint", MISSION)
    assert code == 0
    _no_raw_json(out)
    assert out.startswith("PLAN mission-1 VALID revision=1")
    assert "CRITERION criterion-checks" in out


def test_json_mode_still_emits_canonical_json_for_every_action(
    store: SQLiteMissionStore, capsys: pytest.CaptureFixture[str]
) -> None:
    """Human mode renders; `--json` is what a machine reads. Both, not either."""
    for action in ("show", "lint"):
        code, out = _run(capsys, "--json", "plan", action, MISSION)
        assert code == 0
        value = json.loads(out)
        assert value["mission_id"] == MISSION
        assert value["plan_revision"] == 1


def test_each_action_refuses_the_options_that_belong_to_another(
    store: SQLiteMissionStore, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An option accepted where it means nothing is a lie about what will happen."""
    cases = (
        (["plan", "show", MISSION, "--output", str(tmp_path / "x.yaml")], "--output"),
        (["plan", "lint", MISSION, "--detail"], "--detail"),
        (["plan", "export", MISSION, "--plan-sha256", "0" * 64], "--plan-sha256"),
        (["plan", "diff", MISSION, "1"], "two revisions"),
        (["plan", "show", MISSION, "--repo", str(tmp_path)], "planning options"),
        (["plan", "approve", MISSION], "requires --revision"),
        (["plan", "show"], "requires a mission ID"),
    )
    for argv, reason in cases:
        assert main(argv) == 1, argv
        captured = capsys.readouterr()
        assert reason in captured.err, (argv, captured.err)


def test_edit_without_an_editor_says_so_instead_of_guessing(
    store: SQLiteMissionStore, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.delenv("VISUAL", raising=False)
    assert main(["plan", "edit", MISSION]) == 1
    assert "plan export and plan revise" in capsys.readouterr().err


def test_a_proposal_does_not_accept_the_action_options(
    store: SQLiteMissionStore, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["plan", "a goal", "--repo", str(tmp_path), "--detail"]) == 1
    assert "does not accept action options" in capsys.readouterr().err


def _private_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The private state root `plan edit` writes its scratch export into."""
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    monkeypatch.setenv("GRAPHENE_STATE_DIR", str(state))
    return state


def test_edit_hands_the_canonical_export_to_the_editor_and_revises_what_comes_back(
    store: SQLiteMissionStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`plan edit` under a non-interactive $EDITOR, end to end through the parser.

    The editor is a real program the CLI launches: it asserts the file it was
    handed is byte-for-byte the canonical export — so a `plan edit` that
    opened an empty or stale file fails here — and writes a valid revision
    back. Everything after that is the `plan revise` path, so the assertions
    below are the ones `plan revise` already has to satisfy.
    """
    state = _private_state(tmp_path, monkeypatch)
    code, out = _run(capsys, "--json", "plan", "export", MISSION)
    assert code == 0
    before = json.loads(out)
    exported = str(before["document"])
    expected = tmp_path / "expected.yaml"
    expected.write_text(exported)

    plan = plan_from_yaml(exported)
    tasks = [item.model_dump(mode="json") for item in plan.tasks]
    tasks[0]["read_paths"] = sorted({*tasks[0]["read_paths"], "out/candidate.patch"})
    revision = tmp_path / "revision.yaml"
    revision.write_text(
        plan_to_yaml(
            plan.__class__.model_validate(
                {**plan.model_dump(mode="json"), "tasks": tasks}
            )
        )
    )
    editor = tmp_path / "editor.py"
    editor.write_text(
        "import pathlib, sys\n"
        "given, wanted, target = (pathlib.Path(item) for item in sys.argv[1:4])\n"
        "assert target.read_text() == given.read_text(), 'not the canonical export'\n"
        "target.write_text(wanted.read_text())\n"
    )
    monkeypatch.setenv(
        "EDITOR",
        " ".join(
            shlex.quote(item)
            for item in (sys.executable, str(editor), str(expected), str(revision))
        ),
    )
    monkeypatch.delenv("VISUAL", raising=False)

    code, revised = _run(capsys, "plan", "edit", MISSION)

    assert code == 0
    _no_raw_json(revised)
    assert "PLAN REVISED mission-1 v1 -> v2" in revised
    assert "Not approved yet" in revised
    committed = store.snapshot(MISSION).plan
    assert committed.revision == 2
    assert committed.previous_revision == 1
    # A new revision is a new digest, and it is not approved by being made.
    after = json.loads(_run(capsys, "--json", "plan", "export", MISSION)[1])
    assert after["plan_revision"] == 2
    assert after["plan_sha256"] != before["plan_sha256"]
    shown = json.loads(_run(capsys, "--json", "plan", "show", MISSION)[1])
    assert shown["plan_sha256"] == after["plan_sha256"]
    assert shown["approved_revision"] is None
    # `lint` and `diff` behave exactly as they do after `plan revise`.
    assert _run(capsys, "plan", "lint", MISSION)[1].startswith(
        "PLAN mission-1 VALID revision=2"
    )
    diff = _run(capsys, "plan", "diff", MISSION, "1", "2")[1]
    assert "PLAN DIFF mission-1 v1 -> v2" in diff
    assert "read_paths" in diff
    assert "** SCOPE EXPANSION **" in diff
    # The scratch export is written under the private state root, not $CWD.
    assert (state / "plan-edits" / f"{MISSION}-v1.yaml").is_file()


def test_edit_whose_editor_exits_non_zero_revises_nothing(
    store: SQLiteMissionStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A refused edit is not a silent one, and it leaves the revision alone."""
    _private_state(tmp_path, monkeypatch)
    monkeypatch.setenv("EDITOR", "false")
    monkeypatch.delenv("VISUAL", raising=False)

    assert main(["plan", "edit", MISSION]) == 1

    assert "the editor exited non-zero" in capsys.readouterr().err
    assert store.snapshot(MISSION).plan.revision == 1
