"""The map's contract: positions are computed in Python, final once drawn, and every mark is a record."""

import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from graphene_map.graph import BREAK, CAPTION, MARK_CAP, build_graph, to_json
from graphene_map.model import Agent, Commit, Prompt, Session, ToolEvent
from graphene_map.record import seconds
from graphene_map.store import Store

SID = "aaaaaaaa-0000-4000-8000-000000000000"
ROOT = "/home/dev/project"
GRADES = {"edit", "shell", "commit", "window", "unknown", "record"}


def ts(minute: int, second: int = 0) -> str:
    return f"2026-03-02T09:{minute:02d}:{second:02d}.000Z"


def edit(event_id: str, stamp: str, path: str, agent: str | None = None) -> ToolEvent:
    return ToolEvent(
        event_id, SID, "p1", stamp, "Edit", {"file_path": f"{ROOT}/{path}"}, {}, True, agent, path
    )


def bash(event_id: str, stamp: str, command: str, agent: str | None = None, ok: bool = True) -> ToolEvent:
    response = {"stdout": "ok"} if ok else "Error: Exit code 1"
    return ToolEvent(event_id, SID, "p1", stamp, "Bash", {"command": command}, response, ok, agent)


@pytest.fixture
def store(tmp_path):
    """One main agent and one subagent: an edit each on one file, a check that fails then passes,
    the subagent's commit (one file it never wrote), a long idle gap, then a commit nobody made."""
    with Store.open(tmp_path) as st:
        st.upsert_session(Session(SID, ROOT, ts(0), ts(40), source="backfill"))
        st.add_prompt(Prompt("p1", SID, 1, ts(0, 5), "write the guide"))
        st.add_event(ToolEvent("c1", SID, "p1", ts(1), "Agent", {"description": "guide"}, {"agentId": "a1"}))
        st.upsert_agent(
            Agent("a1", SID, parent_tool_use_id="c1", task="guide", started_at=ts(1, 5), ended_at=ts(6))
        )
        for event in (
            edit("e1", ts(2), "docs/guide.md", "a1"),
            edit("e2", ts(2, 3), "docs/guide.md", "a1"),
            edit("e3", ts(3), "docs/guide.md"),
            bash("b1", ts(4), "uv run pytest -q", "a1", ok=False),
            bash("b2", ts(5), "uv run pytest -q", "a1"),
            bash("k1", ts(5, 30), "git commit -q -m guide && git log --oneline -1", "a1"),
        ):
            st.add_event(event)
        files = [("docs/guide.md", "M"), ("app/gen.py", "A")]
        st.add_commit(Commit("a" * 40, ts(5, 31), "guide", SID, "a1", "k1", files=files))
        st.add_commit(Commit("f" * 40, ts(30), "stray", files=[("pyproject.toml", "M")]))
        yield st


def marks_of(graph, kind):
    return [m for m in graph.marks if m.kind == kind]


def test_an_idle_gap_becomes_a_fixed_width_break_that_keeps_its_real_duration(store):
    graph = build_graph(store, [SID])
    (gap,) = graph.axis["breaks"]
    assert gap["seconds"] == seconds(ts(30)) - seconds(ts(6)) and gap["x1"] - gap["x0"] == BREAK
    assert graph.axis["width"] == 6 * 60 + BREAK and graph.caption == CAPTION


def test_lanes_and_rows_have_their_own_origin_and_appear_in_order(store):
    graph = build_graph(store, [SID])
    assert [(lane.kind, lane.y) for lane in graph.lanes] == [
        ("main", 0.0),
        ("agent", 28.0),
        ("unknown", 56.0),
    ]
    folders = [(r.path, r.y, r.extra) for r in graph.rows if r.kind == "dir"]
    assert folders == [("docs", 0.0, 22.0), ("app", 22.0, 22.0), (".", 44.0, 22.0)]
    assert all(r.y == next(d.y for d in graph.rows if d.id == r.dir) for r in graph.rows if r.kind == "file")


def test_marks_at_one_x_merge_with_a_count_but_two_agents_stay_two_marks(store):
    graph = build_graph(store, [SID])
    changes = [(m.agent.split(":")[-1], m.count, m.grade) for m in marks_of(graph, "change")]
    assert changes == [("a1", 2, "edit"), ("main", 1, "edit")]
    guide = next(r for r in graph.rows if r.id == "file:docs/guide.md")
    assert guide.collision and guide.agents == [f"lane:{SID[:8]}:a1", f"lane:{SID[:8]}:main"]
    assert graph.counters["collisions"] == 1


def test_coverage_is_three_counts_and_a_path_with_no_write_is_drawn_at_its_commit(store):
    graph = build_graph(store, [SID])
    cov = graph.coverage
    assert (cov["committed_files"], cov["write"], cov["commit"], cov["nothing"], cov["window"]) == (
        3,
        1,
        1,
        1,
        1,
    )
    assert cov["paths"] == {"commit": ["app/gen.py"], "nothing": ["pyproject.toml"]}
    evidence = {(m.at, m.grade, m.agent) for m in marks_of(graph, "evidence")}
    assert evidence == {
        ("file:app/gen.py", "commit", f"lane:{SID[:8]}:a1"),
        ("file:pyproject.toml", "window", "lane:unknown"),
    }


