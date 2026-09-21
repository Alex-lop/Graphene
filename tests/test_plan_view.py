"""The plan as the page draws it: every position computed in Python, and final the moment it is drawn."""

import subprocess

import pytest

from graphene_debrief import plan
from graphene_debrief.plan_view import HOLES, NODE_H, NODE_W, build_plan_view
from graphene_debrief.store import Store

ALEX = plan.Caller("alex", True)
BOT = plan.Caller("claude:aaaa1111", False, "aaaa1111-session")


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    for name, text in {"src/api/users.py": "x = 1\n", "README.md": "# toy\n"}.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    for key, value in (("user.email", "t@example.com"), ("user.name", "T")):
        subprocess.run(["git", "-C", str(tmp_path), "config", key, value], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "start"], check=True, capture_output=True)
    return tmp_path


@pytest.fixture
def store(repo):
    with Store.open(repo) as s:
        yield s


def node(node_id, **extra):
    return {"id": node_id, "title": node_id, "scope": ["src/**"], "check": "true", **extra}


def boxes(view):
    return [(n["x"], n["y"], n["width"], n["height"]) for n in view["nodes"]]


def overlapping(view):
    out = []
    for i, a in enumerate(boxes(view)):
        for b in boxes(view)[i + 1 :]:
            apart = a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]
            if not apart:
                out.append((a, b))
    return out


# -- the layout -----------------------------------------------------------------------------------


def test_a_column_is_the_longest_path_to_a_node_and_a_lane_is_an_owner(store):
    plan.propose(store, [node("a"), node("b", needs=["a"]), node("c", needs=["a", "b"])], ALEX)
    plan.propose(store, [node("mine", owner="alex")], ALEX)
    view = build_plan_view(store)
    columns = {n["id"]: n["column"] for n in view["nodes"]}
    assert columns == {"a": 0, "b": 1, "c": 2, "mine": 0}  # c waits on b, not only on a
    assert [lane["id"] for lane in view["lanes"]] == ["agent", "alex"]  # the agents' lane first
    assert {n["id"]: n["lane"] for n in view["nodes"]}["mine"] == "alex"
    assert all(n["x"] == n["column"] * (NODE_W + 40) for n in view["nodes"])


def test_the_layout_is_deterministic_and_no_two_boxes_overlap(store):
    plan.propose(store, [node("a"), node("b"), node("c", needs=["a"]), node("d", owner="alex")], ALEX)
    first, second = build_plan_view(store), build_plan_view(store)
    assert first["nodes"] == second["nodes"] and first["lanes"] == second["lanes"]
    assert overlapping(first) == []
    assert first["width"] > 0 and first["height"] > 0


def test_an_edge_runs_from_the_right_of_its_source_to_the_left_of_its_target(store):
    plan.propose(store, [node("a"), node("b", needs=["a"])], ALEX)
    view = build_plan_view(store)
    at = {n["id"]: n for n in view["nodes"]}
    [edge] = view["edges"]
    assert (edge["source"], edge["target"]) == ("a", "b")
    assert edge["points"][0] == [at["a"]["x"] + NODE_W, at["a"]["y"] + NODE_H / 2]
    assert edge["points"][-1] == [at["b"]["x"], at["b"]["y"] + NODE_H / 2]
    assert all(point[0] >= edge["points"][0][0] for point in edge["points"])


def test_fifty_nodes_lay_out_without_overlapping(store):
    chain = [node("n0")] + [node(f"n{i}", needs=[f"n{i - 1}"]) for i in range(1, 25)]
    chain += [node(f"m{i}", needs=["n0"], owner="alex") for i in range(25)]
    plan.propose(store, chain, ALEX)
    view = build_plan_view(store)
    assert len(view["nodes"]) == 50 and overlapping(view) == []
    assert max(n["column"] for n in view["nodes"]) == 24


def test_adding_a_node_moves_no_column_unless_its_depth_changed(store):
    plan.propose(store, [node("a"), node("b", needs=["a"]), node("c")], ALEX)
    before = {n["id"]: n["column"] for n in build_plan_view(store)["nodes"]}
    plan.propose(store, [node("d", needs=["b"])], ALEX)
    plan.edit(store, "c", {"needs": ["b"]}, ALEX)  # c's own depth changed: it is allowed to move
    after = {n["id"]: n["column"] for n in build_plan_view(store)["nodes"]}
    assert {k: v for k, v in after.items() if k in ("a", "b")} == {"a": before["a"], "b": before["b"]}
    assert after["c"] == 2 and after["d"] == 2


# -- the tree ---------------------------------------------------------------------------------------


