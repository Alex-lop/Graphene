# ruff: noqa: F811, E501  (fixtures imported from test_plan; long literals are texts as written)
"""The text form against every finding the adversarial review confirmed (49), one regression each where
it was fixed: the finding's number is above its test. Written by the agents that re-checked the fixes,
run and kept here."""

import pytest
from test_plan import ALEX, BOT, repo, store  # noqa: F401  (fixtures)
from test_plan_text import TREE, shaped, store_ctx, without  # noqa: F401

from graphene_debrief import plan
from graphene_debrief import plan_text as T
from graphene_debrief.plan import (  # noqa: F401
    DONE,
    DROPPED,
    OPEN,
    PROPOSED,
    REVIEW,
    RUNNING,
    Caller,
    Refused,
)
from graphene_debrief.store import Store  # noqa: F401


# finding 0 (fixed)
def test_a_goal_of_several_lines_comes_back_whole_and_grows_no_node(store):
    goal = "customers download invoices as PDF\nso support stops getting emails\n- the old CSV export keeps working"
    plan.set_goal(store, goal, ALEX)
    T.apply(store, "- render one invoice  [render]\n    scope: src/pdf/**\n    check: true\n", ALEX, None)
    text, opened = T.render(store)
    widened = text.replace("scope: src/pdf/**", "scope: src/pdf/**, tests/pdf/**")
    assert T.apply(store, widened, ALEX, opened) == ["render: scope changed"]
    sub, opened = T.render(store, "render")  # the goal as "# the plan:" notes, every line of it
    assert T.apply(store, sub, ALEX, opened) == []
    assert T.apply(store, T.render(store)[0], BOT, None) == []  # an agent piping `plan --text` back
    assert (plan.goal(store), [n.id for n in plan.nodes(store)]) == (goal, ["render"])


# finding 1 (partly)
def test_a_comma_in_a_scope_glob_survives_a_save_of_another_node(store):
    plan.propose(store, [{"id": "a", "title": "leaf a", "scope": ["data/2024,Q1.csv"], "check": "true"},
                         {"id": "b", "title": "leaf b", "scope": ["README.md"], "check": "true"}], ALEX)  # fmt: skip
    text, opened = T.render(store)
    assert T.apply(store, text, ALEX, opened) == []
    edited = text.replace("scope: README.md\n    check: true", "scope: README.md\n    check: make b")
    assert T.apply(store, edited, ALEX, opened) == ["b: check changed"]
    a = plan.get(store, "a")
    assert (a.scope, a.rev) == (["data/2024,Q1.csv"], 1)


# finding 2 (fixed)
def test_tabs_inside_values_survive_and_a_done_node_with_one_blocks_no_edit(store, repo):
    plan.set_goal(store, "phase 1:\tinvoices", ALEX)
    check = "grep -q 'x\ty' src/t/a.txt"
    plan.propose(store, [{"id": "a", "title": "leaf a", "goal": "col1\tcol2", "scope": ["src/t/**"], "check": check},
                         {"id": "b", "title": "leaf b", "scope": ["README.md"], "check": "true"}], ALEX)  # fmt: skip
    plan.start(store, "a", BOT, repo)
    (repo / "src" / "t").mkdir(parents=True)
    (repo / "src" / "t" / "a.txt").write_text("x\ty\n")
    plan.finish(store, "a", BOT)
    text, opened = T.render(store)
    assert plan.get(store, "a").state == DONE and T.apply(store, text, ALEX, opened) == []
    edited = text.replace("scope: README.md", "scope: README.md, docs/**")
    assert T.apply(store, edited, ALEX, opened) == ["b: scope changed"]
    a = plan.get(store, "a")
    assert (a.goal, a.check, plan.goal(store)) == ("col1\tcol2", check, "phase 1:\tinvoices")


# finding 3 (partly)
def test_backslashes_in_a_scope_survive_a_save_of_another_node(store):
    scope = ["src\\api\\**", "app/\\[slug\\]/**", "docs\\"]
    plan.propose(store, [{"id": "a", "title": "leaf a", "scope": scope, "check": "true"},
                         {"id": "b", "title": "leaf b", "scope": ["docs/**"], "check": "echo b"}], ALEX)  # fmt: skip
    text, opened = T.render(store)
    assert T.apply(store, text.replace("echo b", "echo b2"), ALEX, opened) == ["b: check changed"]
    assert plan.get(store, "a").scope == scope
    with pytest.raises(Refused, match="line break"):  # refused when written, not on every later save
        plan.propose(store, [{"id": "c", "title": "leaf c", "scope": ["src/a\nb/**"], "check": "true"}], ALEX)


# finding 4 (fixed)
def test_a_planners_goal_stays_proposed_through_a_save_that_accepts_nothing(store):
    T.apply(store, "goal: the planner's sentence\n- one  [a]\n    scope: src/a/**\n    check: true\n"
                   "- two  [b]\n    scope: src/b/**\n    check: true\n", BOT, None)  # fmt: skip
    text, opened = T.render(store)
    assert T.apply(store, text, ALEX, opened) == []
    assert T.apply(store, text.split("? two")[0], ALEX, opened) == ["dropped b: two"]  # b rejected
    assert (plan.goal(store), store.meta("goal:proposed")) == ("", "the planner's sentence")
    text, opened = T.render(store)
    assert T.apply(store, text.replace("? one", "- one"), ALEX, opened) == ["accepted a"]
    assert plan.goal(store) == "the planner's sentence"


# finding 5 (fixed)
def test_a_blank_check_is_not_written_as_none_and_a_round_trip_keeps_it(store):
    with pytest.raises(Refused, match="a: a leaf needs a check"):  # blank is no check, not a command
        plan.propose(store, [{"id": "a", "title": "t", "scope": ["src/**"], "check": " \n\t"}], ALEX)
    plan.propose(
        store, [{"id": "a", "title": "t", "scope": ["src/**"], "check": " \n\t", "signoff": True}], ALEX
    )
    assert plan.get(store, "a").check is None
    text, opened = T.render(store)
    assert "check:" not in text  # was `check: None`, stored back as the command 'None'
    assert T.apply(store, text, ALEX, opened) == []
    assert (plan.get(store, "a").check, plan.get(store, "a").rev) == (None, 1)


# finding 6 (fixed)
def test_a_save_that_moves_no_sibling_does_not_reorder(store):
    leaf = {"scope": ["README.md"], "check": "true"}
    plan.propose(store, [{"id": "p", "title": "parent"}, {"id": "b", "title": "leaf b", **leaf}], ALEX)
    plan.propose(store, [{"id": "c", "title": "leaf c", "parent": "p", **leaf}], ALEX)  # c after b
    seqs = store.node_seqs()
    text, opened = T.render(store)  # p, c under it, then b: depth-first is not the order they were added
    said = T.apply(store, text.replace("check: true", "check: test -f README.md", 1), ALEX, opened)
    assert said == ["c: check changed"]
    assert store.node_seqs() == seqs and store.node_log("*") == []
    assert [n.id for n in plan.ready(plan.nodes(store))] == ["b", "c"]


