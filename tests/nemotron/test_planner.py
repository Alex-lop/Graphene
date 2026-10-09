"""The Nemotron planner, driven by `graphene ask` against the recorded fake: it reads the repository
with tools that only read, answers in a strict JSON schema, prints the fenced plan block, and what it
proposed is in the plan for the person to prune; the bill is in the plan's log."""

import json
import signal

import pytest
from fake_tokenfactory import Fake, call

from graphene_map import board as B
from graphene_map import plan
from graphene_map import plan_text as T
from graphene_map.ask import ask, label, named
from graphene_map.nemotron import planner
from graphene_map.nemotron import tokenfactory as tf
from graphene_map.plan import PROPOSED
from graphene_map.store import Store

ULTRA = "nvidia/Nemotron-3-Ultra-fake"
NOW = "Answer now with the proposal. Write it as JSON."  # the ask for the answer, with no tools
PROPOSAL = """Here is the tree.

```plan
goal: the app greets properly
- the greeting  [greeting]
  ? say hello  [hello]
      greet returns hello
      scope: app.py
      check: python3 -c 'import app; assert app.greet() == "hello"'
```

The README still says hi; I left it."""


def node(id, title, parent=None, mark="?", goal="", scope=(), check=None, needs=()):
    """A node of the JSON answer: every field, as the strict schema has it."""
    return {"id": id, "title": title, "goal": goal, "scope": list(scope), "check": check,
            "needs": list(needs), "parent": parent, "mark": mark}  # fmt: skip


HELLO = node("hello", "say hello", "greeting", goal="greet returns hello", scope=["app.py"],
             check="python3 -c 'import app; assert app.greet() == \"hello\"'")  # fmt: skip
# PROPOSAL, as the JSON the strict schema asks for
ANSWER = {"goal": "the app greets properly", "board": [], "nodes": [node("greeting", "the greeting"), HELLO],
          "says": "The README still says hi; I left it."}  # fmt: skip
WRONG = {**ANSWER, "nodes": [node("greeting", "the greeting"), {**HELLO, "scope": []}]}  # no scope
NO_SCOPE = ("line 3 [hello]: hello: a leaf needs a scope (the paths it may touch), e.g. --scope "
            "'src/api/**'; or give it children, and it is a sub-goal")  # fmt: skip


def answer(p: dict) -> dict:
    return {"content": json.dumps(p)}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@e.com"], ["config", "user.name", "T"]):
        subprocess.run(["git", "-C", str(root), *args], check=True)
    (root / ".gitignore").write_text(".graphene/\n")
    (root / "app.py").write_text('def greet():\n    return "hi"\n')
    (root / "src").mkdir()
    (root / "src" / "deep.py").write_text("# nothing\n")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "start"], check=True)
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def fake(monkeypatch):
    started = []

    def start(replies):
        f = Fake(replies).__enter__()
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        started.append(f)
        return f

    yield start
    for f in started:
        f.__exit__(None, None, None)


def test_it_reads_only_and_what_it_prints_is_proposed_for_the_person(repo, fake):
    f = fake([
        call("list", path="."),
        call("glob", pattern="**/*.py"),
        call("grep", pattern="return", glob="*.py"),
        call("read", path="app.py"),
        call("read", path="../../etc/passwd"),
        call("write", path="app.py", content="gone"),
        {"content": PROPOSAL},
        answer(ANSWER),
    ])  # fmt: skip
    said = []
    with Store.open(repo) as store:
        proposed = ask(store, repo, "make it say hello", named("nemotron"), say=said.append)
        assert any("hello" in line for line in proposed)
        assert plan.get(store, "hello").state == PROPOSED and plan.get(store, "hello").scope == ["app.py"]
        [bill] = store.node_log("*", ("usage",))
        assert bill["actor"] == "planner:nemotron" and bill["detail"]["calls"] == 8  # the strict answer too
        asked = store.node_log("hello", ("proposed",))[-1]
        assert asked["actor"] == "planner:nemotron"
    assert f.requests[0]["model"] == ULTRA  # the largest Nemotron the live list has, by default
    assert [t["function"]["name"] for t in f.requests[0]["tools"]] == ["list", "glob", "grep", "read"]
    results = [m["content"] for m in f.requests[-1]["messages"] if m["role"] == "tool"]
    assert results[0].split("\n") == [".gitignore", "app.py", "src/"]
    assert results[1].split("\n") == ["app.py", "src/deep.py"]
    assert results[2] == 'app.py:2: return "hi"'
    assert results[3].startswith("    1  def greet():")
    assert "not a file of this repository" in results[4]
    assert "there is no tool 'write'" in results[5]
    assert (repo / "app.py").read_text() == 'def greet():\n    return "hi"\n'
    assert any("The README still says hi" in line for line in said)  # what it could not settle