def test_the_page_carries_the_goal_the_tree_and_every_nodes_why(store):
    plan.set_goal(store, "people can sign in", ALEX)
    plan.propose(
        store,
        [
            node(
                "top",
                scope=[],
                check=None,
                goal="an endpoint they can call",
                children=[node("a"), node("b")],
            )
        ],
        ALEX,
    )
    view = build_plan_view(store)
    at = {n["id"]: n for n in view["nodes"]}
    assert view["goal"] == "people can sign in"
    assert [n["id"] for n in view["nodes"]] == ["top", "a", "b"]  # a parent before its children
    assert (at["top"]["depth"], at["a"]["depth"]) == (0, 1)
    assert at["a"]["parent"] == "top" and at["top"]["parent"] is None
    assert at["top"]["sub_goal"] and not at["a"]["sub_goal"]
    assert at["top"]["display_state"] == "sub-goal"  # nobody takes it; its children are the work
    assert (at["top"]["leaves_done"], at["top"]["leaves_total"]) == (0, 2)
    assert at["a"]["why"] == ["people can sign in", "top (top): an endpoint they can call"]
    assert at["top"]["why"] == ["people can sign in"] and not at["a"]["aside"]


def test_a_sub_goal_counts_the_leaves_beneath_it_as_they_finish(store, repo, finish):
    plan.propose(store, [node("top", scope=[], check=None, children=[node("a"), node("b")])], ALEX)
    plan.start(store, "a", BOT, repo)
    finish(store, repo, "a", BOT)
    at = {n["id"]: n for n in build_plan_view(store)["nodes"]}
    assert (at["top"]["leaves_done"], at["top"]["leaves_total"]) == (1, 2)


# -- what the page says about a node ---------------------------------------------------------------


def test_an_open_node_with_something_left_to_wait_on_reads_as_waiting(store):
    plan.propose(store, [node("a", owner="alex"), node("b", needs=["a"])], ALEX)
    at = {n["id"]: n for n in build_plan_view(store)["nodes"]}
    assert at["a"]["display_state"] == "ready" and at["b"]["display_state"] == "waiting"
    assert "a" in " ".join(at["b"]["waits"]) and "alex" in " ".join(at["b"]["waits"])
    assert at["a"]["waits"] == []  # it is the person's own node, and it is theirs to do now


def test_a_running_node_carries_who_holds_it_since_when_and_its_log(store, repo):
    plan.propose(store, [node("a")], ALEX)
    plan.start(store, "a", BOT, repo)
    [shown] = build_plan_view(store)["nodes"]
    assert shown["state"] == "running" and shown["display_state"] == "running"
    assert shown["executor"] == BOT.name and shown["started_at"]
    assert [entry["kind"] for entry in shown["log"]] == ["added", "started"]
    assert shown["log"][0]["actor"] == "alex"


def test_the_top_of_the_view_says_what_waits_on_the_person(store, monkeypatch, repo, finish):
    monkeypatch.setenv("GRAPHENE_PERSON", "alex")
    plan.propose(
        store, [node("a", signoff=True), node("mine", owner="alex"), node("bobs", owner="bob")], ALEX
    )
    plan.propose(store, [node("asked")], BOT)  # a proposal nobody has accepted
    plan.start(store, "a", BOT, store.path.parent.parent)
    finish(store, repo, "a", BOT)
    view = build_plan_view(store)
    waiting = {item["id"]: item["why"] for item in view["waiting_on_person"]}
    assert set(waiting) == {"a", "mine", "asked"}  # bob's node waits on bob, not on the person looking
    assert "sign" in waiting["a"] and "accept" in waiting["asked"] and waiting["mine"] == "yours to do"
    assert view["counts"]["review"] == 1 and view["counts"]["proposed"] == 1
    assert view["paused"] is False
    assert view["forecast"]["runs"] == []  # a node in review has been reached: it waits for the person
    assert [w["id"] for w in view["forecast"]["waits"]] == ["a", "mine", "bobs", "asked"]


def test_archived_nodes_are_not_drawn_and_a_finished_plan_says_it_is_still_in_force(store, repo, finish):
    plan.propose(store, [node("a")], ALEX)
    plan.start(store, "a", BOT, repo)
    finish(store, repo, "a", BOT)
    view = build_plan_view(store, checkout=repo)
    assert view["all_done"] and view["loose"] == []
    (repo / "loose.txt").write_text("after hours")
    assert build_plan_view(store, checkout=repo)["loose"] == ["loose.txt"]
    plan.archive(store, ALEX)
    view = build_plan_view(store, checkout=repo)
    assert view["nodes"] == [] and not view["all_done"]


def test_a_finished_nodes_log_says_what_had_changed(store, repo):
    plan.propose(store, [node("a", scope=["README.md"])], ALEX)
    plan.start(store, "a", BOT, repo)
    (repo / "README.md").write_text("# done\n")
    plan.finish(store, "a", BOT)
    [shown] = build_plan_view(store)["nodes"]
    assert shown["log"][-1] == {**shown["log"][-1], "kind": "finished", "said": "changed: README.md"}


def test_every_hole_a_control_has_is_printed_with_it(store, repo):
    view = build_plan_view(store)
    assert view["repo"] == repo.name  # the page can name the repo before any session is recorded
    assert set(view["holes"]) == {"scope", "check", "stop", "person"}
    assert all(sentence and sentence[-1] == "." for sentence in view["holes"].values())
    assert view["holes"] == HOLES and view["nodes"] == [] and view["lanes"] == []
