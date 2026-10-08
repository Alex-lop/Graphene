# ruff: noqa: F811  (pytest fixtures imported from test_plan are named again as arguments)
"""The plan as text: what `graphene plan edit` opens and `graphene plan propose -` reads. A person
writes it without a manual and an agent without a mistake; an edit applies to the node it was made
on, all of it or none, and a line that cannot be read is refused by its number."""

import sys

import pytest
from test_plan import ALEX, BOT, repo, store  # noqa: F401  (fixtures)

from graphene_map import plan
from graphene_map import plan_text as T
from graphene_map.plan import DONE, DROPPED, OPEN, PROPOSED, Refused

TREE = """\
goal: customers can download their invoices as PDF

- the PDF renderer  [pdf]
  - render one invoice to PDF bytes  [render]
      scope: src/pdf/**, tests/pdf/**
      check: test -f src/pdf/r.txt
  - the invoice template  [template]
      the layout from the design
      scope: templates/invoice.html
      check: true
      needs: render
- say so in the README  [docs]
    scope: README.md
    check: true
"""


def shaped(store):
    T.apply(store, TREE, ALEX, None)
    return T.render(store)


def test_a_person_writes_a_tree_and_it_reads_back_as_written(store):
    said = T.apply(store, TREE, ALEX, None)
    assert said[0] == "goal: customers can download their invoices as PDF"
    assert [n.id for n in plan.nodes(store)] == ["pdf", "render", "template", "docs"]
    template = plan.get(store, "template")
    assert (template.parent, template.needs, template.goal) == (
        "pdf",
        ["render"],
        "the layout from the design",
    )
    assert template.state == OPEN  # a person's lines are in the plan at once
    text, opened = T.render(store)
    assert set(opened) == {"*goal", "*board", "pdf", "render", "template", "docs"}  # goal, board
    # read back and applied again, it changes nothing: the text is the plan
    assert T.apply(store, text, ALEX, opened) == []


def test_an_agent_proposes_in_the_same_text_and_its_goal_waits_for_the_person(store):
    said = T.apply(store, TREE, BOT, None)
    assert all(n.state == PROPOSED for n in plan.nodes(store))
    assert plan.goal(store) == "" and "goal (proposed)" in said[0]
    plan.accept(store, ["docs"], ALEX)  # accepting any of the tree accepts the planner's sentence
    assert plan.goal(store) == "customers can download their invoices as PDF"


def test_an_agent_hangs_new_lines_under_a_node_already_in_the_plan(store):
    shaped(store)
    T.apply(store, "- the PDF renderer  [pdf]\n  ? fonts embedded  [fonts]\n      scope: assets/fonts/**\n"
                   "      check: true\n", BOT, None)  # fmt: skip
    fonts = plan.get(store, "fonts")
    assert (fonts.parent, fonts.state) == ("pdf", PROPOSED)
    with pytest.raises(
        Refused, match=r"line 2: \[render\] is in the plan already, and this text changes its scope"
    ):
        T.apply(store, "- the PDF renderer  [pdf]\n  - render  [render]\n      scope: src/**\n", BOT, None)


def test_an_edit_adds_changes_moves_accepts_and_drops_in_one_save(store):
    T.apply(store, TREE, ALEX, None)
    T.apply(store, "- the PDF renderer  [pdf]\n  ? page numbers  [pages]\n      scope: src/pages.py\n"
                   "      check: true\n", BOT, None)  # fmt: skip
    text, opened = T.render(store)
    text = (
        text.replace("scope: README.md", "scope: README.md, docs/**")  # a wider scope
        .replace("? page numbers  [pages]", "- page numbers  [pages]")  # accepted
        .replace(
            "      needs: render\n",
            "      needs: render\n"
            "    - a new leaf with no id\n        scope: templates/x.html\n        check: true\n",
        )  # fmt: skip
    )
    text = text.replace(
        "- say so in the README  [docs]", "  - say so in the README  [docs]"
    )  # moved under pdf
    said = T.apply(store, text, ALEX, opened)
    assert plan.get(store, "docs").scope == ["README.md", "docs/**"]
    assert plan.get(store, "docs").parent == "pdf"
    assert plan.get(store, "pages").state == OPEN
    new = plan.get(store, "new-leaf-no")  # an id from its title: it names a branch too
    assert new.parent == "template" and new.state == OPEN
    assert "accepted pages" in said and any(line.startswith("docs: moved under pdf") for line in said)
    # deleting a node's lines drops that node, and what is under it
    text, opened = T.render(store)
    said = T.apply(store, without(text, "template"), ALEX, opened)
    assert plan.get(store, "template").state == DROPPED and plan.get(store, "new-leaf-no").state == DROPPED
    assert "dropped template: the invoice template" in said