def test_a_tool_call_written_as_text_is_read_as_one_not_as_the_answer(repo, fake):
    """On 7 October Ultra wrote `<tool_call>{…}</tool_call>` in its text, twice in a row, and the planner
    took it for the proposal: "no proposal". It is a call: run it, answer it, and go on."""
    written = '<tool_call>\n{"name": "read", "arguments": {"path": "app.py"}}\n</tool_call>'
    f = fake([{"content": written}, {"content": PROPOSAL}, answer(ANSWER)])
    with Store.open(repo) as store:
        ask(store, repo, "make it say hello", named("nemotron"), say=lambda s: None)
        assert plan.get(store, "hello").state == PROPOSED
    told = f.requests[1]["messages"][-1]
    assert told["role"] == "user" and told["content"].startswith("Result of read:\n    1  def greet():")


def test_out_of_steps_it_is_asked_to_answer_without_tools(repo, fake):
    f = fake([call("list", path=".")] * 2 + [{"content": PROPOSAL}])
    with Store.open(repo) as store:
        ask(store, repo, "make it say hello", named("nemotron --steps 3"), say=lambda s: None)
        assert plan.get(store, "hello").state == PROPOSED  # an answer that is not JSON is read as text
    assert "tools" in f.requests[0] and "tools" not in f.requests[2] and "response_format" in f.requests[2]
    assert f.requests[2]["messages"][-1]["content"] == NOW


def test_the_answer_is_asked_in_a_strict_schema_and_no_tool_step_carries_it(repo, fake):
    f = fake([call("list", path="."), {"content": PROPOSAL}, answer(ANSWER)])
    with Store.open(repo) as store:
        ask(store, repo, "make it say hello", named("nemotron"), say=lambda s: None)
    *steps, last = f.requests
    assert len(steps) == 2 and all("tools" in r and "response_format" not in r for r in steps)
    assert "tools" not in last and last["response_format"]["type"] == "json_schema"
    assert last["response_format"]["json_schema"]["name"] == "proposal"
    assert last["response_format"]["json_schema"]["strict"] is True
    assert last["messages"][-2:] == [{"role": "assistant", "content": PROPOSAL},  # its draft, then the ask
                                     {"role": "user", "content": NOW}]  # fmt: skip


def test_an_answer_cut_off_at_the_token_limit_is_asked_again_with_twice_the_room(repo, fake):
    """A cut-off answer is broken JSON: it is asked again, not read and sent back."""
    cut = {"content": json.dumps(ANSWER)[:40], "_finish": "length"}
    f = fake([{"content": PROPOSAL}, cut, answer(ANSWER)])
    with Store.open(repo) as store:
        ask(store, repo, "make it say hello", named("nemotron"), say=lambda s: None)
        assert plan.get(store, "hello").state == PROPOSED
    assert [r["max_tokens"] for r in f.requests] == [8192, 8192, 16384]
    assert f.requests[2]["messages"][-1]["content"] == NOW  # the same ask, with room


def test_the_schema_is_strict_all_the_way_down():
    objects = []

    def walk(s: dict) -> None:
        if s["type"] == "object":
            assert s["additionalProperties"] is False and s["required"] == list(s["properties"])
            objects.append(s["required"])
            for v in s["properties"].values():
                walk(v)
        elif s["type"] == "array":
            walk(s["items"])
        else:
            assert s["type"] in ("string", ["string", "null"]) and set(s) <= {"type", "enum"}

    walk(planner.FORMAT["json_schema"]["schema"])
    assert objects == [["says", "goal", "nodes", "board"],  # says first, then nodes before what names them
                       ["id", "title", "goal", "scope", "check", "needs", "parent", "mark"],
                       ["kind", "id", "text", "default", "then", "options", "about"],
                       ["text", "then"]]  # fmt: skip
    assert planner.FORMAT["json_schema"]["schema"]["properties"]["board"]["items"]["properties"]["kind"][
        "enum"] == list(B.KINDS)  # fmt: skip


