# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""The r row: shown wherever a came-back leaf's offers are, r takes it (else runs the leaf again),
the precheck mark and its line, and the record's line for a reopen after landing."""

from test_plan_cli import person, repo  # noqa: F401  (fixtures)
from test_tui import proposed, watch

from graphene_map import node_record as NR
from graphene_map import plan
from graphene_map.store import Store
from graphene_map.tui import Watch

R_ARGV = ["plan", "first", "auto"]  # a harmless command standing for `node reopen`
STAND_IN = [("r", "reopen schema: the landed fix was wrong", R_ARGV)]


def came_back(repo):
    proposed(repo)
    person("plan", "accept")
    with Store.open(repo) as store:
        bot = plan.Caller("claude:aaaa1111", False, "aaaa1111-session")
        plan.start(store, "schema", bot, repo)
        plan.release(store, "schema", bot, "it needs a rework")


def test_the_r_row_shows_in_the_record_pane_the_offers_field_and_the_keys(repo, monkeypatch):
    came_back(repo)
    monkeypatch.setattr(plan, "offers", lambda store, node: STAND_IN if node.id == "schema" else [])
    seen, _ = watch(repo, ["G"], size=(120, 36))
    assert "r  reopen schema: the landed fix was wrong" in seen["detail"]
    assert "graphene plan first auto" in seen["detail"]
    assert "r reopen" in seen["status"] and "r run it again" not in seen["status"]
    seen, _ = watch(repo, ["G", "enter"], size=(120, 36))
    assert "offers" in seen["detail"] and "r  reopen schema" in " ".join(seen["detail"].split()).replace("r reopen", "r  reopen")


def test_r_takes_the_offer_when_there_is_one_and_runs_the_leaf_again_when_not(repo, monkeypatch):
    came_back(repo)
    ran = []
    monkeypatch.setattr(Watch, "background", lambda self, argv: ran.append(argv))
    monkeypatch.setattr(plan, "offers", lambda store, node: STAND_IN if node.id == "schema" else [])
    seen, _ = watch(repo, ["G", "r"])
    assert "graphene plan first auto" in seen["status"] and not ran
    monkeypatch.setattr(plan, "offers", lambda store, node: [])
    seen, _ = watch(repo, ["G", "r"])
    assert ran and ran[0][0] == "run" and ran[0][-2:] == ["--node", "schema"]
    seen, _ = watch(repo, ["G"])
    assert "r run it again" in seen["status"] and "r reopen" not in seen["status"]


def precheck(repo, node_id, **detail):
    with Store.open(repo) as store:
        rev = plan.get(store, node_id).rev
        mine = {"rev": rev, "check": "true", "base": "abcdef0123456789", "exit": 0, **detail}
        store.log_node(node_id, "2026-01-05T01:00:00.000Z", "precheck", "graphene", detail=mine)


def test_a_check_that_passes_at_the_base_is_marked_and_said(repo):
    proposed(repo)
    precheck(repo, "schema", verdict="passes", why="exit 0")
    seen, _ = watch(repo, ["G"], size=(120, 36))
    said = " ".join(seen["detail"].split())
    assert "its check passes at the base commit abcdef0, so it proves nothing: e edits the check" in said
    assert any("schema" in row and "∅" in row for row in seen["tree"])
    assert not any("∅" in row for row in seen["tree"] if "ids" in row)


def test_a_check_naming_paths_outside_its_scope_is_marked_and_said(repo):
    proposed(repo)
    precheck(repo, "schema", verdict="outside", why="x", paths=["a.py", "b.py"])
    seen, _ = watch(repo, ["G"], size=(120, 36))
    assert "its check names a.py, b.py outside its scope, at abcdef0" in " ".join(seen["detail"].split())
    assert any("schema" in row and "∅" in row for row in seen["tree"])


def test_a_red_or_stale_precheck_is_not_marked(repo):
    proposed(repo)
    precheck(repo, "schema", verdict="red", why="exit 1")
    precheck(repo, "ids", verdict="passes", why="exit 0", rev=99)
    seen, _ = watch(repo, ["G"], size=(120, 36))
    assert not any("∅" in row for row in seen["tree"]) and "proves nothing" not in seen["detail"]


def log(*kinds):
    return [{"timestamp": f"t{i}", "kind": k, "actor": "alex", "detail": {"note": "wrong"}}
            for i, k in enumerate(kinds)]  # fmt: skip


def test_a_reopen_after_landing_says_the_fix_is_a_new_commit():
    said = [a.said for a in NR._acts(log("landed", "reopened"))]
    assert said == ["wrong (reopened after landing; the fix is a new commit)"]
    assert [a.said for a in NR._acts(log("finished", "reopened"))] == ["wrong"]
