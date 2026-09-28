"""The plan as the page draws it: every position computed in Python, and final the moment it is drawn."""

import subprocess

import pytest

from graphene_map import plan
from graphene_map.plan_view import HOLES, NODE_H, NODE_W, build_plan_view
from graphene_map.store import Store

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


def through(edge, box):
    """Whether any straight piece of an edge runs inside a box (its edges excluded)."""
    x, y, w, h = box
    pieces = zip(edge["points"], edge["points"][1:], strict=False)
    return any(
        min(a[0], b[0]) < x + w and max(a[0], b[0]) > x and min(a[1], b[1]) < y + h and max(a[1], b[1]) > y
        for a, b in pieces
    )


def test_no_edge_runs_through_a_box_even_one_that_skips_a_column(store):
    plan.propose(store, [node("a"), node("b", needs=["a"]), node("c", needs=["a", "b"])], ALEX)
    plan.propose(store, [node("x"), node("y"), node("z", needs=["x"]), node("w", needs=["z", "y"])], ALEX)
    plan.propose(store, [node("p", owner="alex"), node("q", needs=["p", "c"])], ALEX)
    view = build_plan_view(store)
    at = {n["id"]: (n["x"], n["y"], n["width"], n["height"]) for n in view["nodes"]}
    assert "a>c" in {e["id"] for e in view["edges"]} and at["a"][1] == at["b"][1] == at["c"][1]  # one row
    crossed = [(e["id"], i) for e in view["edges"] for i, box in at.items()
               if i not in (e["source"], e["target"]) and through(e, box)]  # fmt: skip
    assert crossed == []


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


def tree_boxes(view):
    return [(n["tree_x"], n["tree_y"], n["width"], n["height"]) for n in view["nodes"]]


def sub(node_id, *children):
    return node(node_id, scope=[], check=None, children=list(children))


def test_the_top_down_tree_is_deterministic_no_two_boxes_touch_and_a_parent_is_centred_over_its_children(
    store,
):
    plan.set_goal(store, "feeds load", ALEX)
    plan.propose(
        store,
        [
            sub("readers", node("csv"), sub("xml", node("parse"), node("wire"), node("map")), node("json")),
            node("alone"),
            sub("proof", node("e2e", needs=["readers"])),
        ],
        ALEX,
    )
    first, second = build_plan_view(store), build_plan_view(store)
    assert first["nodes"] == second["nodes"] and first["tree_links"] == second["tree_links"]
    at = {n["id"]: n for n in first["nodes"]}
    tree = {**first, "nodes": [{**n, "x": n["tree_x"], "y": n["tree_y"]} for n in first["nodes"]]}
    assert overlapping(tree) == []
    for parent in ("readers", "xml", "proof"):
        kids = [n for n in first["nodes"] if n["parent"] == parent]
        assert at[parent]["tree_x"] == (kids[0]["tree_x"] + kids[-1]["tree_x"]) / 2
        assert all(k["tree_y"] >= at[parent]["tree_y"] + NODE_H + 40 for k in kids)  # below it, clear of it
    tops = [n for n in first["nodes"] if n["depth"] == 0]
    assert first["tree_goal"] == [(tops[0]["tree_x"] + tops[-1]["tree_x"]) / 2, 0.0]  # the goal on top
    assert min(n["tree_y"] for n in first["nodes"]) > NODE_H
    leaves = [n["id"] for n in sorted(first["nodes"], key=lambda n: n["tree_x"]) if not n["sub_goal"]]
    assert leaves == ["csv", "parse", "wire", "map", "json", "alone", "e2e"]  # outline order, left to right
    links = {(link["source"], link["target"]) for link in first["tree_links"]}
    assert links == {("", "readers"), ("", "alone"), ("", "proof")} | {
        (n["parent"], n["id"]) for n in first["nodes"] if n["parent"]
    }
    wire = next(link for link in first["tree_links"] if link["target"] == "wire")
    assert wire["points"][0] == [at["xml"]["tree_x"] + NODE_W / 2, at["xml"]["tree_y"] + NODE_H]
    assert wire["points"][-1] == [at["wire"]["tree_x"] + NODE_W / 2, at["wire"]["tree_y"]]
    assert first["tree_width"] == max(n["tree_x"] for n in first["nodes"]) + NODE_W
    assert first["tree_height"] == max(n["tree_y"] for n in first["nodes"]) + NODE_H


def test_the_critical_path_on_a_diamond_is_the_longest_chain_and_a_tie_goes_to_the_plans_order(store):
    plan.propose(
        store, [node("a"), node("b", needs=["a"]), node("c", needs=["a"]), node("d", needs=["b", "c"])], ALEX
    )
    view = build_plan_view(store)
    assert view["critical"] == ["a", "b", "d"]
    assert {e["id"] for e in view["edges"] if e["critical"]} == {"a>b", "b>d"}
    assert view["ready"] == ["a"]  # the one leaf that can start now


def test_the_critical_path_through_a_chain_leaves_out_what_is_done_and_follows_a_need_on_a_sub_goal(
    store, repo, finish
):
    plan.propose(
        store,
        [node("a"), node("b", needs=["a"]), sub("top", node("c"), node("d", needs=["c"])), node("e")],
        ALEX,
    )
    plan.edit(store, "top", {"needs": ["b"]}, ALEX)  # everything under top waits on b
    view = build_plan_view(store)
    assert view["critical"] == ["a", "b", "c", "d"]
    assert {e["id"] for e in view["edges"] if e["critical"]} == {"a>b", "b>top", "c>d"}
    plan.start(store, "a", BOT, repo)
    finish(store, repo, "a", BOT)
    view = build_plan_view(store)
    assert view["critical"] == ["b", "c", "d"] and view["ready"] == ["b", "e"]


def test_with_nothing_waiting_on_anything_there_is_no_critical_path(store):
    plan.propose(store, [node("a"), node("b")], ALEX)
    view = build_plan_view(store)
    assert view["critical"] == [] and not any(e["critical"] for e in view["edges"])


# -- what the page says about a node ---------------------------------------------------------------


def test_an_open_node_with_something_left_to_wait_on_reads_as_waiting(store):
    plan.propose(store, [node("a", owner="alex"), node("b", needs=["a"])], ALEX)
    at = {n["id"]: n for n in build_plan_view(store)["nodes"]}
    assert at["a"]["display_state"] == "ready" and at["b"]["display_state"] == "waiting"
    assert "a" in " ".join(at["b"]["waits"]) and "alex" in " ".join(at["b"]["waits"])
    assert at["a"]["waits"] == []  # it is the person's own node, and it is theirs to do now


def test_a_leaf_its_executor_handed_back_came_back_and_waits_on_the_person(store, repo, monkeypatch):
    """Decision 42: the terminal reads it `came back`, in the colour of what waits on you."""
    monkeypatch.setenv("GRAPHENE_PERSON", "alex")
    plan.propose(store, [node("a"), node("b", needs=["a"])], ALEX)
    plan.start(store, "a", BOT, repo)
    plan.release(store, "a", BOT, "it needs README.md too")
    view = build_plan_view(store)
    at = {n["id"]: n for n in view["nodes"]}
    assert at["a"]["display_state"] == "came back"
    assert at["b"]["waits"] == ["waits on a (a), which came back"]
    assert view["waiting_on_person"] == [{"id": "a", "title": "a", "why": "see why it came back"}]
    plan.edit(store, "a", {"title": "a, again"}, ALEX)  # the person has moved it on: it is ready again
    assert build_plan_view(store)["nodes"][0]["display_state"] == "ready"


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