BOARD = {
    "goal": "the app greets,\nand says goodbye",
    "board": [
        {"kind": "question", "id": "bye-word", "text": "what does\nbye say?", "default": "goodbye",
         "then": ["goal bye + It says goodbye."], "about": "bye", "options": [
             {"text": "see you", "then": ["goal bye + It says see you.", "check bye: grep -q see app.py"]}]},
        {"kind": "leave out", "id": "no-flag", "text": "a --name flag", "default": None, "then": [],
         "options": [], "about": None},
    ],
    "nodes": [
        node("words", "the words"),
        node("hello", "say hello", "words", goal="greet returns hello", scope=["app.py"], check="true"),
        node("bye", "say goodbye", "words", goal="bye returns goodbye.\nIn src.",
             scope=["src/deep.py", "docs/my notes/*.md"], check="cd src\ntest -f deep.py", needs=["hello"]),
    ],
    "says": "Two leaves under one sub-goal.",
}  # fmt: skip


def test_the_json_reads_as_the_plan_text_and_lands_field_for_field(repo):
    """Every string but a node's goal is one line in the text, a goal keeps its lines, a check's lines
    run one after another, and a node's parent places it."""
    with Store.open(repo) as store:
        T.apply(store, planner.as_text(BOARD), plan.Caller("planner:nemotron", False), None)
        assert store.meta("goal:proposed") == "the app greets, and says goodbye"
        got = {n.id: (n.title, n.goal, n.scope, n.check, n.needs, n.parent) for n in plan.nodes(store)}
        assert got == {
            "words": ("the words", "", [], None, [], None),
            "hello": ("say hello", "greet returns hello", ["app.py"], "true", [], "words"),
            "bye": ("say goodbye", "bye returns goodbye.\nIn src.", ["src/deep.py", "docs/my notes/*.md"],
                    "cd src; test -f deep.py", ["hello"], "words"),
        }  # fmt: skip
        fields = ("kind", "id", "text", "default", "then", "options", "about")
        assert [{k: it[k] for k in fields} for it in B.items(store)] == [
            {**BOARD["board"][0], "text": "what does bye say?"}, BOARD["board"][1]
        ]  # fmt: skip


def test_a_board_item_whose_id_the_text_cannot_read_gets_one_it_can(repo):
    """Ultra named risks with ids of 33 letters and more; an item's id is a handle nothing names."""
    long = {**BOARD["board"][1], "kind": "risk", "id": "validation-change-breaks-csv-and-json-feeds"}
    with Store.open(repo) as store:
        text = planner.as_text({**BOARD, "board": [long]})
        T.apply(store, text, plan.Caller("planner:nemotron", False), None)
        assert [it["id"] for it in B.items(store)] == ["validation-change-breaks"]


def test_a_json_proposal_lands_through_ask_with_its_board_goal_and_needs(repo, fake):
    fake([call("list", path="."), {"content": "I have read enough."}, answer(BOARD)])
    said = []
    with Store.open(repo) as store:
        ask(store, repo, "greet and say goodbye", named("nemotron"), say=said.append)
        [session] = {r["detail"]["session"] for r in store.node_log("*", ("asked",))}
        assert {r["session_id"] for r in store.node_log(None, ("proposed",))} == {session}  # not the dry run
        proposed = {n.id: n.state for n in plan.nodes(store)}
        assert proposed == dict.fromkeys(("words", "hello", "bye"), PROPOSED)
        assert plan.get(store, "bye").needs == ["hello"] and plan.get(store, "bye").parent == "words"
        assert [it["id"] for it in B.items(store)] == ["bye-word", "no-flag"]
        B.pick(store, "bye-word", 1, plan.Caller("alex", True))
        assert plan.get(store, "bye").check == "grep -q see app.py"
    assert said[-2:] == ["the planner says:", "  Two leaves under one sub-goal."]