# finding 7 (partly)
def test_an_owner_with_spaces_or_a_line_break_round_trips_unchanged(store):
    plan.propose(store, [
        {"id": "a", "title": "A", "scope": ["README.md"], "check": "true", "owner": " bob\nsmith "},
        {"id": "b", "title": "B", "scope": ["src/**"], "check": "true"},
    ], ALEX)  # fmt: skip
    text, opened = T.render(store)
    assert "    owner: bob smith\n" in text
    assert T.apply(store, text.replace("- B  [b]", "- B2  [b]"), ALEX, opened) == ["b: title changed"]
    assert (plan.get(store, "a").owner, plan.get(store, "a").rev) == ("bob smith", 1)


# finding 8 (fixed)
def test_a_dropped_node_is_refused_before_its_text_is_opened(store):
    plan.propose(store, [{"id": "a", "title": "leaf a", "scope": ["README.md"], "check": "true"}], ALEX)
    plan.drop(store, "a", ALEX)
    for alone in (False, True):
        with pytest.raises(
            Refused, match=r"^a is dropped; there is nothing of it to edit \(`graphene plan undo`"
        ):
            T.render(store, "a", alone)


# finding 9 (fixed)
def test_a_text_saved_with_a_byte_order_mark_applies(store, repo):
    from contextlib import nullcontext

    T.apply(store, "- leaf a  [a]\n    scope: README.md\n    check: true\n", ALEX, None)
    text, opened = T.render(store)
    edited = "﻿" + text.replace("check: true", "check: test -f README.md")
    assert T.apply(store, edited, ALEX, opened) == ["a: check changed"]

    def editor(path):  # Notepad's "UTF-8 with BOM"
        path.write_bytes(
            b"\xef\xbb\xbf" + path.read_bytes().replace(b"README.md\n", b"README.md, src/**\n", 1)
        )
        return 0

    said = T.edit_loop(lambda: nullcontext(store), None, False, ALEX, [], repo / "e.txt", "the plan", editor,
                       interactive=False)  # fmt: skip
    assert list(said) == ["a: scope changed"] and plan.get(store, "a").scope == ["README.md", "src/**"]


# finding 10 (fixed)
@pytest.mark.parametrize(
    "key", ["depends on", "requires", "depends_on", "blocked by", "waits on", "blocked_by"]
)
def test_a_dependency_said_in_other_words_is_a_need_not_a_description(store, key):
    two = "- render  [render]\n    scope: src/pdf/**\n    check: true\n- ship it  [ship]\n    scope: C.md\n    check: true\n"
    T.apply(store, two + f"    {key}: render\n", BOT, None)
    plan.accept(store, [], ALEX)
    ship = plan.get(store, "ship")
    assert (ship.needs, ship.goal) == (["render"], "")
    assert [n.id for n in plan.ready(plan.nodes(store))] == ["render"]


# finding 11 (fixed)
@pytest.mark.parametrize("key", ["sign-off", "Sign-off", "sign off", "sign_off"])
def test_sign_off_spelled_as_the_product_spells_it_keeps_the_gate(store, key):
    T.apply(store, f"- render  [render]\n    scope: src/pdf/**\n    check: true\n    {key}: yes\n", BOT, None)
    render = plan.get(store, "render")
    assert (render.signoff, render.goal) == (True, "")
    text, opened = T.render(store)  # and a person adding it in an edit keeps it too
    T.apply(store, text.replace("    signoff: yes\n", ""), ALEX, opened)
    text, opened = T.render(store)
    assert T.apply(store, text + f"    {key}: yes\n", ALEX, opened) == ["render: signoff changed"]
    assert plan.get(store, "render").signoff


# finding 12 (partly)
def test_a_key_written_with_equals_bold_or_as_a_bullet_is_the_key_and_a_near_miss_is_refused_by_line(store):
    for k, body in enumerate(["scope = src/pdf/**\n    check = true", "**Scope:** src/pdf/**\n    **Check:** true",
                              "- scope: src/pdf/**\n    - check: true"]):  # fmt: skip
        T.apply(store, f"- render  [r{k}]\n    {body}\n", BOT, None)
        node = plan.get(store, f"r{k}")
        assert (node.scope, node.check, node.goal) == (["src/pdf/**"], "true", "")
    for near, key, no in (
        ("Paths", "scope", 2),
        ("files", "scope", 2),
        ("checks", "check", 3),
        ("Tests", "check", 3),
    ):
        body = (
            f"    {near}: src/pdf/**\n    check: true\n"
            if key == "scope"
            else f"    scope: x\n    {near}: true\n"
        )
        with pytest.raises(Refused, match=rf"line {no}: '{near.lower()}:' is not read; say it with {key}:"):
            T.apply(store, "- render  [bad]\n" + body, BOT, None)


# finding 13 (fixed)
def test_a_yaml_list_under_an_empty_scope_or_needs_is_its_values_not_child_nodes(store):
    said = T.apply(store, "- render  [render]\n    scope:\n      - src/pdf/**\n      - tests/pdf/**\n"
                          "    check: true\n- ship it  [ship]\n    scope: C.md\n    check: true\n"
                          "    needs:\n      - render\n", BOT, None)  # fmt: skip
    assert said == ["proposed render: render", "proposed ship: ship it"]
    assert plan.get(store, "render").scope == ["src/pdf/**", "tests/pdf/**"]
    ship = plan.get(store, "ship")
    assert (ship.parent, ship.needs) == (None, ["render"])
    plan.accept(store, [], ALEX)
    assert [n.id for n in plan.ready(plan.nodes(store))] == ["render"]


# finding 14 (fixed)
def test_bullets_under_a_leaf_are_its_keys_or_refused_never_contractless_children(store):
    said = T.apply(
        store, "- **Render one invoice** [render]\n  - Scope: src/pdf/**\n  - Check: true\n", BOT, None
    )
    assert said == ["proposed render: **Render one invoice**"]
    render = plan.get(store, "render")
    assert (render.scope, render.check) == (["src/pdf/**"], "true")
    criteria = "- ship it  [ship]\n    scope: C.md\n    check: true\n    - handles multi-page invoices\n"
    for who in (BOT, ALEX):  # under a leaf with a contract, a person's title-only line is refused too
        with pytest.raises(Refused, match=r"line 4: 'handles multi-page invoices' is a new leaf with no scope "
                                          r"and no check.*\[ship\] should achieve.*without its '- '"):  # fmt: skip
            T.apply(store, criteria, who, None)
    with pytest.raises(Refused, match=r"line 5: 'scope: C.md' is not indented under"):  # criteria first
        T.apply(store, "- ship it  [ship]\n    Acceptance criteria:\n    - handles it\n    - fonts\n"
                       "    scope: C.md\n    check: true\n", BOT, None)  # fmt: skip
    assert [n.id for n in plan.nodes(store)] == ["render"]