def without(text, node_id):
    """The text with one node's line and every line under it deleted, as a person does in an editor."""
    lines, out, cut = text.splitlines(), [], None
    for line in lines:
        depth = len(line) - len(line.lstrip())
        if cut is not None and (depth > cut or not line.strip()):
            continue
        cut = depth if line.rstrip().endswith(f"[{node_id}]") else None
        if cut is None:
            out.append(line)
    return "\n".join(out)


def test_reordering_lines_reorders_the_siblings(store):
    text, opened = shaped(store)
    swapped = text.replace("- the PDF renderer  [pdf]", "@@").replace(
        "- say so in the README  [docs]", "- the PDF renderer  [pdf]"
    )
    lines = swapped.splitlines()
    docs_block = ["- say so in the README  [docs]", "    scope: README.md", "    check: true"]
    lines = [line for line in lines if line not in ("    scope: README.md", "    check: true")]
    lines = [line for line in lines if line != "- the PDF renderer  [pdf]"]
    at = lines.index("@@")
    lines[at : at + 1] = [*docs_block, "- the PDF renderer  [pdf]"]
    T.apply(store, "\n".join(lines), ALEX, opened)
    assert [n.id for n in plan.kids(plan.nodes(store))[None]] == ["docs", "pdf"]
    assert [e["kind"] for e in store.node_log("*")][-1] == "reordered"


def test_a_line_it_cannot_read_is_refused_by_its_number_and_nothing_is_applied(store):
    text, opened = shaped(store)
    for bad, said in [
        ("scope: src/**\n", r"line 1: .* is not under a node"),
        ("- a  [x]\n- b  [x]\n", r"line 2: \[x\] is on line 1 too"),
        ("- a\n    signoff: maybe\n", r"line 2: signoff is yes or no"),
        ("- a\n    scope: 'src/my file\n", r"line 2: No closing quotation"),
        ("-  [x]\n", r"line 1: a node needs a title"),
    ]:
        with pytest.raises(Refused, match=said):
            T.apply(store, bad, ALEX, None)
    # one good change and one the plan refuses: neither is made
    broken = text.replace("scope: README.md", "scope: README.md, notes.md").replace(
        "      check: test -f src/pdf/r.txt\n", ""
    )
    with pytest.raises(Refused, match=r"line \d+ \[render\]: render: a leaf needs a check"):
        T.apply(store, broken, ALEX, opened)
    assert plan.get(store, "docs").scope == ["README.md"]


def test_an_edit_to_a_node_that_moved_on_since_it_was_opened_is_refused(store):
    text, opened = shaped(store)
    plan.edit(store, "docs", {"check": "test -f README.md"}, ALEX)
    with pytest.raises(Refused, match=r"\[docs\] was changed by someone else since this text was opened"):
        T.apply(store, text.replace("scope: README.md", "scope: README.md, x.md"), ALEX, opened)
    # a node the person did not change is no conflict, and their change elsewhere is made without
    # writing over the one made meanwhile
    T.apply(store, text.replace("check: test -f src/pdf/r.txt", "check: true"), ALEX, opened)
    assert plan.get(store, "render").check == "true" and plan.get(store, "docs").check == "test -f README.md"


def test_a_node_in_the_plan_does_not_go_back_to_being_a_proposal(store):
    text, opened = shaped(store)
    with pytest.raises(Refused, match=r"\[docs\] is in the plan already; a node does not go back"):
        T.apply(store, text.replace("- say so in the README", "? say so in the README"), ALEX, opened)