def test_a_refused_proposal_goes_back_with_graphenes_words_and_the_second_lands(repo, fake):
    f = fake([{"content": PROPOSAL}, answer(WRONG), answer(ANSWER)])
    said = []
    with Store.open(repo) as store:
        ask(store, repo, "make it say hello", named("nemotron"), say=said.append)
        assert plan.get(store, "hello").state == PROPOSED and plan.get(store, "hello").scope == ["app.py"]
        [bill] = store.node_log("*", ("usage",))
        assert bill["detail"]["calls"] == 3
    assert said[0] == "asking the planner (nemotron)…" and not [s for s in said if "again" in s]  # one start
    lines = "\n".join(f"{k:>5}  {line}" for k, line in enumerate(planner.as_text(WRONG).splitlines(), 1))
    assert "    3  ? say hello  [hello]" in lines
    told = f"Graphene could not read the proposal: {NO_SCOPE}\nIt read your JSON as:\n{lines}\n"
    assert f.requests[2]["messages"][-2:] == [
        {"role": "assistant", "content": json.dumps(WRONG)},
        {"role": "user", "content": told + "Answer again with the whole proposal."},
    ]
    assert bill["detail"]["sent_back"] == [NO_SCOPE]


def test_a_fault_goes_back_twice_at_most_and_the_third_answer_is_the_answer(repo, fake):
    f = fake([{"content": PROPOSAL}, answer(WRONG), answer(WRONG), answer(WRONG)])
    said = []
    with Store.open(repo) as store:
        with pytest.raises(plan.Refused, match="^no proposal; nothing was added") as no:  # one start
            ask(store, repo, "make it say hello", named("nemotron"), say=said.append)
        assert plan.nodes(store) == []
        [bill] = store.node_log("*", ("usage",))
    assert "hello: a leaf needs a scope" in str(no.value) and bill["detail"]["sent_back"] == [NO_SCOPE] * 2
    assert [bool(r.get("response_format")) for r in f.requests] == [False, True, True, True]
    assert said == ["asking the planner (nemotron)…"]  # one start: the planner sent it back itself


GREETING = node("greeting", "the greeting")
BYE = node("bye", "say bye", "greeting", scope=["bye.py"], check="true")


def test_an_answer_with_two_faults_gets_both_in_one_send_back(repo, fake):
    """Last night's misses: Graphene said one fault, and the second answer mended it and kept the other."""
    two = {**ANSWER, "nodes": [*WRONG["nodes"], BYE, {**BYE, "id": "wave", "title": "wave"}]}
    f = fake([{"content": PROPOSAL}, answer(two), answer(ANSWER)])
    with Store.open(repo) as store:
        ask(store, repo, "make it say hello", named("nemotron"), say=lambda s: None)
        assert plan.get(store, "hello").state == PROPOSED
        [bill] = store.node_log("*", ("usage",))
    [sent] = bill["detail"]["sent_back"]
    both = "line 7 [bye]: bye and wave both write bye.py. A path has one leaf that writes it: give it to one"
    assert sent.split("\n") == [f"{both}, and let the other wait on it", NO_SCOPE]
    told = f.requests[2]["messages"][-1]["content"]
    assert told.startswith(f"Graphene could not read the proposal: {sent}\nIt read your JSON as:\n")


def item(kind: str, id: str, then=(), about=None) -> dict:
    """A board item of the JSON answer, with a default."""
    return {"kind": kind, "id": id, "text": id, "default": "yes", "then": list(then), "options": [],
            "about": about}  # fmt: skip


REPAIRS = [  # nodes and a board with a fault that needs no judgement, the line saying its repair, what landed
    ([GREETING, {**HELLO, "needs": ["nope"]}], [], "[hello] needs: 'nope' is not the id of a node; dropped",
     lambda s: plan.get(s, "hello").needs == []),
    ([GREETING, {**HELLO, "needs": ["bye"]}, {**BYE, "needs": ["hello"]}], [],
     "[bye] needs: 'hello' closes a cycle; dropped",
     lambda s: [n.needs for n in plan.nodes(s)] == [[], ["bye"], []]),
    ([GREETING, HELLO], [item("question", "which", ["scope app.py + src/deep.py"])],
     "[which] then: scope app.py + src/deep.py names app.py, a file, not a node; dropped",
     lambda s: B.items(s)[0]["then"] == []),
    ([node("The Greeting", "the greeting"), {**HELLO, "parent": "The Greeting"}], [],
     "[The Greeting] is not an id; it is [greeting] now",
     lambda s: plan.get(s, "hello").parent == "greeting"),
    ([GREETING, {**HELLO, "id": "hello."}], [], "[hello.] is not an id; it is [hello] now",
     lambda s: plan.get(s, "hello").scope == ["app.py"]),  # a branch name cannot end in "."
    ([GREETING, HELLO, {**BYE, "id": ""}], [item("question", "which", ["condition docs/**"], about="")],
     "[] is not an id; it is [node] now",  # and the item, which names no node, is about none still
     lambda s: plan.get(s, "node").title == "say bye" and B.items(s)[0]["about"] is None),
    ([{**HELLO, "parent": "plan"}], [], "[hello] parent: 'plan' is not the id of another node; dropped",
     lambda s: plan.get(s, "hello").parent is None),
    ([GREETING, HELLO], [item("risk", "slow", about="app.py")],
     "[slow] about: app.py names a file, not a node; dropped", lambda s: B.items(s)[0]["about"] is None),
    ([GREETING, HELLO], [{**item("risk", "slow"), "options": [{"text": "cache it", "then": []}]}],
     "[slow] is a risk with options; it is a question now",  # feeds 10 and 17, 9 October: thrice each
     lambda s: [(it["kind"], it["options"][0]["text"]) for it in B.items(s)] == [("question", "cache it")]),
]