# finding 15 (fixed)
def test_a_contract_at_the_childs_own_column_is_refused_not_given_to_its_parent(store):
    for text in (
        "- pdf  [pdf]\n  - render  [render]\n  scope: src/pdf/**\n  check: true\n",
        "- pdf  [pdf]\n    - render  [render]\n\tscope: src/pdf/**\n\tcheck: true\n",  # a Tab reads as 4
    ):
        with pytest.raises(Refused, match=r"line 3: 'scope: src/pdf/\*\*' is not indented under \[render\]"):
            T.apply(store, text, BOT, None)
    assert plan.nodes(store) == []


# finding 16 (fixed)
def test_a_numbered_line_with_an_id_is_a_node_and_without_one_says_what_its_node_is_for(store):
    with pytest.raises(Refused, match=r"line 4: '1\. render  \[render\]' does not line up with \[pdf\]'s other "
                                      r"lines.*a numbered line is not a node"):  # fmt: skip
        T.apply(store, "- pdf  [pdf]\n    1. read the spec\n    2. then write it\n  1. render  [render]\n"
                       "      scope: src/pdf/**\n      check: true\n", BOT, None)  # fmt: skip
    assert plan.nodes(store) == []
    T.apply(store, "- pdf  [pdf]\n    1. read the spec\n    2) then write it\n  - render  [render]\n"
                   "      scope: src/pdf/**\n      check: true\n", BOT, None)  # fmt: skip
    pdf, render = plan.get(store, "pdf"), plan.get(store, "render")
    assert (pdf.goal, pdf.scope, pdf.check) == ("1. read the spec\n2) then write it", [], None)
    assert (render.parent, render.scope) == ("pdf", ["src/pdf/**"])
    assert [n.id for n in plan.nodes(store)] == ["pdf", "render"]


# finding 17 (partly)
def test_an_id_written_first_or_followed_by_a_colon_or_a_note_is_the_id_and_a_bad_one_is_refused(store):
    T.apply(store, "- [WIP] first form\n    scope: a/**\n    check: true\n- second form  [b]:\n    scope: b/**\n"
                   "    check: true\n- third form  [c] (optional)\n    scope: c/**\n    check: true\n", BOT, None)  # fmt: skip
    assert [(n.id, n.title) for n in plan.nodes(store)] == [
        ("wip-first-form", "[WIP] first form"), ("b", "second form"), ("c", "third form (optional)")
    ]  # fmt: skip
    with pytest.raises(Refused) as no:
        T.apply(store, "- render one invoice  [pdf/render]\n    scope: src/**\n    check: true\n", BOT, None)
    assert "line 1: [pdf/render] is not an id" in str(no.value)
    T.apply(store, "- render one invoice  [render invoice]\n    scope: src/**\n    check: true\n", BOT, None)
    assert plan.nodes(store)[-1].title == "render one invoice  [render invoice]"


# finding 18 (partly)
def test_a_quoted_check_or_scope_is_read_without_its_quotes_and_none_is_no_check(store):
    T.apply(store, "- render  [r]\n    scope: \"src/pdf/**\", 'tests/pdf/**'\n    check: \"pytest tests/pdf\"\n"
                   "- lint  [lint]\n    scope: lint/**\n    check: `ruff check lint`\n"
                   "- review the copy  [copy]\n    scope: README.md\n    check: none\n    signoff: yes\n", BOT, None)  # fmt: skip
    r, lint, copy = plan.get(store, "r"), plan.get(store, "lint"), plan.get(store, "copy")
    assert (r.scope, r.check, lint.check) == (
        ["src/pdf/**", "tests/pdf/**"],
        "pytest tests/pdf",
        "ruff check lint",
    )
    assert (copy.check, copy.signoff) == (None, True)  # sign-off only, as the text meant
    # backticks around a glob are markdown: read without them (a glob stored with one is refused)
    T.apply(store, "- render again  [pdf]\n    scope: `src/pdf/**`\n    check: true\n", BOT, None)
    assert plan.get(store, "pdf").scope == ["src/pdf/**"]
    with pytest.raises(Refused, match="is not a path"):
        plan.propose(store, [{"id": "q", "title": "q", "scope": ["`x`"], "check": "true"}], ALEX)


# finding 19 (fixed)
def test_a_brace_glob_is_refused_by_its_line_not_split_at_its_comma(store):
    with pytest.raises(Refused, match=r"line 2: braces are not read in a scope"):
        T.apply(store, "- render  [render]\n    scope: src/pdf/**/*.{py,html}\n    check: true\n", BOT, None)
    assert plan.nodes(store) == []


# finding 20 (fixed)
def test_an_inline_comment_after_a_scope_or_needs_is_a_comment_not_more_paths(store):
    T.apply(store, "- set up CI  [ci]\n    scope: .github/**\n    check: true\n"
                   "- render one invoice  [render]\n    scope: src/pdf/**  # the renderer only\n"
                   "    check: true\n    needs: ci  # after CI\n", ALEX, None)  # fmt: skip
    render = plan.get(store, "render")
    assert (render.scope, render.needs) == (["src/pdf/**"], ["ci"])
    assert not plan.in_scope("the/x.py", render.scope)  # the comment's words are not globs


# finding 21 (fixed)
def test_a_markdown_heading_is_refused_rather_than_dropped_and_the_tree_flattened(store):
    text = ("goal: invoices as PDF\n\n## The PDF renderer\n- render one invoice  [render]\n"
            "    scope: src/pdf/**\n    check: true\n")  # fmt: skip
    for who in (ALEX, BOT):
        with pytest.raises(Refused, match=r"^line 3: a heading is not read; a sub-goal is a '- ' line"):
            T.apply(store, text, who, None)
    assert plan.nodes(store) == []
    T.apply(store, text.replace("## The PDF renderer", "# a note"), BOT, None)  # "# " is still a note
    assert [n.id for n in plan.nodes(store)] == ["render"]


# finding 22 (fixed)
def test_a_refusal_names_the_line_of_the_node_it_is_about_not_an_earlier_id_it_mentions(store):
    text = ("- set up CI  [check]\n    scope: .github/**\n    check: true\n"
            "- render one invoice  [render]\n    scope: src/pdf/**\n")  # fmt: skip
    with pytest.raises(Refused, match=r"^line 4 \[render\]: render: a leaf needs a check") as no:
        T.apply(store, text, ALEX, None)
    assert T._annotated(text, str(no.value)).splitlines()[4].startswith("# ^ refused: render:")
    both = "- render  [render]\n    scope: a/**\n    check: true\n- tpl  [template]\n    scope: {}\n    check: true\n"
    with pytest.raises(
        Refused, match=r"^line 4 \[template\]: template: `Templates/render\.html` matches nothing"
    ):
        T.apply(store, both.format("Templates/render.html"), BOT, None, files=["templates/render.html"])
    assert plan.nodes(store) == []
    T.apply(store, both.format("t/**") + "    needs: [render]\n", BOT, None)  # an [id] in needs: is the id
    assert plan.get(store, "template").needs == ["render"]