def test_a_subtree_edit_touches_only_the_subtree(store):
    shaped(store)
    text, opened = T.render(store, "pdf")
    assert set(opened) == {"pdf", "render", "template"} and "[docs]" not in text
    with pytest.raises(Refused, match=r"\[docs\] is in the plan, but not in the part of it"):
        T.apply(store, text + "- say so in the README  [docs]\n", ALEX, opened, "pdf")
    # a line added at the subtree's top level is a sibling of its root
    T.apply(store, text + "- the email  [email]\n    scope: src/mail/**\n    check: true\n", ALEX, opened)
    assert plan.get(store, "email").parent is None and plan.get(store, "docs").state == OPEN


def test_what_is_true_of_a_node_is_written_as_notes_and_never_read(store, repo):
    shaped(store)
    plan.start(store, "render", BOT, repo)
    plan.release(store, "render", BOT, "it needs src/util.py as well")
    store.log_node("render", plan._now(), "denied", None, None, None, {"path": "src/util.py"})
    text, _ = T.render(store)
    assert "# came back: it needs src/util.py as well" in text  # the word the screen shows, then why
    assert "# it wanted, outside its scope: src/util.py" in text
    assert "# waiting on render (came back)" in text  # the template waits on it


def test_the_notes_say_a_nodes_state_in_the_words_of_the_screen(store, repo):
    """The text form's notes spelled the state their own way ("waits on", "running: claude:…", no
    note at all for a ready leaf); now the same word as the screen and `graphene plan`, then what
    the word needs said."""
    run = plan.Caller("run:claude", False, "run-session")
    shaped(store)
    plan.propose(store, [{"id": "mine", "title": "read it over", "owner": "alex"},
                         {"id": "later", "title": "the rest, to be split"}], ALEX)  # fmt: skip
    plan.propose(store, [{"id": "idea", "title": "an idea", "scope": ["x.py"], "check": "true"}], BOT)
    plan.start(store, "render", run, repo)
    notes = {}
    for line in T.render(store)[0].splitlines():
        if "[" in line:
            node = line.rsplit("[", 1)[1].rstrip("]")
        elif line.strip().startswith("# ") and not line.startswith("#"):
            notes.setdefault(node, []).append(line.strip()[2:])
    assert notes["pdf"] == ["0/2 done"] and notes["docs"] == ["ready"]
    assert notes["render"][0].startswith("running: claude, started by graphene run, since ")
    assert notes["template"] == ["waiting on render (running)"]
    assert notes["mine"] == ["yours"] and notes["later"] == ["to fill in: no scope and no leaves yet"]
    assert notes["idea"] == ["proposed by a Claude Code session (aaaa1111)"]


def test_a_multi_line_check_is_compared_as_the_text_writes_it(store):
    [n] = plan.propose(store, [{"id": "x", "title": "x", "scope": ["x"], "check": "true\ntrue"}], ALEX)
    text, opened = T.render(store)
    assert "check: true; true" in text
    assert T.apply(store, text, ALEX, opened) == []  # an edit elsewhere never rewrites it
    assert plan.get(store, "x").check == "true\ntrue"


def test_the_editor_loop_puts_a_refusal_under_its_line_and_keeps_the_text(store, repo, tmp_path):
    shaped(store)
    path = tmp_path / "PLAN_EDIT.txt"
    tries = []

    def editor(p):
        text = p.read_text()
        tries.append(text)
        if len(tries) == 1:
            p.write_text(text.replace("scope: README.md", "scope: README.md\n    signoff: maybe"))
        elif len(tries) == 2:
            assert "# ^ refused: signoff is yes or no, not 'maybe'" in text
            p.write_text(text.replace("signoff: maybe", "signoff: yes"))
        return 0

    said = T.edit_loop(lambda: store_ctx(store), None, False, ALEX, [], path, "the plan of x", editor)
    assert "docs: signoff changed" in said and plan.get(store, "docs").signoff is True
    assert not path.exists()
    # saved unchanged after a refusal: nothing applied, the text kept
    tries.clear()

    def stubborn(p):
        text = p.read_text()
        tries.append(text)
        if len(tries) == 1:
            p.write_text(text.replace("scope: README.md", "scope: README.md\n    owner:"))
            p.write_text(p.read_text().replace("- say so in the README  [docs]", "- [docs]"))
        return 0

    with pytest.raises(Refused, match="nothing was applied; your text is kept in"):
        T.edit_loop(lambda: store_ctx(store), None, False, ALEX, [], path, "x", stubborn)
    assert path.exists()