@pytest.mark.parametrize("case", REPAIRS)
def test_a_fault_that_needs_no_judgement_is_repaired_and_said_not_sent_back(repo, fake, case):
    nodes, board, repaired, landed = case
    f = fake([{"content": "I have read enough."}, answer({**ANSWER, "nodes": nodes, "board": board})])
    said = []
    with Store.open(repo) as store:
        ask(store, repo, "make it say hello", named("nemotron"), say=said.append)
        assert plan.get(store, "hello").state == PROPOSED and landed(store)
    assert len(f.requests) == 2  # one strict answer: nothing was sent back
    assert said[1:4] == ["the planner says:", f"  {ANSWER['says']}", f"  repaired: {repaired}"]


def test_past_twelve_lines_what_the_planner_says_counts_the_lines_not_shown(repo, fake):
    """Twelve ids with a space are twelve repairs: with the says line, thirteen lines. The last was cut
    with no word."""
    leaves = [node(f"Leaf {k}", f"leaf {k}", scope=[f"f{k}.py"], check="true") for k in range(1, 13)]
    fake([{"content": "I have read enough."}, answer({**ANSWER, "nodes": leaves})])
    said = []
    with Store.open(repo) as store:
        ask(store, repo, "make it say hello", named("nemotron"), say=said.append)
    assert said[-2:] == ["  repaired: [Leaf 11] is not an id; it is [leaf-11] now", "  (and 1 more)"]


def test_a_name_the_text_form_reads_is_no_fault_to_repair(repo, fake):
    """The repairs read an id, a parent: and needs: as the text form reads them back: on one line, with
    no space around, "[greeting]" as greeting, and "hello, none" as hello."""
    bye = {**BYE, "parent": "`greeting`", "needs": ["[hello], none"]}
    spaced = {**ANSWER, "nodes": [node(" greeting", "the greeting"), {**HELLO, "parent": "greeting\n"}, bye]}
    f = fake([{"content": "I have read enough."}, answer(spaced)])
    said = []
    with Store.open(repo) as store:
        ask(store, repo, "make it say hello", named("nemotron"), say=said.append)
        assert plan.get(store, "hello").parent == "greeting" == plan.get(store, "bye").parent
        assert plan.get(store, "bye").needs == ["hello"]
    assert len(f.requests) == 2 and not [line for line in said if "repaired" in line]


def test_a_need_on_the_node_above_goes_back_and_is_not_repaired(repo, fake):
    """report 9, 9 October: a tests leaf under the leaf it tests, and waiting on it. Dropping the need
    made the tested leaf a sub-goal with a scope that no leaf writes; which edge is wrong is the model's."""
    under = node("hello-test", "test hello", "hello", scope=["test_app.py"], check="true", needs=["hello"])
    f = fake([{"content": PROPOSAL}, answer({**ANSWER, "nodes": [*ANSWER["nodes"], under]}), answer(ANSWER)])
    with Store.open(repo) as store:
        ask(store, repo, "make it say hello", named("nemotron"), say=lambda s: None)
        assert plan.get(store, "hello").scope == ["app.py"] and len(plan.nodes(store)) == 2
        [bill] = store.node_log("*", ("usage",))
    assert "the plan has a cycle: hello -> hello-test -> hello" in bill["detail"].get("sent_back", [""])[0]
    assert "needs: hello" in f.requests[2]["messages"][-1]["content"]  # as the model wrote it