# finding 23 (fixed)
def test_a_code_fence_around_the_text_or_a_byte_order_mark_before_it_is_read_past(store):
    body = "goal: invoices as PDF\n- render one invoice  [render]\n    scope: src/pdf/**\n    check: true\n"
    for text in ("```text\n" + body + "```\n", "﻿" + body):
        goal, lines = T.parse(text)
        assert (goal, [(ln.id, ln.scope, ln.check) for ln in lines]) == (
            "invoices as PDF",
            [("render", ["src/pdf/**"], "true")],
        )
    T.apply(store, "﻿```\n" + body + "```\n", BOT, None)
    assert plan.get(store, "render").state == plan.PROPOSED


# finding 24 (fixed)
def test_a_goal_indented_or_written_on_the_line_after_its_key_is_read_as_the_goal(store):
    indented = (
        "  goal: invoices as PDF\n  - render one invoice  [render]\n      scope: a/**\n      check: true\n"
    )
    below = "goal:\n  invoices as PDF\n- render one invoice  [render]\n    scope: a/**\n    check: true\n"
    for text in (indented, below):
        goal, lines = T.parse(text)
        assert (goal.strip(), [ln.id for ln in lines]) == ("invoices as PDF", ["render"])
    plan.set_goal(store, "line one\nline two", ALEX)  # a goal of two lines reads back as it was
    text, opened = T.render(store)
    assert T.parse(text)[0] == "line one\nline two" and T.apply(store, text, ALEX, opened) == []


# finding 25 (partly)
def test_a_tag_repeated_at_the_end_of_two_lines_is_refused_as_one_id_not_as_a_copy(store):
    text = "- parse args [P1]\n    scope: README.md\n    check: true\n- add tests [P1]\n    scope: README.md\n    check: true\n"
    with pytest.raises(
        Refused, match=r"line 4: \[P1\] is on line 1 too\. An \[id\] at the end of a line names one node"
    ) as no:
        T.apply(store, text, BOT, None)
    assert "copied" not in str(no.value) and plan.nodes(store) == []


# finding 26 (fixed)
def test_an_agent_cannot_reserve_its_leaf_for_a_person_by_writing_its_own_name_as_owner(store):
    leaf = "- render one invoice  [render]\n    scope: README.md\n    check: true\n    owner: {}\n"
    for name in ("claude", BOT.name):
        with pytest.raises(Refused, match=r"line 1: owner: names a person, and '.+' is not the person here"):
            T.apply(store, leaf.format(name), BOT, None)
    assert plan.nodes(store) == []
    T.apply(store, leaf.format("agent"), BOT, None)
    plan.accept(store, [], ALEX)
    assert [n.id for n in plan.ready(plan.nodes(store), BOT)] == ["render"]


# finding 27 (fixed)
def test_a_markdown_checkbox_before_a_title_is_not_part_of_it(store):
    T.apply(store, "- [ ] render one invoice  [render]\n    scope: README.md\n    check: true\n"
                   "* [x] write the README\n    scope: README.md\n    check: true\n", BOT, None)  # fmt: skip
    assert [(n.id, n.title) for n in plan.nodes(store)] == [
        ("render", "render one invoice"),
        ("write-readme", "write the README"),
    ]


# finding 28 (partly)
def test_deleting_only_a_leafs_line_never_gives_its_scope_and_check_to_the_sub_goal_above(store):
    T.apply(store, TREE.replace("      needs: render\n", ""), ALEX, None)
    text, opened = T.render(store)
    with pytest.raises(
        Refused,
        match=r"^line 6: 'scope: src/pdf/\*\*, tests/pdf/\*\*' is 6 columns in from \[pdf\]; .* If they were "
        r"a node's whose line you deleted, delete them too",
    ):
        T.apply(store, text.replace("  - render one invoice to PDF bytes  [render]\n", ""), ALEX, opened)
    pdf, render = plan.get(store, "pdf"), plan.get(store, "render")
    assert (pdf.scope, pdf.check, render.state) == ([], None, OPEN)


# finding 29 (changed-behaviour-ok)
def test_deleting_a_sub_goals_line_alone_does_not_hang_its_children_on_the_leaf_above(store):
    docs = "- say so in the README  [docs]\n    scope: README.md\n    check: true\n"
    T.apply(store, docs + TREE.split("\n\n", 1)[1].split("- say so")[0], ALEX, None)
    text, opened = T.render(store)
    with pytest.raises(
        Refused, match=r"\[render\]'s parent \[pdf\] was deleted, and \[render\] would now be under docs"
    ):
        T.apply(store, text.replace("- the PDF renderer  [pdf]\n", ""), ALEX, opened)
    assert [(n.id, n.parent, n.state) for n in plan.nodes(store)][1:] == [
        ("pdf", None, OPEN), ("render", "pdf", OPEN), ("template", "pdf", OPEN),
    ]  # fmt: skip
    assert "docs" in [n.id for n in plan.ready(plan.nodes(store), BOT)]  # still a leaf anyone may take


# finding 30 (partly)
def test_a_child_typed_under_its_parents_title_does_not_take_the_parents_lines(store):
    T.apply(store, "- the PDF renderer  [pdf]\n    all PDF output in one place\n    needs: docs\n"
            "    signoff: yes\n  - render one invoice  [render]\n      scope: src/pdf/**\n      check: true\n"
            "- say so in the README  [docs]\n    scope: README.md\n    check: true\n", ALEX, None)  # fmt: skip
    text, opened = T.render(store)
    for child in (
        "  - embed the fonts\n      scope: src/fonts/**\n      check: true\n",
        "  - embed the fonts\n",
    ):
        with pytest.raises(Refused):
            T.apply(store, text.replace("[pdf]\n", "[pdf]\n" + child, 1), ALEX, opened)
    pdf = plan.get(store, "pdf")
    assert (pdf.goal, pdf.needs, pdf.signoff) == ("all PDF output in one place", ["docs"], True)
    assert "embed-fonts" not in {n.id for n in plan.nodes(store)}


# finding 31 (partly)
def test_undo_of_an_added_node_is_refused_while_an_agents_proposal_hangs_under_it(store):
    T.apply(store, "- docs  [docs]\n    scope: README.md\n    check: true\n", ALEX, None)
    text, opened = T.render(store)
    with plan.undoable(store, ALEX, "plan edit"):
        T.apply(store, text + "- ship the release  [rel]\n", ALEX, opened)
    T.apply(
        store,
        "- ship the release  [rel]\n  ? tag it  [tag]\n      scope: CHANGELOG.md\n      check: true\n",
        BOT,
        None,
    )
    with pytest.raises(Refused, match="tag"):
        plan.undo(store, ALEX)
    plan.validate(plan.nodes(store))  # never a plan that refuses every later add or edit
    assert plan.get(store, "rel").state == OPEN