class store_ctx:
    """The loop opens the store each time it needs it; the test's store stays open."""

    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self.store

    def __exit__(self, *exc):
        return False


def test_undo_puts_back_the_persons_last_act_unless_it_moved_on(store, repo):
    shaped(store)
    with plan.undoable(store, ALEX, "node drop docs"):
        plan.drop(store, "docs", ALEX)
    assert plan.undo(store, ALEX) == "node drop docs" and plan.get(store, "docs").state == OPEN
    with plan.undoable(store, ALEX, "node set render"):
        plan.edit(store, "render", {"scope": ["src/**"]}, ALEX)
    plan.start(store, "render", BOT, repo)  # an executor took it since
    with pytest.raises(Refused, match=r"cannot undo 'node set render': render \(running\) changed since"):
        plan.undo(store, ALEX)
    with pytest.raises(Refused, match="undoing"):
        plan.undo(store, BOT)


def test_undo_of_an_add_takes_the_node_out_and_a_goal_back(store):
    with plan.undoable(store, ALEX, "plan edit"):
        T.apply(store, TREE, ALEX, None)
    assert plan.undo(store, ALEX) == "plan edit"
    assert {n.state for n in plan.nodes(store)} == {DROPPED} and plan.goal(store) == ""
    with pytest.raises(Refused, match="nothing to undo"):
        plan.undo(store, ALEX)


def test_a_check_no_executor_can_make_pass_is_named_before_anything_is_spent(repo):
    files = ["tests/test_csvfeed.py", "ingest/xmlfeed.py"]
    typo = plan.Node("n9", "t", scope=["tests/test_xmlfeed.py"],
                     check="python3 -m pytest/ test/test_csvfeed.py tests/test_jsonfeed.py -q")  # fmt: skip
    assert plan.unreachable(typo, files, repo) == [
        "pytest/",
        "test/test_csvfeed.py",
        "tests/test_jsonfeed.py",
    ]
    check = "python3 -c 'from ingest.xmlfeed import read_xml' && python3 tests/test_xmlfeed.py"
    fine = plan.Node("x", "t", scope=["tests/test_xmlfeed.py"], check=check)
    assert plan.unreachable(fine, files, repo) == []


def test_a_child_put_between_a_node_and_its_own_lines_is_refused_not_given_them(store):
    text, opened = shaped(store)
    wedged = text.replace("  - the invoice template  [template]\n", "  - the invoice template  [template]\n"
                          "    - a step inside it\n")  # fmt: skip
    with pytest.raises(Refused, match=r"line \d+: the line sits between \[template\] and \[template\]'s own"):
        T.apply(store, wedged, ALEX, opened)


def test_done_leaves_are_written_with_when(store, repo):
    shaped(store)
    plan.start(store, "render", BOT, repo)
    (repo / "src" / "pdf").mkdir(parents=True)
    (repo / "src" / "pdf" / "r.txt").write_text("done\n")
    plan.finish(store, "render", BOT)
    text, _ = T.render(store)
    assert "[render]\n      # done " in text and plan.get(store, "render").state == DONE


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


# -- the recheck of the closing review: its regression tests --------------------


# Recheck 53 (partly)
def test_a_check_that_can_pass_is_not_called_unreachable(repo):
    need = plan.Node("pdf", "the renderer", scope=["tests/pdf/**"])
    for check, everything in (
        ("python3 -m pytest tests/pdf/test_render.py -q", [need]),  # what a need writes
        ("curl -sf localhost:8000/api/health", []),
        ("cd web && npx jest src/App.test.js", []),
        ("make build && test -f dist/app.js", []),
    ):
        node = plan.Node("n", "t", scope=["lib/**"], check=check, needs=["pdf"])
        assert plan.unreachable(node, ["web/src/App.test.js"], repo, everything) == [], check


# Recheck 55 (fixed)
def test_a_sub_goal_whose_children_are_all_proposals_is_not_asked_the_leaf_rule(store):
    T.apply(store, "- the API  [api]\n    check: true\n  ? endpoint  [ep]\n      scope: src/**\n"
                   "      check: true\n", ALEX, None)  # fmt: skip
    assert plan.edit(store, "api", {"title": "the public API"}, ALEX).title == "the public API"