def test_two_nodes_each_others_parent_go_back_as_a_cycle_and_the_repairs_end(repo):
    """One of them with a need: the repairs walked the tree down for ever, the plan's write lock held."""

    def late(*_):
        raise TimeoutError("the repairs never ended")

    cycle = {**ANSWER, "nodes": [node("a", "a", "b"), node("b", "b", "a", needs=["c"]), node("c", "c")]}
    was = signal.signal(signal.SIGALRM, late)
    signal.alarm(5)
    try:
        _, _, faults = planner._tried(repo, json.dumps(cycle), ["app.py"])
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, was)
    assert any("the plan has a cycle" in f for f in faults), faults


def test_a_repair_never_hides_a_fault_that_needs_the_models_judgement(repo, fake):
    both = {**ANSWER, "nodes": [GREETING, {**HELLO, "scope": [], "needs": ["nope"]}]}
    f = fake([{"content": PROPOSAL}, answer(both), answer(ANSWER)])
    with Store.open(repo) as store:
        ask(store, repo, "make it say hello", named("nemotron"), say=lambda s: None)
        assert plan.get(store, "hello").scope == ["app.py"]
        [bill] = store.node_log("*", ("usage",))
    assert bill["detail"]["sent_back"] == [NO_SCOPE]
    assert "nope" not in f.requests[2]["messages"][-1]["content"]  # it reads back the repaired text


def test_a_split_that_repeats_a_goal_of_two_lines_lands_with_nothing_sent_back(repo, fake):
    """A split writes the node's line again, and the schema has it fill the goal. The goal a text-form
    planner wrote has two lines; copied whole, it is the node's own goal, not a change to its contract."""
    text = ("? say hello  [hello]\n    goal: greet returns hello.\n    goal: It keeps the old name.\n"
            "    scope: app.py\n    check: true\n")  # fmt: skip
    with Store.open(repo) as store:
        T.apply(store, text, plan.Caller("planner:claude", False), None)  # a text-form planner wrote it
    split = {"goal": None, "board": [], "says": "", "nodes": [
        node("hello", "say hello", mark="-", goal="greet returns hello.\nIt keeps the old name.",
             scope=["app.py"], check="true"),
        node("hello-def", "define greet", "hello", scope=["app.py"], check="true"),
        node("hello-word", "return hello", "hello", scope=["words.py"], check="true", needs=["hello-def"]),
    ]}  # fmt: skip
    f = fake([{"content": "I have read enough."}, answer(split)])
    with Store.open(repo) as store:
        ask(store, repo, "split it", named("nemotron"), about="hello", split=True, say=lambda s: None)
        assert plan.get(store, "hello-word").parent == "hello"
        assert plan.get(store, "hello").goal == "greet returns hello.\nIt keeps the old name."
    assert len(f.requests) == 2  # one strict call: nothing was sent back


def test_a_reask_is_tried_with_the_tree_it_replaces_dropped(repo, fake):
    """`ask --finer` drops the last tree in the claim that adds the new one. The dry run drops it too,
    else a tree that uses an id of the last one again would be sent back for nothing."""
    finer = {**ANSWER, "nodes": [node("greeting", "the greeting"), {**HELLO, "check": "true"}]}
    f = fake([{"content": PROPOSAL}, answer(ANSWER), {"content": PROPOSAL}, answer(finer)])
    with Store.open(repo) as store:
        ask(store, repo, "make it say hello", named("nemotron"), say=lambda s: None)
        ask(store, repo, "make it say hello", named("nemotron"), say=lambda s: None, size="finer")
        assert plan.get(store, "hello").state == "dropped"
        [greeting, new] = plan.nodes(store, (PROPOSED,))
        assert (greeting.title, new.title, new.check, new.parent) == ("the greeting", "say hello", "true",
                                                                       greeting.id)  # fmt: skip
    assert len(f.requests) == 4  # nothing was sent back