# finding 32 (fixed)
def test_a_planners_goal_stays_a_proposal_until_the_person_accepts_some_of_its_tree(store):
    T.apply(
        store,
        "goal: invoices as PDF\n\n- say so in the README  [docs]\n    scope: README.md\n    check: true\n",
        BOT,
        None,
    )
    text, opened = T.render(store)
    T.apply(store, text.replace("scope: README.md", "scope: README.md, docs/**"), ALEX, opened)
    assert (plan.goal(store), store.meta("goal:proposed")) == ("", "invoices as PDF")
    text, opened = T.render(store)
    T.apply(store, text.split("? say so")[0], ALEX, opened)  # the whole tree deleted, its goal line kept
    assert (plan.goal(store), store.meta("goal:proposed"), plan.get(store, "docs").state) == (
        "",
        None,
        DROPPED,
    )


# finding 33 (fixed)
def test_a_goal_with_line_breaks_round_trips_and_an_edit_elsewhere_leaves_it(store):
    T.apply(store, TREE, ALEX, None)
    for k, goal in enumerate(
        ("invoices as PDF.\nThey asked in March.", "invoices as PDF:\n- no email attachments yet")
    ):
        plan.set_goal(store, goal, ALEX)
        for root, parent, alone in ((None, None, False), ("pdf", None, False), ("template", "pdf", True)):
            text, opened = T.render(store, root, alone)
            assert T.apply(store, text, ALEX, opened, parent) == []
        text, opened = T.render(store)
        edited = text.replace("scope: README.md", f"scope: README.md, d{k}/**")
        assert T.apply(store, edited, ALEX, opened) == ["docs: scope changed"]
        assert plan.goal(store) == goal
    assert "no-email-attachments" not in {n.id for n in plan.nodes(store)}


# finding 34 (fixed)
def test_node_edit_alone_refuses_to_drop_a_sub_goal_whose_children_it_did_not_show(store, repo):
    from test_plan_text import TREE

    T.apply(store, TREE, ALEX, None)
    plan.start(store, "render", BOT, repo)
    text, opened = T.render(store, "pdf", alone=True)
    assert "[render]" not in text
    with pytest.raises(Refused, match="render, template"):
        T.apply(store, "- the PDF output\n", ALEX, opened)  # its one line retyped
    assert [(n.id, n.state) for n in plan.nodes(store)] == [
        ("pdf", OPEN), ("render", plan.RUNNING), ("template", OPEN), ("docs", OPEN)
    ]  # fmt: skip


# finding 35 (partly)
def test_deleting_the_line_of_a_node_that_moved_on_since_it_was_opened_is_refused(store, repo):
    from test_plan_text import shaped, without

    text, opened = shaped(store)
    plan.edit(store, "template", {"scope": ["templates/**"]}, plan.Caller("sam", True))  # changed meanwhile
    plan.start(store, "docs", BOT, repo)  # taken meanwhile
    for gone, now in (("template", "open"), ("docs", "running")):
        with pytest.raises(
            Refused,
            match=rf"\[{gone}\], whose lines were deleted, was changed by someone else since this text was "
            rf"opened \(it was open, it is {now} now\)",
        ):
            T.apply(store, without(text, gone), ALEX, opened)
    assert (plan.get(store, "template").state, plan.get(store, "docs").state) == (OPEN, plan.RUNNING)
    assert plan.get(store, "template").scope == ["templates/**"]


# finding 36 (partly)
def test_nodes_deleted_together_may_need_each_other_and_a_refusal_names_what_is_needed(store):
    from test_plan_text import shaped, without

    shaped(store)
    plan.edit(store, "docs", {"needs": ["render"]}, ALEX)
    text, opened = T.render(store)
    with pytest.raises(Refused, match=r"deleted lines: docs waits on render; change what it needs first"):
        T.apply(store, without(text, "pdf"), ALEX, opened)  # docs stays, and needs what goes with pdf
    assert {n.state for n in plan.nodes(store)} == {OPEN}  # the refusal applied nothing
    # template needs render and docs needs render: all deleted in one save, checked as one set
    said = T.apply(store, without(without(text, "pdf"), "docs"), ALEX, opened)
    assert said == [
        "dropped pdf: the PDF renderer",
        "dropped docs: say so in the README",
    ]  # render and template went with pdf
    assert {n.state for n in plan.nodes(store)} == {DROPPED}


# finding 37 (fixed)
def test_a_leaf_split_into_children_hands_them_its_scope_and_check(store):
    from test_plan_text import shaped

    text, opened = shaped(store)
    split = text.replace(  # the note under it is its state, as the screen says it
        "- say so in the README  [docs]\n    # ready\n    scope: README.md\n    check: true\n",
        "- say so in the README  [docs]\n  - the PDF section\n      scope: README.md\n"
        "      check: grep -q PDF README.md\n  - the changelog\n      scope: CHANGELOG.md\n      check: true\n",
    )
    assert split != text
    T.apply(store, split, ALEX, opened)
    docs = plan.get(store, "docs")
    assert (docs.scope, docs.check) == ([], None)
    assert [(n.id, n.scope) for n in plan.kids(plan.nodes(store))["docs"]] == [
        ("pdf-section", ["README.md"]),
        ("changelog", ["CHANGELOG.md"]),
    ]


# finding 38 (fixed)
def test_a_new_sub_goal_with_a_check_wraps_existing_nodes_in_one_save(store):
    from test_plan_text import shaped

    text, opened = shaped(store)
    wrapped = text.replace(  # the note under it is its state, as the screen says it
        "- say so in the README  [docs]\n    # ready\n    scope: README.md\n    check: true\n",
        "- ship the docs\n    check: test -f README.md\n"
        "  - say so in the README  [docs]\n      scope: README.md\n      check: true\n",
    )
    said = T.apply(store, wrapped, ALEX, opened)
    assert "added ship-docs: ship the docs" in said and plan.get(store, "docs").parent == "ship-docs"
    ship = plan.get(store, "ship-docs")
    assert (ship.scope, ship.check) == ([], "test -f README.md")
    with pytest.raises(
        Refused, match=r"lonely: a leaf needs a scope"
    ):  # a new line with no children is a leaf
        T.apply(store, "- lonely\n    check: true\n", ALEX, None)