# -- every key the text reads: honoured, or refused by its line; never turned into prose -----------


def leaf(title: str, *lines: str, check: bool = True, scope: str = "calc.py") -> str:
    """A node's line and its own lines under it, and a scope and a check unless told otherwise."""
    tail = (f"scope: {scope}", "check: true") if check else ()
    return "".join(f"{'    ' if k else ''}{line}\n" for k, line in enumerate((f"- {title}", *lines, *tail)))


def test_parent_places_a_node_under_a_node_of_the_text_or_of_the_plan(store):
    """A proposal said `parent: wire` under a leaf; it was read as the leaf's goal and the leaf landed
    at the root."""
    wire = "- wire it in  [wire]\n  - add is kept  [keep]\n      scope: calc.py\n      check: true\n"
    T.apply(store, wire + leaf("sub is added  [sub]", "parent: wire", scope="sub.py"), BOT, None)
    sub = plan.get(store, "sub")
    assert (sub.parent, sub.goal) == ("wire", "")
    plan.accept(store, [], ALEX)
    T.apply(store, leaf("mul is added  [mul]", "parent: wire", scope="mul.py"), BOT, None)
    assert plan.get(store, "mul").parent == "wire"  # a node already in the plan
    neg = leaf("neg  [neg]", "parent: pow", scope="neg.py")
    powers = leaf("powers  [pow]", "parent: wire", check=False) + neg
    T.apply(store, powers, BOT, None)
    assert (plan.get(store, "pow").parent, plan.get(store, "neg").parent) == ("wire", "pow")
    assert "parent:" not in T.render(store)[0]  # the tree is said by indentation, not as anyone's goal


@pytest.mark.parametrize(
    "text, says",
    [
        (leaf("a leaf  [a]", "parent: nowhere"),
         "line 2: parent: 'nowhere' is not the id of a node, in this text or in the plan"),
        (leaf("a leaf  [a]", "parent:"), "line 2: parent: names no node"),
        ("- top  [top]\n  - a leaf  [a]\n      parent: other\n      scope: x\n      check: true\n"
         + leaf("other  [other]"),
         "line 3: parent: other, but [a]'s line is indented under [top]; say where it goes one way"),
        (leaf("a leaf  [a]", "parent: a"), "line 2: parent: a is the node itself"),
        (leaf("a leaf  [a]", "title: something else"),
         "line 2: title: is not read under a node; a node's title is its own line, after its '- '"),
        (leaf("a leaf  [a]", "children: b, c", check=False), "line 2: children: is not read under a node"),
        (leaf("a leaf  [a]", "id: b"), "line 2: id: b, and the node's line says [a]"),
        (leaf("a leaf", "id: not an id!"), "line 2: id: 'not an id!' is not an id"),
    ],
)  # fmt: skip
def test_a_key_the_text_cannot_honour_is_refused_by_its_line(store, text, says):
    with pytest.raises(Refused) as no:
        T.apply(store, text, BOT, None)
    assert str(no.value).startswith(says)
    assert plan.nodes(store) == []


def test_id_is_the_nodes_id_and_goal_is_what_it_should_achieve(store):
    T.apply(store, leaf("div is added", "id: div", "goal: division, by zero refused"), BOT, None)
    div = plan.get(store, "div")
    assert (div.title, div.goal) == ("div is added", "division, by zero refused")


def test_a_person_moves_a_node_with_parent_in_an_edit(store):
    shaped(store)
    text, opened = T.render(store)
    docs = "- say so in the README  [docs]\n"
    moved = text.replace(docs, docs + "    parent: pdf\n")
    assert T.apply(store, moved, ALEX, opened) == ["docs: moved under pdf"]
    assert plan.get(store, "docs").parent == "pdf"




# -- a check never runs another leaf's file -------------------------------------------------------------


def top(node_id: str, scope: str, check: str = "true", *more: str) -> str:
    """A leaf at the top, named by its id, with its scope, its check and any more lines of its own."""
    lines = (f"- {node_id}  [{node_id}]", f"    scope: {scope}", f"    check: {check}")
    return "".join(f"{line}\n" for line in (*lines, *(f"    {m}" for m in more)))


