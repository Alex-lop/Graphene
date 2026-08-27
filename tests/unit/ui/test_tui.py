"""`graphene ui` headless: the replay renders, keys work, q quits, panes come from the store."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Static

from graphene.cli.main import build_parser
from graphene.orchestration.mission_projection import MissionProjection
from graphene.orchestration.mission_replay import load_verified_mission_replay
from graphene.orchestration.scripted import load_scenario, propose_scripted_mission
from graphene.orchestration.sqlite_mission_store import SQLiteMissionStore
from graphene.ui.frames import compose_frame
from graphene.ui.read_only_store import ReadOnlyMissionStore
from graphene.ui.run import build_source, handle
from graphene.ui.sources import LiveSource, ReplaySource
from graphene.ui.tui import GrapheneUI


def _plain(app: GrapheneUI, widget_id: str) -> str:
    content = app.query_one(f"#{widget_id}", Static).content
    return content.plain if hasattr(content, "plain") else str(content)


@pytest.fixture
def replay_source() -> ReplaySource:
    return ReplaySource(load_verified_mission_replay())


def test_replay_renders_dag_banner_and_signed_state_then_q_quits(replay_source: ReplaySource) -> None:
    async def scenario() -> None:
        app = GrapheneUI(replay_source)
        async with app.run_test(size=(120, 45)) as pilot:
            banner = _plain(app, "banner")
            assert "mission_status_reports" in banner and "PLAN v1" in banner
            assert "digest 9b9f15f52186" in banner and "AUTHORIZED — revision 1 approved" in banner
            dag = _plain(app, "dag")
            for task_id in ("redact_notes", "render_json", "render_markdown", "wire_cli", "assemble", "verify"):
                assert task_id in dag
            assert "needs_input" in dag and "▼" in dag and "->" not in dag
            await pilot.press("q")
        assert app.return_code == 0 or app.return_code is None


    asyncio.run(scenario())


def test_stepping_checkpoints_changes_node_states(replay_source: ReplaySource) -> None:
    async def scenario() -> None:
        app = GrapheneUI(replay_source)
        async with app.run_test(size=(120, 45)) as pilot:
            assert "◐ ready" in _plain(app, "dag")
            await pilot.press("n")
            await pilot.pause()
            assert "● running" in _plain(app, "dag") and "checkpoint 2/11" in _plain(app, "banner")
            for _ in range(12):
                await pilot.press("n")
            await pilot.pause()
            assert "checkpoint 11/11" in _plain(app, "banner")
            assert "completed" in _plain(app, "banner")
            await pilot.press("q")


    asyncio.run(scenario())


def test_selecting_a_node_and_pressing_enter_opens_its_why_pane(replay_source: ReplaySource) -> None:
    async def scenario() -> None:
        app = GrapheneUI(replay_source)
        async with app.run_test(size=(140, 45)) as pilot:
            for _ in range(11):
                await pilot.press("n")
            await pilot.press("j")  # first node in snapshot order: assemble
            await pilot.press("j")  # redact_notes
            await pilot.press("enter")
            await pilot.pause()
            assert "┃ redact_notes" in _plain(app, "dag")
            pane = _plain(app, "pane")
            assert pane.startswith("redact_notes")
            assert "Redact private notes" in pane
            assert "attempts" in pane and "#1 committed · passed" in pane
            assert "checks" in pane and "receipts" in pane and "lineage" in pane
            assert "the replay carries checkpoints" in pane
            await pilot.press("escape")
            await pilot.pause()
            assert _plain(app, "pane") == ""
            await pilot.press("q")


    asyncio.run(scenario())


def test_summary_view_is_built_from_the_snapshot(replay_source: ReplaySource) -> None:
    async def scenario() -> None:
        app = GrapheneUI(replay_source)
        async with app.run_test(size=(140, 45)) as pilot:
            for _ in range(11):
                await pilot.press("n")
            await pilot.press("s")
            await pilot.pause()
            pane = _plain(app, "pane")
            final = replay_source.replay.stages[-1]
            assert pane.startswith("what was done")
            assert final.mission.goal in pane
            assert "mission completed" in pane
            for task in final.tasks:
                assert task.task_id in pane
            assert "fixture/redact_notes.patch" in pane and "fixture/wire_cli.patch" in pane
            assert "commit_created" in pane
            assert "receipts:" in pane and f"head seq {final.head.seq}" in pane
            await pilot.press("q")


    asyncio.run(scenario())


def test_frame_dump_and_once_are_plain_text_from_the_same_renderer(replay_source: ReplaySource, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    frame = compose_frame(replay_source, pane="summary")
    assert "\x1b[" not in frame and "->" not in frame
    assert "what was done" in frame and "AUTHORIZED" in frame
    args = build_parser().parse_args(["ui", "--replay", "taskmaster", "--once"])
    assert handle(args) == 0
    out = capsys.readouterr().out
    assert out.startswith("GRAPHENE mission_status_reports")
    args = build_parser().parse_args(["ui", "--replay", "taskmaster", "--frames", str(tmp_path / "frames"), "--poll", "0"])
    assert handle(args) == 0
    frames = sorted((tmp_path / "frames").glob("frame-*.txt"))
    assert len(frames) == 12  # 11 checkpoints and the closing summary frame
    assert "checkpoint 1/11" in frames[0].read_text()
    assert "what was done" in frames[-1].read_text()


def test_live_source_attaches_read_only_to_the_most_recent_active_mission(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    store = SQLiteMissionStore(state / "missions.sqlite3")
    propose_scripted_mission(scenario=load_scenario(), store=store, runtime=state / "runtime", mission_id="mission-ui-live")
    args = build_parser().parse_args(["ui", "--state-dir", str(state), "--once"])
    source = build_source(args)
    assert isinstance(source, LiveSource) and source.mission_id == "mission-ui-live"
    assert isinstance(source.store, ReadOnlyMissionStore)
    frame = compose_frame(source)
    assert "mission-ui-live" in frame and "NOT AUTHORIZED — plan approval required" in frame
    assert "->" not in frame
    # The projection the TUI polls is the same read-only handle.
    assert isinstance(source.projection, MissionProjection)
    assert MissionProjection(source.store).snapshot("mission-ui-live").mission.approved_plan_revision is None


def test_unknown_mission_and_missing_replay_fail_closed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    SQLiteMissionStore(state / "missions.sqlite3")
    assert handle(build_parser().parse_args(["ui", "--state-dir", str(state), "--once"])) == 2
    assert "no active mission" in capsys.readouterr().err
    assert handle(build_parser().parse_args(["ui", "--replay", str(tmp_path / "nope.json"), "--once"])) == 2
    assert "no replay" in capsys.readouterr().err
