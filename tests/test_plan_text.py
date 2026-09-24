# ruff: noqa: F811  (pytest fixtures imported from test_plan are named again as arguments)
"""The plan as text: what `graphene plan edit` opens and `graphene plan propose -` reads. A person
writes it without a manual and an agent without a mistake; an edit applies to the node it was made
on, all of it or none, and a line that cannot be read is refused by its number."""

import sys

import pytest
from test_plan import ALEX, BOT, repo, store  # noqa: F401  (fixtures)

from graphene_debrief import plan
from graphene_debrief import plan_text as T
from graphene_debrief.plan import DONE, DROPPED, OPEN, PROPOSED, Refused

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
    assert set(opened) == {"*goal", "pdf", "render", "template", "docs"}  # and the goal, as it was shown
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
    T.apply(store, "- the PDF renderer  [pdf]\n  ? fonts embedded  [fonts]\n      scope: src/pdf/fonts/**\n"
                   "      check: true\n", BOT, None)  # fmt: skip
    fonts = plan.get(store, "fonts")
    assert (fonts.parent, fonts.state) == ("pdf", PROPOSED)
    with pytest.raises(
        Refused, match=r"line 2: \[render\] is in the plan already, and this text changes its scope"
    ):
        T.apply(store, "- the PDF renderer  [pdf]\n  - render  [render]\n      scope: src/**\n", BOT, None)


def test_an_edit_adds_changes_moves_accepts_and_drops_in_one_save(store):
    T.apply(store, TREE, ALEX, None)
    T.apply(store, "- the PDF renderer  [pdf]\n  ? page numbers  [pages]\n      scope: src/pdf/p.py\n"
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


def leaf(title: str, *lines: str, check: bool = True) -> str:
    """A node's line and its own lines under it, and a scope and a check unless told otherwise."""
    tail = ("scope: calc.py", "check: true") if check else ()
    return "".join(f"{'    ' if k else ''}{line}\n" for k, line in enumerate((f"- {title}", *lines, *tail)))


def test_parent_places_a_node_under_a_node_of_the_text_or_of_the_plan(store):
    """A proposal said `parent: wire` under a leaf; it was read as the leaf's goal and the leaf landed
    at the root."""
    wire = "- wire it in  [wire]\n  - add is kept  [keep]\n      scope: calc.py\n      check: true\n"
    T.apply(store, wire + leaf("sub is added  [sub]", "parent: wire"), BOT, None)
    sub = plan.get(store, "sub")
    assert (sub.parent, sub.goal) == ("wire", "")
    plan.accept(store, [], ALEX)
    T.apply(store, leaf("mul is added  [mul]", "parent: wire"), BOT, None)
    assert plan.get(store, "mul").parent == "wire"  # a node already in the plan
    powers = leaf("powers  [pow]", "parent: wire", check=False) + leaf("neg  [neg]", "parent: pow")
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