def test_a_check_that_runs_another_leafs_file_waits_on_it_and_the_proposal_says_so(store):
    reader = top("reader", "src/xml.py", "python3 -m pytest tests/test_xml.py -q")
    said = T.apply(store, reader + top("tests", "tests/test_xml.py"), BOT, None)
    assert plan.get(store, "reader").needs == ["tests"]
    assert said[-1] == "reader waits on tests: its check runs tests/test_xml.py, which tests writes"
    csv = top("csv", "src/csv.py", "python3 ./tests/test_csv.py")  # ./a is a
    T.apply(store, csv + top("t", "tests/test_csv.py"), BOT, None)
    assert plan.get(store, "csv").needs == ["t"]


def test_a_check_that_runs_a_module_by_name_waits_on_the_leaf_that_writes_its_file(store):
    """Statements run 3 stopped on this form: `unittest tests.test_dunning`, a file another leaf wrote."""
    check = "python3 -m unittest tests.test_dunning.TestDunning.test_fee"
    T.apply(store, top("sections", "src/x.py", check) + top("reports", "tests/test_dunning.py"), BOT, None)
    assert plan.get(store, "sections").needs == ["reports"]


def test_a_check_that_runs_a_directory_waits_on_the_leaves_that_write_in_it(store):
    """A directory names what git tracks in it and what a scope makes in it: neither file is there yet."""
    code = top("code", "src/code.py", "python3 -m unittest discover -q tests") + top("x", "tests/test_x.py")
    more = top("more", "src/more.py", "python3 -m pytest spec/") + top("y", "spec/test_y.py")
    T.apply(store, code + more, BOT, None)
    assert (plan.get(store, "code").needs, plan.get(store, "more").needs) == (["x"], ["y"])


def test_a_tests_leaf_that_waits_on_the_code_adds_nothing_and_refuses_nothing(store):
    """The shape the rule asks for: the code's check runs the tests directory, and one tests leaf that
    waits on the code writes the test file. The code's check sees tests/ as it is at the base."""
    check = "python3 -m unittest discover tests"
    tests = top("tests", "tests/test_x.py", check, "needs: code")
    more = top("more", "src/more.py", check, "needs: tests")  # it waits on the tests leaf already
    said = T.apply(store, top("code", "src/code.py", check) + tests + more, BOT, None)
    assert [n.needs for n in plan.nodes(store)] == [[], ["code"], ["tests"]]
    assert not [line for line in said if " waits on " in line]


def test_a_check_that_runs_a_new_file_a_later_leaf_writes_is_refused_by_its_line(store):
    """Take 9, and tonight's first Ultra ask: the tests leaf waits on the code, and the code's check runs
    the tests leaf's new file. It could never pass: the file is not there when the check runs."""
    code = top("feed", "ingest/xml.py", "python3 -m pytest tests/test_xml.py -q")
    says = r"^line 1 \[feed\]: feed: its check runs tests/test_xml\.py, which tests writes after it\. "
    with pytest.raises(Refused, match=says):
        T.apply(store, code + top("tests", "tests/test_xml.py", "true", "needs: feed"), BOT, None)
    assert plan.nodes(store) == []


def test_two_leaves_that_write_one_path_are_refused_by_the_line_and_an_old_pair_is_not_judged_again(store):
    said = r"^line 1 \[a\]: a and b both write README\.md\. A path has one leaf that writes it: give it to "
    with pytest.raises(Refused, match=said + "one, and let the other wait on it$"):
        T.apply(store, top("a", "README.md") + top("b", "docs/**, README.md"), BOT, None)
    assert plan.nodes(store) == []
    T.apply(store, top("a", "README.md"), ALEX, None)
    with pytest.raises(Refused, match=r"^line 1 \[c\]: c and a both write README\.md\. "):
        T.apply(store, top("c", "src/c.py, README.md"), BOT, None)
    # a plan made before the rule may hold two writers of one path: an edit that adds no shared path stands
    plan.propose(store, [{"id": "old", "title": "old", "scope": ["NOTES.md"], "check": "true"}], ALEX)
    store.put_node({**store.node_row("old"), "scope": ["README.md"]})
    text, opened = T.render(store)
    T.apply(store, text.replace("scope: README.md", "scope: README.md, CHANGELOG.md", 1), ALEX, opened)
    assert plan.get(store, "a").scope == ["README.md", "CHANGELOG.md"]