def test_a_check_that_failed_and_was_rerun_green_is_counted_and_linked(store):
    graph = build_graph(store, [SID])
    assert [(m.ok, m.label) for m in marks_of(graph, "check")] == [
        (False, "uv run pytest -q"),
        (True, "uv run pytest -q"),
    ]
    assert (graph.counters["failed_checks"], graph.counters["rerun_green"]) == (1, 1)
    kinds = {link.kind for link in graph.links}
    assert kinds == {"spawned", "returned", "touched", "committed-in", "ran"}
    spawned = next(link for link in graph.links if link.kind == "spawned")
    assert spawned.source.startswith("spawn:") and spawned.target == f"lane:{SID[:8]}:a1"


def test_a_change_list_the_vendor_marks_as_shared_never_makes_a_collision(tmp_path):
    """Two agents, 376 ms apart, each with a list flagged `shared`: the vendor itself says either list
    may belong to the other's command, so neither proves a second writer."""
    diff = {"changedFiles": [f"{ROOT}/notes.md"], "files": [], "moreFiles": 0, "shared": True}
    calls = (("s1", "2026-03-02T09:01:00.000Z", "a1"), ("s2", "2026-03-02T09:01:00.376Z", None))
    with Store.open(tmp_path) as st:
        st.upsert_session(Session(SID, ROOT, ts(0), ts(9), source="backfill"))
        for event_id, stamp, agent in calls:
            call = ToolEvent(
                event_id, SID, None, stamp, "Bash", {"command": "make notes"}, {"bashEditDiff": diff}
            )
            call.agent_id = agent
            st.add_event(call)
        graph = build_graph(st, [SID])
    assert [m.shared for m in marks_of(graph, "change")] == [True, True]  # drawn, and flagged
    assert graph.counters["collisions"] == 0 and not any(r.collision for r in graph.rows)
    assert "never counted" in graph.rules["collision"]


def assert_every_mark_and_link_is_a_record(graph):
    ids = {lane.id for lane in graph.lanes} | {row.id for row in graph.rows} | {m.id for m in graph.marks}
    for mark in graph.marks:
        assert mark.grade in GRADES and mark.ref and mark.count >= 1 and mark.at in ids
        assert isinstance(mark.x, float) and isinstance(mark.y, float)
    for link in graph.links:
        assert link.grade in GRADES and link.ref and link.source in ids and link.target in ids
    assert sum(m.count for m in graph.marks) == graph.omitted["records"]
    assert graph.omitted["merged_into_counts"] == graph.omitted["records"] - len(graph.marks)
    json.dumps(asdict(graph))


def assert_no_jitter(store, session_ids):
    """For every prefix of the run in time order, a mark that is drawn is there in every longer
    prefix with the same x and the same (collapsed) y, and so is every lane and row."""
    full = build_graph(store, session_ids)
    stamps = {m.t for m in full.marks} | {lane.t0 for lane in full.lanes} | {lane.t1 for lane in full.lanes}
    drawn: dict[str, tuple] = {}
    for stamp in sorted(stamps, key=seconds):
        graph = build_graph(store, session_ids, until=stamp)
        now = {m.id: (m.x, m.y) for m in graph.marks}
        now |= {lane.id: (lane.x0, lane.y, lane.dy) for lane in graph.lanes}
        now |= {row.id: (row.y, row.dy) for row in graph.rows}
        now |= {f"tick:{n}": (tick["x"], tick["t"]) for n, tick in enumerate(graph.axis["ticks"])}
        moved = {key: (was, now.get(key)) for key, was in drawn.items() if now.get(key) != was}
        assert moved == {}, f"at {stamp}"
        drawn = now
    everything = {m.id for m in full.marks} | {x.id for x in full.lanes} | {r.id for r in full.rows}
    assert {key for key in drawn if not key.startswith("tick:")} == everything
    return len(stamps)


def test_every_mark_and_link_has_a_grade_and_a_record(store):
    assert_every_mark_and_link_is_a_record(build_graph(store, [SID]))


def test_no_mark_lane_or_row_moves_as_the_run_grows(store):
    assert assert_no_jitter(store, [SID]) >= 9


