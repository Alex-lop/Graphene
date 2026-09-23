# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""`graphene watch`: the plan on one screen, driven the way a person drives it, by keys, headless
(Textual's pilot) at 80 columns and at 120. Every key is a command: after each, the store says what
the command did, and the bottom line says which command it was."""

import asyncio
import sys

from test_plan_cli import agent, person, repo  # noqa: F401  (fixtures)

from graphene_debrief import plan
from graphene_debrief.store import Store
from graphene_debrief.tui import Watch

TREE = """\
goal: users come back with their ids
- the API  [api]
  - users returns ids  [ids]
      scope: api.py
      check: grep -q ids api.py
  - document it  [docs]
      scope: README.md
      check: test -f README.md
      needs: ids
- the schema  [schema]
    scope: schema.py
    check: true
"""


def watch(repo, keys, size=(80, 24), before=None):
    """Drive the screen with keys; returns what it showed at the end, and the app."""
    app = Watch(repo, lambda: Store.open(repo), every=60)

    async def go():
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            if before:
                await before(app, pilot)
            for key in keys:
                await pilot.press(key)
                await pilot.pause()
            app.refresh_plan()
            await pilot.pause()
            return {
                "where": str(app.query_one("#where").render()),
                "status": str(app.query_one("#status").render()),
                "detail": str(app.query_one("#detail").render()),
                "cursor": app.selected(),
                "classes": list(app.screen.classes),
                "screen": type(app.screen).__name__,
                "side": shown(app, app.query_one("#side").region),
            }

    return asyncio.run(go()), app


def shown(app, region):
    """What the screen shows inside a region, row by row, as the person sees it: wrapped and cut."""
    rows = app.screen._compositor.render_strips()[region.y : region.bottom]
    return [row.text[region.x : region.right] for row in rows]


def states(repo):
    with Store.open(repo) as store:
        return {n.id: n.state for n in plan.nodes(store)}


def proposed(repo):
    said = agent("plan", "propose", "-", input=TREE)
    assert said.exit_code == 0, said.output


def test_it_says_where_it_is_which_plan_and_names_the_two_agents(repo):
    proposed(repo)
    seen, _ = watch(repo, [])
    assert (
        repo.name in seen["where"] and "the plan (proposed): users come back with their ids" in seen["where"]
    )
    assert "planner: claude:5e55105e" in seen["status"] and "executors: none" in seen["status"]
    assert seen["classes"] == ["-narrow"]  # 80 columns: the tree above, the node below it
    wide, _ = watch(repo, [], size=(120, 30))
    assert wide["classes"] == ["-wide"]


def test_vim_keys_move_and_fold(repo):
    proposed(repo)
    seen, _ = watch(repo, ["j"])
    assert seen["cursor"] == "ids"
    seen, _ = watch(repo, ["G", "g", "g"])
    assert seen["cursor"] == "api"
    seen, _ = watch(repo, ["G"])
    assert seen["cursor"] == "schema"
    seen, app = watch(repo, ["z", "M", "j"])  # all closed: the next line is the next sub-goal
    assert seen["cursor"] == "schema"
    seen, _ = watch(repo, ["z", "M", "z", "R", "j"])  # all open again
    assert seen["cursor"] == "ids"
    seen, _ = watch(repo, ["z", "a", "j"])  # za on api closes it; `a` of za adds nothing
    assert seen["cursor"] == "schema" and seen["screen"] == "Screen"


def test_y_accepts_d_drops_and_u_puts_it_back(repo):
    proposed(repo)
    seen, _ = watch(repo, ["j", "y"])
    assert states(repo)["ids"] == "open" and states(repo)["api"] == "open"  # and the one it sits under
    assert "graphene plan accept ids" in seen["status"]
    seen, _ = watch(repo, ["G", "d"])
    assert states(repo)["schema"] == "dropped" and "graphene node drop schema" in seen["status"]
    watch(repo, ["u"])
    assert states(repo)["schema"] == "proposed"


def test_visual_selects_several_and_y_accepts_them_all(repo):
    proposed(repo)
    watch(repo, ["j", "V", "j", "y"])
    assert states(repo)["ids"] == "open" and states(repo)["docs"] == "open"
    assert states(repo)["schema"] == "proposed"


def test_search_moves_to_the_match_and_n_to_the_next(repo):
    proposed(repo)
    seen, _ = watch(repo, ["slash", *"doc", "enter"])
    assert seen["cursor"] == "docs" and "/doc: 1 of 1" in seen["status"]


def test_a_adds_a_sibling_with_the_title_typed(repo):
    proposed(repo)
    person("plan", "accept")
    watch(repo, ["j", "a", *"the orders endpoint", "enter"])
    with Store.open(repo) as store:
        [new] = [n for n in plan.nodes(store) if n.title == "the orders endpoint"]
        assert new.parent == "api" and new.state == "open"  # the planner can fill it in: s


def test_e_opens_the_contract_in_the_editor(repo, monkeypatch, tmp_path):
    proposed(repo)
    person("plan", "accept")
    script = tmp_path / "edit.py"
    change = "t.replace('check: true', 'check: make schema')"
    script.write_text(f"import sys\np = sys.argv[1]\nt = open(p).read()\nopen(p, 'w').write({change})\n")
    monkeypatch.setenv("EDITOR", f"{sys.executable} {script}")
    seen, _ = watch(repo, ["G", "e"])
    with Store.open(repo) as store:
        assert plan.get(store, "schema").check == "make schema"
    assert "graphene node edit schema" in seen["status"]


def test_a_leaf_that_came_back_shows_its_fixes_and_w_takes_one(repo):
    proposed(repo)
    person("plan", "accept")
    with Store.open(repo) as store:
        bot = plan.Caller("claude:aaaa1111", False, "aaaa1111-session")
        plan.start(store, "schema", bot, repo)
        store.log_node(
            "schema", plan._now(), "denied", None, bot.session_id, None, {"path": "migrations/001.sql"}
        )
        plan.release(store, "schema", bot, "the column needs a migration too")
    seen, _ = watch(repo, ["G"])
    assert "came back: the column needs a migration too" in seen["detail"]
    assert "w  widen schema's scope to migrations/001.sql" in seen["detail"]
    watch(repo, ["G", "w"])
    with Store.open(repo) as store:
        assert plan.get(store, "schema").scope == ["schema.py", "migrations/001.sql"]


def test_the_colon_line_takes_any_command_verbatim(repo):
    proposed(repo)
    seen, _ = watch(repo, ["colon", *"plan accept schema", "enter"])
    assert states(repo)["schema"] == "open" and "graphene plan accept schema" in seen["status"]
    seen, _ = watch(repo, ["colon", *"graphene node show ids", "enter"])
    assert "ids (revision 1): users returns ids" in seen["detail"]


def test_question_mark_is_help_and_l_is_the_executors_output(repo):
    proposed(repo)
    seen, _ = watch(repo, ["question_mark"])
    assert seen["screen"] == "Help"
    seen, _ = watch(repo, ["j", "l"])
    assert "ids: the executor's output" in seen["detail"] and "(nothing yet)" in seen["detail"]


def test_what_a_colon_command_printed_gives_way_when_the_plan_moves(repo):
    """A recorded run: after `:plan accept`, a leaf came back and its offers were hidden under the
    accept's output until the cursor moved."""
    proposed(repo)

    async def before(app, pilot):
        for key in ["G", "colon", *"plan accept", "enter"]:
            await pilot.press(key)
            await pilot.pause()
        assert app.view == "said"
        with Store.open(repo) as store:
            bot = plan.Caller("claude:aaaa1111", False, "aaaa1111-session")
            plan.start(store, "schema", bot, repo)
            plan.release(store, "schema", bot, "the column needs a migration", wants=["migrations/001.sql"])

    seen, _ = watch(repo, [], before=before)
    assert "came back: the column needs a migration" in seen["detail"]


class Tty:
    """The watch's stdin, at a real terminal (under pytest it is not one)."""

    def isatty(self):
        return True


def test_y_on_a_node_that_is_not_a_proposal_says_so(repo):
    """Recheck: y on an accepted node ran nothing and said nothing: the bottom line kept its hint."""
    proposed(repo)
    person("plan", "accept")
    seen, _ = watch(repo, ["y"])
    assert "✗ graphene plan accept api: api is open, not a proposal" in seen["status"]


def test_u_after_a_visual_d_puts_the_whole_selection_back(repo):
    """Recheck: a visual d was one undo entry per node, so u put back the last node only, and a
    selection of more than 20 pushed every earlier act out of the undo history."""
    proposed(repo)
    seen, _ = watch(repo, ["V", "G", "d"])
    assert set(states(repo).values()) == {"dropped"}
    assert "graphene node drop api ids docs schema" in seen["status"]  # one command
    watch(repo, ["u"])
    assert set(states(repo).values()) == {"proposed"}  # one act, one undo


def test_colon_node_done_is_logged_as_typed_at_a_terminal_and_ends_saying_what_happened(repo, monkeypatch):
    """Recheck: `:node done` runs as a process of its own with no terminal, so the log kept the person's
    act as 'alex (no terminal)'; and its ended line showed its last line ('next: …'), not the first,
    which says what happened. The whole of its output is in the side pane."""
    monkeypatch.setattr(sys, "stdin", Tty())
    proposed(repo)
    person("plan", "accept")

    async def before(app, pilot):
        for key in ["colon", *"node start schema", "enter"]:
            await pilot.press(key)
        (repo / "schema.py").write_text("TABLES = ['users']\n")
        for key in ["colon", *"node done schema", "enter"]:
            await pilot.press(key)
        await asyncio.to_thread(app.runs[0].wait, 60)
        await pilot.pause(0.3)

    seen, _ = watch(repo, [], before=before)
    assert "graphene node done schema ended: schema is done (check passed" in seen["status"]
    assert "schema is done" in seen["detail"] and "next:" in seen["detail"]
    with Store.open(repo) as store:
        actors = {e["kind"]: e["actor"] for e in store.node_log("schema")}
    assert (actors["started"], actors["finished"]) == ("alex", "alex")
    assert plan.caller({"CLAUDECODE": "1", "GRAPHENE_WATCH": "1"}).person is False  # an agent stays one


def test_colon_node_signoff_runs_the_roll_up_check_off_the_screen(repo):
    """Recheck: `:node signoff` ran the parent's roll-up check on the screen's own thread: it froze for
    as long as that check took (up to half an hour)."""
    with Store.open(repo) as store:
        alex, bot = plan.Caller("alex", True), plan.Caller("claude:aaaa1111", False, "aaaa1111-session")
        leaf = {"id": "leaf", "title": "users", "parent": "top", "scope": ["api.py"], "check": "true"}
        plan.propose(
            store, [{"id": "top", "title": "the API", "check": "true"}, {**leaf, "signoff": True}], alex
        )
        plan.start(store, "leaf", bot, repo)
        (repo / "api.py").write_text("def users():\n    return [1]\n")
        plan.finish(store, "leaf", bot, checkout=repo)

    async def before(app, pilot):
        for key in ["colon", *"node signoff leaf", "enter"]:
            await pilot.press(key)
        assert [p.args[3:] for p in app.runs] == [["node", "signoff", "leaf"]]  # its own process
        await asyncio.to_thread(app.runs[0].wait, 60)
        await pilot.pause(0.3)

    seen, _ = watch(repo, [], before=before)
    assert states(repo) == {"top": "done", "leaf": "done"}
    assert "graphene node signoff leaf ended: leaf is done (signed off)" in seen["status"]


LONG = (
    "Graphene refused the write to migrations/001.sql: it is outside schema's scope (schema.py). The column "
    "needs a migration, and the migration lives in migrations/, which I may not write; the ids leaf names it "
    "too. Widen the scope, or add a leaf for it."
)


def test_at_80_columns_a_long_reason_leaves_every_fix_in_sight_and_the_bottom_line_says_what_q_does(repo):
    """Recheck: executors paste their refusal as the reason, and at 80×24 it pushed b, n and ? below the
    fold; on that leaf the bottom line said '? help', where ? starts a planner, which spends."""
    proposed(repo)
    person("plan", "accept")
    with Store.open(repo) as store:
        bot = plan.Caller("claude:aaaa1111", False, "aaaa1111-session")
        plan.start(store, "schema", bot, repo)
        plan.release(store, "schema", bot, LONG, wants=["migrations/001.sql"])
    seen, _ = watch(repo, ["G"])
    side = "\n".join(seen["side"])
    for key in ("w  widen schema's", "b  a sibling leaf", "n  make schema wait on ids", "?  ask the planner"):
        assert key in side, side
    assert "? asks the planner" in seen["status"]
    seen, _ = watch(repo, ["G", "enter"])
    assert "Widen the scope, or add a leaf for it." in seen["detail"]  # the whole reason, in its record


def test_help_wraps_to_the_screen_and_sits_in_the_middle_of_it(repo):
    """Recheck: at 80 columns the help was 106 wide from x=0, and its last 26 columns were cut off with
    no way to scroll to them."""
    proposed(repo)
    for size in ((80, 24), (120, 40)):

        async def before(app, pilot, width=size[0]):
            await pilot.press("question_mark")
            await pilot.pause()
            text, box = app.screen.query_one("#help").region, app.screen.query_one("VerticalScroll").region
            assert text.right <= width and abs(box.x - (width - box.right)) <= 1, (width, text, box)
            assert "zM all closed" in "\n".join(shown(app, text))

        watch(repo, [], size=size, before=before)


def test_what_the_planner_said_after_its_block_reaches_the_screen_that_asked(repo, tmp_path, monkeypatch):
    """Recheck: the planner's sentence after its block ('the planner says: …'), its only way to suggest a
    change to a node already there, and what it proposed never reached the screen that asked."""
    from test_ask import GOOD, planner

    command = planner(tmp_path, GOOD, monkeypatch)

    async def before(app, pilot):
        app.background(["ask", "users come back with their ids", "--with", command])
        await asyncio.to_thread(app.runs[0].wait, 60)
        await pilot.pause(0.3)

    seen, _ = watch(repo, [], before=before)
    assert "graphene ask 'users come back with their ids' ended: the planner says: I read" in seen["status"]
    assert "the planner says: I read api.py and schema.py" in seen["detail"]
    assert "proposed ids: users returns ids" in seen["detail"]


def test_colon_ask_reads_quotes_and_options_as_a_shell_would(repo, monkeypatch):
    """Recheck: `:ask "add a login page"` gave the planner (and the plan's log) the quotes too, and
    `:ask --about ids fix it` passed several sentences, which `graphene ask` refused."""
    proposed(repo)
    asked = []
    monkeypatch.setattr(Watch, "background", lambda self, argv: asked.append(argv))
    for line in ('ask "add a login page"', "ask --about ids fix it", "ask don't break it"):
        watch(repo, ["colon", *line, "enter"])
    assert asked == [
        ["ask", "add a login page"],
        ["ask", "fix it", "--about", "ids"],
        ["ask", "don't break it"],
    ]


def test_the_side_pane_judges_a_check_as_graphene_node_add_does(repo):
    """Recheck: the pane called a path that the leaf's need will write missing ('⚠ … not in its scope'),
    where the command line said nothing of the same check."""
    with Store.open(repo) as store:
        plan.propose(store, [
            {"id": "render", "title": "render", "scope": ["tests/pdf/**"], "check": "true"},
            {"id": "use", "title": "use it", "scope": ["api.py"], "needs": ["render"],
             "check": "python3 -m pytest tests/pdf/test_render.py -q"},
            {"id": "typo", "title": "csv", "scope": ["feeds/csv.py"], "check": "pytest test/test_csv.py"},
        ], plan.Caller("alex", True))  # fmt: skip
    seen, _ = watch(repo, ["G", "k"])
    assert seen["cursor"] == "use" and "⚠" not in seen["detail"]
    seen, _ = watch(repo, ["G"])
    assert (
        "names test/test_csv.py, which is not in the repo and no leaf's scope may create it" in seen["detail"]
    )