# finding 39 (fixed)
def test_a_line_whose_node_was_dropped_while_the_text_was_open_is_to_be_deleted_not_re_added(store):
    shaped(store)
    T.apply(store, "? an FAQ  [faq]\n    scope: docs/faq.md\n    check: true\n", BOT, None)
    text, opened = T.render(store)
    plan.drop(store, "faq", BOT)  # the agent withdraws its proposal meanwhile
    edited = text.replace("scope: README.md", "scope: README.md, docs/**")
    with pytest.raises(Refused, match=r"\[faq\] was dropped since this text was opened; delete its line"):
        T.apply(store, edited, ALEX, opened)
    T.apply(store, without(edited, "faq"), ALEX, opened)
    assert plan.get(store, "docs").scope == ["README.md", "docs/**"]
    assert not [n for n in plan.nodes(store) if n.id.startswith("faq-")]  # nothing brought back
    with pytest.raises(Refused, match=r"faq is dropped; there is nothing of it to edit"):
        T.render(store, "faq")


# finding 40 (fixed)
def test_two_edits_open_at_once_each_read_their_own_file(store, repo):
    shaped(store)
    before = T.render(store)[0]

    def loop(node, editor):
        path = T.edit_path(repo, node)
        return T.edit_loop(lambda: store_ctx(store), node, node is not None, ALEX, [], path, "x", editor)

    def whole(p):  # while the whole plan is open, `node edit docs` opens and quits in another terminal
        assert loop("docs", lambda q: 0) == []
        return 0  # then this one quits without saving too

    assert loop(None, whole) == [] and T.render(store)[0] == before  # quitting applied nothing
    with pytest.raises(Refused, match="is gone; nothing was applied"):
        loop(None, lambda p: p.unlink() or 0)


# finding 41 (fixed)
def test_a_text_kept_after_a_refusal_is_not_written_over_by_the_next_edit(store, repo, monkeypatch):
    shaped(store)
    kept = T.edit_path(repo, None)

    def bad(p):
        p.write_text(p.read_text().replace("scope: README.md", "scope: README.md\n    signoff: maybe"))
        return 0

    with pytest.raises(Refused, match="your text is kept in"):
        T.edit_loop(lambda: store_ctx(store), None, False, ALEX, [], kept, "x", bad, interactive=False)
    monkeypatch.setattr(T.os, "getpid", lambda: 1)  # the next `plan edit` is another process
    again = T.edit_path(repo, None)
    assert T.edit_loop(lambda: store_ctx(store), None, False, ALEX, [], again, "x", lambda p: 0) == []
    assert "signoff: maybe" in kept.read_text() and not again.exists()


# finding 42 (partly)
def test_after_a_node_moved_on_the_next_save_makes_the_persons_change(store, repo, tmp_path):
    shaped(store)
    opens = []

    def editor(p):
        text = p.read_text()
        opens.append(text)
        if len(opens) == 1:
            plan.edit(store, "docs", {"scope": ["README.md", "docs/**"]}, ALEX)  # another terminal, meanwhile
            p.write_text(text.replace("README.md\n    check: true", "README.md\n    check: false"))
        elif len(opens) < 4:
            assert "[docs] was changed by someone else" in text
            p.write_text("".join(line for line in text.splitlines(True) if "# ^ refused" not in line))
        return 0

    T.edit_loop(lambda: store_ctx(store), None, False, ALEX, [], tmp_path / "e.txt", "x", editor)
    assert len(opens) == 2 and plan.get(store, "docs").check == "false"


# finding 43 (fixed)
def test_a_goal_set_elsewhere_meanwhile_is_not_written_over_by_a_save(store):
    shaped(store)
    text, opened = T.render(store)
    plan.set_goal(store, "invoices as PDF and CSV", ALEX)  # another terminal, while the text is open
    T.apply(store, text.replace("README.md\n    check: true", "README.md\n    check: false"), ALEX, opened)
    assert plan.goal(store) == "invoices as PDF and CSV" and plan.get(store, "docs").check == "false"
    with pytest.raises(Refused, match="goal was changed by someone else since this text was opened"):
        T.apply(store, text.replace("goal: customers", "goal: all customers"), ALEX, opened)


# finding 44 (fixed)
def test_a_save_that_accepts_none_of_an_agents_tree_leaves_its_goal_the_agents(store):
    from test_plan_text import TREE

    T.apply(store, TREE, BOT, None)
    text, opened = T.render(store)
    T.apply(store, text.replace("the invoice template", "the invoice layout"), ALEX, opened)
    assert plan.goal(store) == "" and len(plan.nodes(store, (PROPOSED,))) == 4  # retitled, not accepted
    text, opened = T.render(store)
    goal_only = "".join(ln for ln in text.splitlines(True) if ln.startswith(("goal:", "#")))
    said = T.apply(store, goal_only, ALEX, opened)
    assert said and all(s.startswith("dropped") for s in said)
    assert plan.goal(store) == "" and store.meta("goal:proposed") is None  # it went with its tree


# finding 45 (partly)
def test_deleting_the_lines_of_a_node_that_moved_on_since_the_text_was_opened_is_refused(store, repo):
    T.apply(store, "goal: g\n- the API  [api]\n  - users returns ids  [ids]\n      scope: src/api/**\n"
            "      check: true\n- docs  [docs]\n    scope: README.md\n    check: true\n", ALEX, None)  # fmt: skip
    text, opened = T.render(store)
    # while the text is open, an agent proposes under [api] and starts [ids]
    plan.propose(store, [{"id": "cache", "title": "a cache", "parent": "api", "scope": ["src/db/**"],
                          "check": "true"}], BOT)  # fmt: skip
    plan.start(store, "ids", BOT, repo)
    api, ids, docs = (text.index(f"[{i}]") for i in ("api", "ids", "docs"))
    cut = lambda a, b: text[: text.rindex("\n", 0, a) + 1] + text[text.rindex("\n", 0, b) + 1 :]  # noqa: E731
    with pytest.raises(
        Refused, match=r"\[api\], whose lines were deleted, has cache under it, which this text"
    ):
        T.apply(store, cut(api, docs), ALEX, opened)  # [cache] was never in the text: not dropped unseen
    with pytest.raises(
        Refused,
        match=r"\[ids\], whose lines were deleted, was changed by someone else since this text was opened"
        r" \(it was open, it is running now\)",
    ):
        T.apply(store, cut(ids, docs), ALEX, opened)
    assert (plan.get(store, "cache").state, plan.get(store, "ids").state) == (PROPOSED, RUNNING)
    assert plan.get(store, "ids").executor == BOT.label