def test_past_the_cap_marks_merge_further_and_the_omitted_counts_agree_with_the_data(tmp_path):
    start = datetime(2026, 3, 2, 9, tzinfo=UTC)
    with Store.open(tmp_path) as st:
        st.upsert_session(Session(SID, ROOT, ts(0), source="backfill"))
        with st.transaction():
            for n in range(4 * MARK_CAP):  # one call every 15 s on alternating files: no two share a bucket
                stamp = (start + timedelta(seconds=15 * n)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                st.add_event(edit(f"e{n}", stamp, f"src/f{n % 2}.py"))
        graph = build_graph(st, [SID])
    assert graph.axis["bucket"] > 10 and len(graph.marks) <= MARK_CAP
    assert_every_mark_and_link_is_a_record(graph)
    assert sum(m.count for m in marks_of(graph, "change")) == 4 * MARK_CAP


# -- the synthetic run: tests/fixtures/make_run_fixture.py ----------------------------------------

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import make_run_fixture as run  # noqa: E402

GOLDEN = Path(__file__).parent / "fixtures" / "run_graph.json"


@pytest.fixture
def run_store(tmp_path):
    with Store.open(tmp_path) as st:
        run.load(st)
        yield st


def test_the_golden_graph_of_the_synthetic_run_is_pinned(run_store):
    assert to_json(build_graph(run_store, [run.S1]), indent=1) + "\n" == GOLDEN.read_text(encoding="utf-8")


def test_the_synthetic_run_draws_what_its_ground_truth_says(run_store):
    graph = build_graph(run_store, [run.S1])
    assert_every_mark_and_link_is_a_record(graph)
    want = run.expected()["coverage"][run.S1]
    assert {key: graph.coverage[key] for key in want} == want
    assert graph.coverage["paths"] == {
        "commit": ["app/gen_a.py", "app/gen_b.py"],
        "nothing": ["pyproject.toml"],
    }
    kinds = [lane.kind for lane in graph.lanes]
    assert (kinds.count("main"), kinds.count("group"), kinds.count("agent"), kinds.count("unknown")) == (
        1,
        1,
        8,
        1,
    )
    group = next(lane for lane in graph.lanes if lane.kind == "group")
    assert group.members == 6 and {lane.phase for lane in graph.lanes if lane.group == group.id} == {
        "Build",
        "Verify",
    }
    picked = next(m for m in marks_of(graph, "commit") if m.ref == f"commit:{run.SHAS['cp']}")
    assert picked.label.endswith(f"(cherry-pick of {run.SHAS['w3'][:7]})")
    assert (
        picked.committed == "2026-03-02T09:16:00.000Z" and picked.t <= picked.committed
    )  # git's time, the call's
    assert (
        picked.at.endswith(":main") and picked.agent != picked.at
    )  # run by main, credited to its origin's agent
    assert [r.path for r in graph.rows if r.collision and r.kind == "file"] == ["app/util.py"]
    assert {m.at for m in graph.marks if m.copy} == {
        "file:app/api.py",
        "file:app/cli.py",
        "file:tests/test_api.py",
    }
    assert {m.at for m in graph.marks if m.shared} == {"file:app/core.py"}
    assert graph.omitted["vendor_more_files"] == 2 and len(graph.tasks) == 3
    assert graph.counters == {
        "failed_checks": 1,
        "rerun_green": 1,
        "refused": 1,
        "failures": 0,
        "outside": 1,
        "collisions": 1,
    }
    assert [b["seconds"] for b in graph.axis["breaks"]] == [830.0, 180.0]


def test_marks_come_out_in_the_order_the_page_draws_and_culls_them(run_store):
    """x order, because the page finds what is on screen by bisecting on it, and a step under the
    mark at the same place that says more, because the page draws in this order and the last drawn
    takes the click."""
    graph = build_graph(run_store, [run.S1])
    assert [m.x for m in graph.marks] == sorted(m.x for m in graph.marks)
    where = [(m.at, m.x) for m in graph.marks]
    covered = 0
    for i, mark in enumerate(graph.marks):
        if mark.kind != "commit":
            continue
        steps = [j for j, place in enumerate(where) if place == where[i] and graph.marks[j].kind == "step"]
        covered += len(steps)
        assert all(j < i for j in steps), f"a step is drawn over {mark.id}"
    assert covered == 8  # the git-commit call of every commit an agent is recorded making


def test_two_sessions_share_one_axis_and_their_common_file_collides(run_store):
    graph = build_graph(run_store, [run.S1, run.S2])
    assert [r.path for r in graph.rows if r.collision and r.kind == "file"] == ["app/util.py", "app/api.py"]
    assert len({lane.session for lane in graph.lanes if lane.kind == "main"}) == 2
    assert_every_mark_and_link_is_a_record(graph)


@pytest.mark.parametrize("sessions", [[run.S1], [run.S1, run.S2]])
def test_no_mark_lane_or_row_of_the_synthetic_run_moves_as_it_grows(run_store, sessions):
    assert assert_no_jitter(run_store, sessions) > 40


if __name__ == "__main__":  # regenerate the golden graph after a deliberate change to the contract
    import tempfile

    with Store.open(Path(tempfile.mkdtemp())) as s:
        run.load(s)
        GOLDEN.write_text(to_json(build_graph(s, [run.S1]), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {GOLDEN}")