def test_a_word_that_names_nothing_is_ignored_and_a_check_that_moves_is_not_judged(store):
    """pytest is a program, `-k name` and --cov=src are flags, PYTHONPATH=src sets a variable, and `test`
    first in a command is the shell's: none is a path, though a scope covers each. After cd, no path is
    from the top."""
    checker = "PYTHONPATH=src test -f lib/c.py && python3 -m pytest -q -k name --cov=src"
    web = top("web", "web/x.py", "cd web && python3 -m pytest tests/test_z.py") + top("z", "tests/test_z.py")
    checker = top("top", "*, src/new.py, test/test_y.py") + top("checker", "lib/c.py", checker)
    T.apply(store, checker + web, BOT, None)
    assert [n.needs for n in plan.nodes(store)] == [[], [], [], []]


def test_a_plan_edit_that_changes_a_check_says_what_it_waits_on_and_a_moved_path_is_no_clash(store):
    T.apply(store, top("docs", "docs/**") + top("code", "src/code.py, README.md"), ALEX, None)
    text, opened = T.render(store)
    checked = text.replace("README.md\n    check: true", "README.md\n    check: test -f docs/x.md")
    said = T.apply(store, checked, ALEX, opened)
    assert said == ["code: check changed; code waits on docs: its check runs docs/x.md, which docs writes"]
    text, opened = T.render(store)  # README.md goes from code to a new leaf, in one save
    readme = top("readme", "README.md", "grep -q ids README.md")  # its own file: it waits on no one
    T.apply(store, text.replace("src/code.py, README.md", "src/code.py") + readme, ALEX, opened)
    assert [plan.get(store, i).scope for i in ("code", "readme")] == [["src/code.py"], ["README.md"]]
    assert plan.get(store, "readme").needs == []
    text, opened = T.render(store)
    with pytest.raises(Refused, match=r"^line \d+ \[docs\]: docs and readme both write README\.md\. "):
        T.apply(store, text.replace("scope: docs/**", "scope: docs/**, README.md"), ALEX, opened)


def test_one_save_is_judged_against_the_scopes_the_whole_save_gives(store):
    """The fourth review of 8 October: a new line's check was judged before the save's edits were in, so
    one save and the same edits made as two gave different needs. f waited on a, which tests/test_shared.py
    had just left, and not on t, which had just taken tests/test_f.py."""
    T.apply(store, top("t", "tests/test_app.py") + top("a", "src/a.py, tests/test_shared.py"), ALEX, None)
    text, opened = T.render(store)
    text = text.replace("tests/test_app.py", "tests/test_app.py, tests/test_f.py").replace(
        "src/a.py, tests/test_shared.py", "src/a.py")  # fmt: skip
    text += top("b", "src/b.py, tests/test_shared.py")
    text += top("f", "src/f.py", "python3 -m pytest tests/test_f.py tests/test_shared.py")
    said = T.apply(store, text, ALEX, opened)
    assert plan.get(store, "f").needs == ["t", "b"]
    why = ("f waits on t, b: its check runs tests/test_f.py, which t writes, and tests/test_shared.py, "
           "which b writes")  # fmt: skip
    assert said == ["added b: b", "added f: f", "t: scope changed", "a: scope changed", why]
    text, opened = T.render(store)  # a check that runs a file only a leaf after it writes: never passes
    scope = "tests/test_app.py, tests/test_f.py"
    text = text.replace(scope, f"{scope}, tests/test_g.py").replace("[t]\n", "[t]\n    needs: g\n")
    text += top("g", "src/g.py", "python3 -m pytest tests/test_g.py")
    with pytest.raises(Refused, match=r"^line \d+ \[g\]: g: its check runs tests/test_g\.py, which t writes"):
        T.apply(store, text, ALEX, opened)