# finding 46 (partly)
def test_plan_edit_with_nobody_at_a_terminal_is_refused_at_once_and_spawns_no_editor(
    repo, monkeypatch, tmp_path
):
    import os

    from test_plan_cli import AGENT_ENV, agent, runner

    from graphene_debrief.cli import build

    for name in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "AI_AGENT", "GRAPHENE_AS", "GITHUB_ACTIONS",
                 "CODEX_SESSION_ID", "CODEX_SANDBOX", "EDITOR", "VISUAL", *plan.AGENT_MARKS):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.chdir(repo)  # the CLI finds its plan from where it runs: this repo's, never the checkout's
    spawned, vi = tmp_path / "spawned", tmp_path / "bin" / "vi"
    vi.parent.mkdir()
    vi.write_text(f"#!/bin/sh\ntouch {spawned}\n")  # a stand-in vi: says it ran, instead of waiting for ever
    vi.chmod(0o755)
    monkeypatch.setenv("PATH", f"{vi.parent}{os.pathsep}{os.environ['PATH']}")
    proposed = agent("plan", "propose", "-", input="- the API  [api]\n    scope: api.py\n    check: true\n")
    assert proposed.exit_code == 0, proposed.output
    for env, says in (
        (AGENT_ENV, "an agent proposes: `graphene plan propose -`"),
        ({"GRAPHENE_AS": "person:alex"}, "vi needs a terminal, and there is none here"),
    ):
        result = runner.invoke(build(), ["plan", "edit"], env=env)
        assert result.exit_code == 1 and says in result.stderr, result.output
    assert not spawned.exists()


# finding 47 (fixed)
def test_an_editor_that_cannot_be_started_is_refused_in_one_line(store, tmp_path, monkeypatch):
    import contextlib
    import re

    T.apply(store, "- docs  [docs]\n    scope: README.md\n    check: true\n", ALEX, None)
    monkeypatch.delenv("VISUAL", raising=False)
    for editor, why in (("nano-not-installed", "No such file"), ("vim -c 'set tw=0", "No closing quotation"),
                        ("~/bin/myeditor", "No such file")):  # fmt: skip
        monkeypatch.setenv("EDITOR", editor)
        with pytest.raises(
            Refused, match=rf"cannot run your editor \({re.escape(editor)}\): {why}.*; set \$EDITOR"
        ):
            T.edit_loop(lambda: contextlib.nullcontext(store), None, False, ALEX, [], tmp_path / "e.txt", "x")
    assert plan.get(store, "docs").state == OPEN


# finding 48 (fixed)
def test_the_undo_record_is_taken_under_the_write_lock_so_an_agents_start_is_never_in_it(store, repo):
    import sqlite3

    T.apply(store, "- docs  [docs]\n    scope: README.md\n    check: true\n"
            "- ids  [ids]\n    scope: src/api/**\n    check: true\n", ALEX, None)  # fmt: skip
    with plan.undoable(store, ALEX, "plan edit"):
        with pytest.raises(sqlite3.OperationalError, match="locked"), Store.open(repo, quick=True) as other:
            plan.start(other, "ids", BOT, repo)  # an agent's start cannot land inside the person's act
        plan.edit(store, "docs", {"check": "test -f README.md"}, ALEX)
    plan.start(store, "ids", BOT, repo)
    assert plan.undo(store, ALEX) == "plan edit"
    assert plan.get(store, "docs").check == "true"
    assert (plan.get(store, "ids").state, plan.get(store, "ids").executor) == (RUNNING, BOT.label)


# -- what the hunt for the second pass's regressions found -------------------------------------------


def test_a_link_in_the_note_after_an_id_keeps_the_id_and_the_node(store, repo):
    T.apply(store, "- fix login  [login]\n    scope: auth/**\n    check: true\n", ALEX, None)
    plan.start(store, "login", BOT, repo)
    text, opened = T.render(store)
    noted = text.replace("- fix login  [login]", "- fix login  [login] (see https://github.com/o/r/issues/7)")
    said = T.apply(store, noted, ALEX, opened)
    assert said == ["login: title changed"] and plan.get(store, "login").state == RUNNING
    assert plan.get(store, "login").title == "fix login (see https://github.com/o/r/issues/7)"
    assert T.parse("- read [the docs](http://x.y)\n")[1][0].title == "read [the docs](http://x.y)"


def test_a_description_written_after_goal_and_then_plain_round_trips(store):
    plan.propose(store, [{"id": "a", "title": "a", "scope": ["a/**"], "check": "true",
                          "goal": "Steps:\n- parse the file\n- write the pdf\nKeep the API stable."}], ALEX)  # fmt: skip
    text, opened = T.render(store)
    assert "goal: - parse the file" in text
    assert T.apply(store, text, ALEX, opened) == []


def test_a_hash_inside_a_quoted_glob_or_after_an_owner_is_not_a_comment(store):
    plan.propose(store, [{"id": "a", "title": "a", "scope": ["docs/#1 notes/**"], "check": "true"}], ALEX)
    text, opened = T.render(store)
    assert T.apply(store, text, ALEX, opened) == []
    assert plan.get(store, "a").scope == ["docs/#1 notes/**"]
    with pytest.raises(Refused, match="an owner is a name"):
        plan.propose(
            store, [{"id": "o", "title": "o", "scope": ["o/**"], "check": "true", "owner": "team #2"}], ALEX
        )
    T.apply(store, "- c  [c]\n    scope: c/**\n    check: true\n    owner: me  # I do this one\n", ALEX, None)
    assert plan.get(store, "c").owner == "alex"
    T.apply(store, "- b  [b]\n    scope: src/c#/**, docs/x  # the docs\n    check: true\n", ALEX, None)
    assert plan.get(store, "b").scope == ["src/c#/**", "docs/x"]


def test_an_owner_in_another_case_is_the_one_it_names(store):
    T.apply(store, "- a  [a]\n    scope: a/**\n    check: true\n    owner: Agent\n"
                   "- b  [b]\n    scope: b/**\n    check: true\n    owner: Me\n", BOT, None)  # fmt: skip
    assert plan.get(store, "a").owner == plan.AGENT and plan.get(store, "b").owner == plan.person_name()


def test_undo_puts_back_a_sub_goal_whose_children_went_with_it(store):
    T.apply(store, TREE, ALEX, None)
    with plan.undoable(store, ALEX, "node drop pdf"):
        plan.drop(store, "pdf", ALEX)
    assert plan.undo(store, ALEX) == "node drop pdf"
    assert {plan.get(store, i).state for i in ("pdf", "render", "template")} == {OPEN}


def test_a_description_line_that_starts_like_a_fence_is_kept(store):
    plan.propose(store, [{"id": "a", "title": "a", "scope": ["a/**"], "check": "true",
                          "goal": "the layout:\n~~~ as drawn ~~~\nas designed"}], ALEX)  # fmt: skip
    text, opened = T.render(store)
    assert T.apply(store, text, ALEX, opened) == []


def test_a_bullet_with_an_id_is_a_node(store):
    T.apply(store, "- the PDF work  [pdf]\n  • render one invoice  [render]\n      scope: src/pdf/**\n"
                   "      check: true\n", BOT, None)  # fmt: skip
    assert plan.get(store, "render").parent == "pdf"