def test_a_reask_is_tried_with_the_last_tree_dropped_as_the_person_drops_it(repo, fake, monkeypatch):
    """`graphene ask` is the person's, and drops the last tree with a node of theirs under it. The dry
    run dropped it as the planner, which may not drop the person's node: it kept the tree, and sent
    the model back for an id it used again."""
    for name in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "AI_AGENT", "CODEX_SESSION_ID", "CODEX_SANDBOX"):
        monkeypatch.delenv(name, raising=False)  # the person, as `graphene ask` runs only for them
    finer = {**ANSWER, "nodes": [node("greeting", "the greeting"), {**HELLO, "check": "true"}]}
    f = fake([{"content": PROPOSAL}, answer(ANSWER), {"content": PROPOSAL}, answer(finer), answer(finer)])
    with Store.open(repo) as store:
        ask(store, repo, "make it say hello", named("nemotron"), say=lambda s: None)
        mine = {"id": "mine", "title": "mine", "parent": "greeting", "scope": ["mine.py"], "check": "true"}
        plan.propose(store, [mine], plan.caller())
        ask(store, repo, "make it say hello", named("nemotron"), say=lambda s: None, size="finer")
        assert {n.id: n.state for n in plan.nodes(store) if n.state == "dropped"}.keys() == {
            "greeting", "hello", "mine"}  # fmt: skip
    assert len(f.requests) == 4  # nothing was sent back


def test_a_merge_is_tried_beside_the_leaves_it_would_replace(repo, fake):
    """`graphene talk merge` proposes one leaf whose scope takes in the leaves it would replace. The dry
    run lets it share their paths, as `graphene ask` does, so it is not sent back for that."""
    alex = plan.Caller("alex", True)
    both = {**ANSWER, "nodes": [node("both", "say hello and bye", scope=["app.py", "bye.py"], check="true")]}
    f = fake([{"content": "I have read enough."}, answer(both)])
    with Store.open(repo) as store:
        hi = {"id": "hi", "title": "hi", "scope": ["app.py"], "check": "true"}
        plan.propose(store, [hi, {**hi, "id": "bye", "title": "bye", "scope": ["bye.py"]}], alex)
        ask(store, repo, "one leaf for both", named("nemotron"), say=lambda s: None, beside={"hi", "bye"})
        assert plan.get(store, "both").state == PROPOSED
    assert len(f.requests) == 2  # one strict answer: nothing was sent back


def test_named_planners():
    assert label(named("nemotron")) == "nemotron"
    assert "--tools Read,Grep,Glob" in named("claude")
    for nothing in (None, "", " "):  # none chosen: nothing starts (first walker, finding 1)
        with pytest.raises(plan.Refused, match="^no planner is chosen for this repo, so nothing was started"):
            named(nothing)
    assert named("codex") == "codex exec --sandbox read-only"


def test_a_planner_that_cannot_reach_token_factory_says_why_in_its_own_words(repo, monkeypatch):
    """What the person reads when the key is missing: the planner's own last word, whole, not the
    last 300 characters of what it printed, and not "the planner" twice."""
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    tf._listed.cache_clear()
    said = []
    with Store.open(repo) as store, pytest.raises(plan.Refused) as no:
        ask(store, repo, "make it say hello", named("nemotron"), say=said.append)
    assert "no proposal (exit 3): stopped: NEBIUS_API_KEY is not set" in str(no.value)
    assert said == ["asking the planner (nemotron)…"]  # asked once: again would fail the same way
    assert "the planner printed" not in str(no.value)


def test_a_bill_under_a_cent_is_never_shown_as_nothing():
    from graphene_map.tui import money

    assert money(0.0015) == "$0.0015" and money(0.034) == "$0.03" and money(0) == "$0.00"


def test_what_git_ignores_is_never_read_and_so_never_sent(repo, fake):
    """A judge had the planner read a git-ignored .env holding a secret, and send it to Token Factory."""
    (repo / ".gitignore").write_text(".graphene/\n.env\n")
    (repo / ".env").write_text("AWS_SECRET_ACCESS_KEY=do-not-send\n")
    f = fake([call("read", path=".env"), call("list", path="."), call("grep", pattern="SECRET"),
              call("read", path=".graphene/graphene.db"), {"content": PROPOSAL}, answer(ANSWER)])  # fmt: skip
    with Store.open(repo) as store:
        ask(store, repo, "make it say hello", named("nemotron"), say=lambda s: None)
    sent = json.dumps(f.requests)
    assert "do-not-send" not in sent and "SQLite" not in sent
    results = [m["content"] for m in f.requests[-1]["messages"] if m["role"] == "tool"]
    assert "git ignores it" in results[0] and ".env" not in results[1].split("\n")
    assert results[2] == "(no match)"