def test_a_check_changed_in_a_save_is_judged_after_the_boards_answers_in_it(store):
    T.apply(store, top("a", "src/a.py") + top("b", "src/b.py"), ALEX, None)
    asked = "question: which?  [q]\n    default: d\n    option: o\n    then: scope b + tests/test_a.py\n"
    T.apply(store, asked, BOT, None)
    text, opened = T.render(store)
    text = text.replace("src/a.py\n    check: true", "src/a.py\n    check: python3 -m pytest tests/test_a.py")
    T.apply(store, text.replace("then: scope b + tests/test_a.py\n", "then: scope b + tests/test_a.py\n"
                                "    answer: option 1\n"), ALEX, opened)  # fmt: skip
    assert plan.get(store, "b").scope == ["src/b.py", "tests/test_a.py"]
    assert plan.get(store, "a").needs == ["b"]  # as when the answer came first, in a save of its own


def test_a_leaf_in_the_plan_waits_on_one_that_joins_it_and_writes_what_its_check_runs(store):
    """The fourth review of 8 October: only a new leaf's check was judged. f, in the plan already, runs
    tests/test_f.py, which t, added after it, writes: f ran before the test was there, and came back."""
    f = {"id": "f", "title": "f", "scope": ["src/f.py"], "check": "python3 -m pytest tests/test_f.py"}
    t = {"id": "t", "title": "t", "scope": ["tests/test_f.py"], "check": "true"}
    plan.propose(store, [f], ALEX)
    told = []
    plan.propose(store, [t], ALEX, told=told)
    assert plan.get(store, "f").needs == ["t"]
    assert told == ["f waits on t: its check runs tests/test_f.py, which t writes"]
    # an agent's proposal binds nobody: what is in the plan waits on it once the person accepts it
    plan.propose(store, [{**f, "id": "g", "scope": ["src/g.py"], "check": "pytest tests/test_g.py"}], ALEX)
    plan.propose(store, [{**t, "id": "u", "scope": ["tests/test_g.py"]}], BOT)
    assert plan.get(store, "g").needs == []
    told = []
    plan.accept(store, ["u"], ALEX, told=told)
    assert plan.get(store, "g").needs == ["u"] and plan.get(store, "g").rev == 2
    assert told == ["g waits on u: its check runs tests/test_g.py, which u writes"]
    # a tests leaf that waits on the code, whose check runs the tests leaf's new file: it could never pass
    plan.propose(store, [{**f, "id": "h", "scope": ["src/h.py"], "check": "pytest tests/test_h.py"}], ALEX)
    plan.propose(store, [{**t, "id": "v", "scope": ["tests/test_h.py"], "needs": ["h"]}], BOT)
    with pytest.raises(Refused, match=r"^h: its check runs tests/test_h\.py, which v writes after it\. "):
        plan.accept(store, ["v"], ALEX, told=[])
    assert plan.get(store, "v").state == PROPOSED


def test_a_scope_that_takes_in_what_another_leafs_check_runs_makes_that_leaf_wait(store):
    T.apply(store, top("x", "src/x.py", "python3 -m pytest tests/test_y.py") + top("y", "src/y.py"), ALEX)
    text, opened = T.render(store)
    said = T.apply(store, text.replace("scope: src/y.py", "scope: src/y.py, tests/test_y.py"), ALEX, opened)
    assert plan.get(store, "x").needs == ["y"]
    assert said == ["y: scope changed", "x waits on y: its check runs tests/test_y.py, which y writes"]
    T.apply(store, top("p", "src/p.py", "python3 -m pytest tests/test_q.py") + top("q", "src/q.py"), ALEX)
    told = []  # node set, the same
    plan.edit(store, "q", {"scope": ["src/q.py", "tests/test_q.py"]}, ALEX, told=told)
    assert plan.get(store, "p").needs == ["q"]
    assert told == ["p waits on q: its check runs tests/test_q.py, which q writes"]


def test_a_check_changed_in_a_save_waits_on_a_scope_changed_below_it(store):
    """x's check runs tests/test_y.py now, and y, on a line below, takes that file in the same save."""
    T.apply(store, top("x", "src/x.py") + top("y", "src/y.py"), ALEX, None)
    text, opened = T.render(store)
    text = text.replace("src/x.py\n    check: true", "src/x.py\n    check: python3 -m pytest tests/test_y.py")
    said = T.apply(store, text.replace("scope: src/y.py", "scope: src/y.py, tests/test_y.py"), ALEX, opened)
    assert said == [
        "x: check changed; x waits on y: its check runs tests/test_y.py, which y writes", "y: scope changed"
    ]