def test_an_id_dressed_in_markdown_is_the_id(store):
    T.apply(store, "- render one invoice  [`render`]\n    scope: src/pdf/**\n    check: true\n"
                   "- ship  [**ship**]\n    scope: s/**\n    check: true\n    needs: render\n", BOT, None)  # fmt: skip
    assert plan.get(store, "ship").needs == ["render"]


def test_two_edits_in_one_second_have_files_of_their_own(tmp_path):
    first, second = T.edit_path(tmp_path, "a"), T.edit_path(tmp_path, "a")
    assert first != second and first.exists() and second.exists()


def test_after_a_conflict_only_what_the_person_changed_wins(store, tmp_path):
    shaped(store)
    path, tries = tmp_path / "edit.txt", []

    def editor(p):
        text = p.read_text()
        tries.append(text)
        if len(tries) == 1:
            plan.edit(store, "docs", {"check": "make docs"}, ALEX)  # someone else, meanwhile
            p.write_text(text.replace("scope: README.md", "scope: README.md, docs/**"))
        else:
            p.write_text("\n".join(line for line in text.splitlines() if "# ^ refused" not in line) + "\n")
        return 0

    said = T.edit_loop(lambda: store_ctx(store), None, False, ALEX, [], path, "x", editor)
    docs = plan.get(store, "docs")
    assert "docs: scope changed" in said and (docs.scope, docs.check) == (
        ["README.md", "docs/**"],
        "make docs",
    )


def test_an_orphaned_description_deeper_than_its_node_is_refused_in_an_edit(store):
    T.apply(store, "- api  [api]\n    the public API\n  - users  [users]\n      returns ids\n"
                   "      scope: u/**\n      check: true\n", ALEX, None)  # fmt: skip
    text, opened = T.render(store)
    with pytest.raises(Refused, match="deeper than \\[api\\]'s other lines"):
        T.apply(store, "\n".join(line for line in text.splitlines() if "[users]" not in line
                                 and "scope: u/**" not in line and "check: true" not in line), ALEX, opened)  # fmt: skip


def test_a_dropped_id_given_a_new_one_takes_the_needs_that_name_it_along(store):
    """Recheck: asking again after a drop gave the reused [csv] a new id, but `needs: csv` on another
    line kept the dropped one, so the whole proposal was refused, twice, and nothing was added."""
    text = (
        "goal: csv export\n- the export  [export]\n  - csv writer  [csv]\n      scope: export.py\n"
        "      check: true\n  - document csv  [csv-docs]\n      scope: README.md\n      check: true\n"
        "      needs: csv\n"
    )
    T.apply(store, text, BOT, None)
    plan.drop(store, "export", ALEX)
    T.apply(store, text, BOT, None)  # the planner cannot see dropped ids, and proposes the same text
    alive = {n.id: n for n in plan.nodes(store) if n.state == PROPOSED}
    assert alive["document-csv"].needs == ["csv-writer"] and alive["csv-writer"].parent == "export-2"


def test_a_check_that_changes_directory_by_pushd_prefix_or_dash_c_is_not_judged(repo):
    """Recheck: only `cd` counted as a change of directory; these valid checks were said to name
    missing files."""
    for check in (
        "(pushd web; npx jest src/App.test.js)",
        "npm --prefix web test -- src/App.test.js",
        "make -C web test FILE=src/App.test.js",
    ):
        node = plan.Node("n", "t", scope=["lib/**"], check=check)
        assert plan.unreachable(node, ["web/src/App.test.js"], repo) == [], check


# -- the recheck of the closing review: its regression tests --------------------


# Recheck 45 (fixed)
def test_accepting_a_planners_tree_never_replaces_the_persons_own_goal(store):
    plan.set_goal(store, "my own goal: invoices as PDF", ALEX)
    T.apply(
        store,
        "goal: the planner's sentence\n- render one invoice  [render]\n    scope: src/**\n    check: true\n",
        BOT,
        None,
    )
    text, opened = T.render(store)
    assert T.apply(store, text.replace("? render", "- render"), ALEX, opened) == ["accepted render"]
    assert (plan.goal(store), store.meta("goal:proposed")) == ("my own goal: invoices as PDF", None)


# Recheck 46 (fixed)
def test_deleting_the_proposed_goal_line_declines_it_when_the_tree_is_accepted(store):
    T.apply(
        store,
        "goal: rewrite everything in Rust\n- render one invoice  [render]\n    scope: src/**\n    check: true\n",
        BOT,
        None,
    )
    text, opened = T.render(store)
    saved = "\n".join(line for line in text.splitlines() if not line.startswith("goal:")).replace(
        "? render", "- render"
    )
    assert T.apply(store, saved, ALEX, opened) == ["the proposed goal was dropped", "accepted render"]
    assert (plan.goal(store), store.meta("goal:proposed")) == ("", None)


# Recheck 47 (partly)
def test_a_dropped_trees_goal_is_not_adopted_when_another_planners_leaf_is_accepted(store):
    one, two = Caller("planner:one", False, "s-one"), Caller("planner:two", False, "s-two")
    T.apply(
        store,
        "goal: rewrite the importer in Rust\n- port the importer  [port]\n    scope: src/**\n    check: true\n",
        one,
        None,
    )
    T.apply(store, "- fix the date bug  [datefix]\n    scope: lib/**\n    check: true\n", two, None)
    plan.drop(store, "port", ALEX)
    plan.accept(store, ["datefix"], ALEX)
    assert plan.goal(store) == ""


# Recheck 57 (fixed)
def test_a_scope_written_from_the_root_of_the_disk_is_refused_when_it_is_written(store, repo):
    for glob in ("/src/**", f"{repo}/src/**", "!/src/api/x.py", "../src/**"):
        with pytest.raises(Refused, match="a scope is a path inside the repo"):
            plan.propose(store, [{"id": "x", "title": "x", "scope": ["src/**", glob], "check": "true"}], ALEX)
    with pytest.raises(Refused, match="a scope is a path inside the repo"):  # a planner's, from its Glob tool
        T.apply(store, f"? fix a  [fixa]\n    scope: {repo}/src/**\n    check: true\n", BOT, None)
    assert plan.nodes(store) == []


# Recheck 60 (fixed)
def test_an_undo_and_an_edit_meanwhile_are_not_written_over_by_a_text_left_open(store):
    plan.propose(store, [{"id": "x", "title": "x", "scope": ["src/**"], "check": "true"}], ALEX)
    with plan.undoable(store, ALEX, "node set x"):
        plan.edit(store, "x", {"scope": ["src/a/**"]}, ALEX)
    text, opened = T.render(store)  # opened at revision 2
    plan.undo(store, ALEX)  # another terminal: undo, then an edit of its own
    plan.edit(store, "x", {"scope": ["lib/**"]}, ALEX)
    with pytest.raises(Refused, match="changed by someone else"):
        T.apply(store, text.replace("scope: src/a/**", "scope: src/a/**, docs/**"), ALEX, opened)
    assert plan.get(store, "x").scope == ["lib/**"]
