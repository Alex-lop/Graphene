# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""`graphene watch`: the plan on one screen, driven the way a person drives it, by keys, headless
(Textual's pilot) at 80 columns and at 120. Every key is a command: after each, the store says what
the command did, and the bottom line says which command it was."""

import asyncio
import re
import sys

from test_plan_cli import agent, person, repo  # noqa: F401  (fixtures)

from graphene_map import plan
from graphene_map.store import Store
from graphene_map.tui import Watch

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
                "tree": shown(app, app.query_one("#tree").scrollable_content_region),  # less its scrollbar
                "sideways": app.tree.max_scroll_x,
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


def test_the_top_line_says_whose_plan_and_the_goal_is_the_first_row(repo):
    """The top line was the repository and a goal cut with no ellipsis; the goal is now the tree's
    first row, and the top line says whose plan it is in the words every write ends with."""
    proposed(repo)
    seen, _ = watch(repo, [])
    where = f"the plan of {plan.where(repo)}"  # the words every write ends with; a long path keeps its tail
    assert seen["where"] == where if len(where) <= 78 else seen["where"].startswith("the plan of …")
    assert seen["where"].endswith(repo.name) and len(seen["where"]) <= 78
    assert seen["tree"][0].startswith("▼ ? users come back with their ids") and "proposed" in seen["tree"][0]
    assert seen["cursor"] is None and "users come back with their ids" in seen["detail"]  # the goal's pane
    assert "planner:" not in seen["status"] and "you: 2 · 0 running" in seen["status"]  # the tree, once
    assert seen["classes"] == ["-narrow"]  # 80 columns: the tree above, the node below it
    wide, _ = watch(repo, [], size=(120, 30))
    assert wide["classes"] == ["-wide"] and "waiting on you: 2 · executors: none" in wide["status"]
    person("plan", "accept")
    seen, _ = watch(repo, [])
    assert seen["tree"][0].startswith("▼ ○ users come back with their ids") and "0/3 done" in seen["tree"][0]
    folded, _ = watch(repo, ["z", "a"])  # the goal's row folds like any other: all of it
    assert [row.strip() for row in folded["tree"] if row.strip()] == [folded["tree"][0].strip()]
    assert folded["tree"][0].startswith("▶")


def test_vim_keys_move_and_fold(repo):
    proposed(repo)
    seen, _ = watch(repo, ["j", "j"])  # the goal's row first, then api, then ids
    assert seen["cursor"] == "ids"
    seen, _ = watch(repo, ["G", "g", "g"])
    assert seen["cursor"] is None and "the goal · proposed" in seen["detail"]
    seen, _ = watch(repo, ["G"])
    assert seen["cursor"] == "schema"
    seen, app = watch(repo, ["z", "M", "j", "j"])  # all closed: the next line is the next sub-goal
    assert seen["cursor"] == "schema"
    seen, _ = watch(repo, ["z", "M", "z", "R", "j", "j"])  # all open again
    assert seen["cursor"] == "ids"
    seen, _ = watch(repo, ["j", "z", "a", "j"])  # za on api closes it; `a` of za adds nothing
    assert seen["cursor"] == "schema" and seen["screen"] == "Screen"


def test_y_accepts_d_drops_and_u_puts_it_back(repo):
    proposed(repo)
    seen, _ = watch(repo, ["j", "j", "y"])
    assert states(repo)["ids"] == "open" and states(repo)["api"] == "open"  # and the one it sits under
    assert "graphene plan accept ids" in seen["status"]
    seen, _ = watch(repo, ["G", "d"])
    assert states(repo)["schema"] == "dropped" and "graphene node drop schema" in seen["status"]
    watch(repo, ["u"])
    assert states(repo)["schema"] == "proposed"


def test_visual_selects_several_and_y_accepts_them_all(repo):
    proposed(repo)
    watch(repo, ["j", "j", "V", "j", "y"])
    assert states(repo)["ids"] == "open" and states(repo)["docs"] == "open"
    assert states(repo)["schema"] == "proposed"


def test_search_moves_to_the_match_and_n_to_the_next(repo):
    proposed(repo)
    seen, _ = watch(repo, ["slash", *"doc", "enter"])
    assert seen["cursor"] == "docs" and "/doc: 1 of 1" in seen["status"]


def test_a_adds_a_sibling_with_the_title_typed(repo):
    proposed(repo)
    person("plan", "accept")
    watch(repo, ["j", "j", "a", *"the orders endpoint", "enter"])
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
    assert "schema · came back" in seen["detail"] and "the column needs a migration too" in seen["detail"]
    assert "w  widen its scope to migrations/001.sql" in seen["detail"]
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
    seen, _ = watch(repo, ["j", "j", "l"])
    assert "ids · output of attempt 1" in seen["detail"] and "nothing yet" in seen["detail"]


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
    assert "schema · came back" in seen["detail"] and "the column needs a migration" in seen["detail"]


class Tty:
    """The watch's stdin, at a real terminal (under pytest it is not one)."""

    def isatty(self):
        return True


def test_y_on_a_node_that_is_not_a_proposal_says_so(repo):
    """Recheck: y on an accepted node ran nothing and said nothing: the bottom line kept its hint."""
    proposed(repo)
    person("plan", "accept")
    seen, _ = watch(repo, ["j", "y"])
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
    for key in ("w  widen its scope", "b  a sibling leaf", "n  wait on ids", "?  ask the planner"):
        assert key in side, side
    assert "? ask the planner" in seen["status"] and "? help" not in seen["status"]
    seen, _ = watch(repo, ["G", "enter"])
    assert "Widen the scope, or add a leaf for it." in seen["detail"]  # the whole reason, in its record


def test_help_wraps_to_the_screen_and_sits_in_the_middle_of_it(repo):
    """Recheck: at 80 columns the help was 106 wide from x=0, and its last 26 columns were cut off with
    no way to scroll to them. It is grouped as the README groups the keys: two columns at 120, one at
    80, and it closes on ?, Esc or q."""
    proposed(repo)
    for size in ((80, 24), (120, 40)):

        async def before(app, pilot, width=size[0]):
            await pilot.press("question_mark")
            await pilot.pause()
            text, box = app.screen.query_one("#help").region, app.screen.query_one("VerticalScroll").region
            assert text.right <= width and abs(box.x - (width - box.right)) <= 1, (width, text, box)
            rows = shown(app, text)
            assert "zR zM" in "\n".join(rows)
            assert len(app.screen.query("#help > Static")) == (2 if width >= 110 else 1)
            if width >= 110:  # side by side: the first group of each column on one row
                assert any("move" in r and "run" in r for r in rows), rows
                assert "plan first on or off" in "\n".join(rows)

        watch(repo, [], size=size, before=before)
    for key in ("question_mark", "escape", "q"):
        seen, _ = watch(repo, ["question_mark", key])
        assert seen["screen"] == "Screen"


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
    # what it proposed, on the bottom line (its sentence was there when it began); what it said, in the pane
    assert "the planner proposed users-api, ids; what it said is in the pane" in seen["status"]
    assert "I read api.py and schema.py" in seen["detail"]
    assert "proposed ids: users returns ids" in seen["detail"]


def test_colon_ask_reads_quotes_and_options_as_a_shell_would(repo, monkeypatch):
    """Recheck: `:ask "add a login page"` gave the planner (and the plan's log) the quotes too, and
    `:ask --about ids fix it` passed several sentences, which `graphene ask` refused."""
    proposed(repo)
    asked = []
    monkeypatch.setattr(Watch, "background", lambda self, argv: asked.append(argv))
    lines = ('ask "add a login page"', "ask --about ids fix it", "ask don't break it",
             "ask add a --dry-run flag to load")  # fmt: skip
    for line in lines:
        watch(repo, ["colon", *line, "enter"])
    assert asked == [
        ["ask", "add a login page"],
        ["ask", "fix it", "--about", "ids"],
        ["ask", "don't break it"],
        ["ask", "add a --dry-run flag to load"],  # seen at the screen: the flag was taken for ask's
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
    assert "names test/test_csv.py, which is not in the repo and no leaf's scope may create it" in " ".join(
        seen["detail"].split()
    )  # wrapped at words in the pane


def test_colon_stop_reaches_a_parallel_run_by_the_pid_and_start_its_lock_names(repo):
    """The run's lock became two lines (pid, start time) and :stop still read one: it stopped
    reaching a parallel run started from another terminal."""
    import subprocess

    from graphene_map import run as R

    # its own SIGINT handler: a CI step may start with SIGINT ignored, and a child inherits that
    # (and only after it says so: a SIGINT before that is ignored, which raced on Linux CI)
    code = (
        "import signal, time; signal.signal(signal.SIGINT, signal.default_int_handler); "
        "print('up', flush=True); time.sleep(30)"
    )
    run = subprocess.Popen([sys.executable, "-c", code, "graphene", "run"], stdout=subprocess.PIPE, text=True)
    assert run.stdout.readline().strip() == "up"
    try:
        (repo / ".graphene").mkdir(exist_ok=True)
        (repo / ".graphene" / "run.lock").write_text(f"{run.pid}\n{R._started(run.pid)}\n")
        app = Watch(repo, lambda: Store.open(repo), every=60)
        app.stop_runs()
        assert run.wait(timeout=10) != 0 and "stopping 1 run" in app.message
    finally:
        run.kill()


# -- the recheck of the closing review: its regression tests --------------------


# Recheck 28 (fixed)
def test_q_gives_the_terminal_back_while_a_run_started_here_goes_on(repo):
    import os
    import signal
    import subprocess
    import time

    proposed(repo)
    child = (
        "import asyncio, subprocess, types\n"
        "from graphene_map import tui\n"
        "from graphene_map.store import Store\n"
        f"repo = {str(repo)!r}\n"
        "real = subprocess.Popen\n"  # the run is a sleep, so the screen's own git calls stay real
        "tui.subprocess = types.SimpleNamespace(Popen=lambda argv, **kw: real(['sleep', '20'], **kw),\n"
        "    DEVNULL=subprocess.DEVNULL, STDOUT=subprocess.STDOUT, run=subprocess.run)\n"
        "app = tui.Watch(tui.Path(repo), lambda: Store.open(tui.Path(repo)), every=60)\n"
        "async def go():\n"
        "    async with app.run_test() as pilot:\n"
        "        app.background(['run'])\n"
        "        print(app.runs[0].pid, flush=True)\n"
        "        await pilot.press('q')\n"
        "asyncio.run(go())\n"
    )
    began = time.monotonic()
    ran = subprocess.run([sys.executable, "-c", child], capture_output=True, text=True, timeout=12)
    assert ran.returncode == 0, ran.stderr
    assert time.monotonic() - began < 10  # not the run's 20 s
    os.kill(int(ran.stdout.split()[0]), signal.SIGKILL)  # the run went on: it is still there to stop


# Recheck 29 (fixed)
def test_a_command_that_keeps_a_terminal_is_refused_not_run_on_the_screen(repo, monkeypatch):
    from graphene_map import server

    served = []
    monkeypatch.setattr(server, "make_server", lambda *a, **k: served.append(a))
    proposed(repo)
    for typed in ("ui --no-open", "ingest hook"):
        seen, _ = watch(repo, ["colon", *typed, "enter"], size=(120, 30))
        assert f"`graphene {typed.split()[0]}` takes a terminal of its own" in seen["status"]
    assert served == []  # no server was started on the screen's own thread


# Recheck 30 (fixed)
def test_a_node_moved_under_a_later_one_is_drawn_under_it(repo):
    from graphene_map.tui import _walk

    proposed(repo)
    person("plan", "accept")
    assert person("node", "set", "api", "--parent", "schema").exit_code == 0
    drawn = {}

    async def before(app, pilot):
        drawn.update({n.data: n.parent.data for n in _walk(app.tree.root)})

    watch(repo, [], before=before)
    assert drawn == {"schema": None, "api": "schema", "ids": "api", "docs": "api"}  # as plan --text


# Recheck 32 (fixed)
def test_search_skips_a_hidden_done_aside_and_lands_on_what_is_drawn(repo):
    bot = plan.Caller("claude:aaaa1111", False, "aaaa1111-session")
    with Store.open(repo) as store:  # a leaf made from a typed prompt, closed: not drawn
        [made] = plan.propose(
            store, [{"title": "rename the schema table", "scope": ["schema.py"]}], plan.Caller("alex", True),
            aside=True,
        )  # fmt: skip
        plan.start(store, made.id, bot, str(repo), attended=True)
        (repo / "schema.py").write_text("TABLES = ['users']\n")
        assert plan.close_aside(store, made.id, bot).state == "done"
    proposed(repo)
    person("plan", "accept")
    seen, _ = watch(repo, ["slash", *"schema", "enter", "n"])
    assert seen["cursor"] == "schema" and "/schema: 1 of 1" in seen["status"]


# Recheck 33 (fixed)
def test_escape_ends_a_search_so_n_takes_the_offer_again(repo):
    proposed(repo)
    person("plan", "accept")
    with Store.open(repo) as store:
        bot = plan.Caller("claude:aaaa1111", False, "aaaa1111-session")
        plan.start(store, "schema", bot, repo)
        plan.release(store, "schema", bot, "the column must wait until ids is in")
    watch(repo, ["slash", *"schema", "enter", "escape", "n"])
    with Store.open(repo) as store:
        assert plan.get(store, "schema").needs == ["ids"]


# Recheck 35 (fixed)
def test_at_80_columns_the_bottom_line_still_says_what_the_key_did(repo):
    from test_plan_cli import runner

    from graphene_map.cli import build

    person_proposes = runner.invoke(  # the person's own tree: no planner named, the longest top line
        build(), ["plan", "propose", "-"], env={"GRAPHENE_AS": "person:alex"}, input=TREE
    )
    assert person_proposes.exit_code == 0, person_proposes.output
    with Store.open(repo) as store:
        plan.start(store, "schema", plan.Caller("claude:aaaa1111", False, "aaaa1111-session"), repo)
    seen, _ = watch(repo, ["j", "j", "d"])
    top, bottom = seen["status"].splitlines()
    assert len(top) <= 78  # 80 columns less the padding: it does not wrap onto the message's row
    assert bottom.startswith("✗ graphene node drop ids: docs waits on ids")


# Recheck 36 (fixed)
def test_two_commands_started_in_one_second_each_keep_their_own_output(repo, monkeypatch):
    proposed(repo)
    monkeypatch.setattr("graphene_map.tui.time.strftime", lambda _: "20260923-040553")  # one second

    async def before(app, pilot):
        app.background(["node", "show", "docs"])
        app.background(["node", "show", "ids"])
        for proc in app.runs:
            proc.wait()

    watch(repo, [], before=before)
    assert len(list((repo / ".graphene" / "runs").iterdir())) == 2


# Recheck 37 (partly)
def test_u_after_a_visual_y_puts_the_whole_selection_back(repo):
    proposed(repo)
    watch(repo, ["j", "j", "V", "j", "j", "y"])
    assert set(states(repo).values()) == {"open"}
    watch(repo, ["u"])
    assert set(states(repo).values()) == {"proposed"}  # one act, one undo


# Recheck 38 (fixed)
def test_zc_or_za_on_a_leaf_closes_the_branch_it_sits_in(repo):
    proposed(repo)
    seen, _ = watch(repo, ["j", "j", "z", "c", "j"])  # api closed: the next line is the next sub-goal
    assert seen["cursor"] == "schema"
    seen, _ = watch(repo, ["j", "j", "z", "a", "j"])
    assert seen["cursor"] == "schema"


# Recheck 39 (fixed)
def test_the_bottom_line_gives_what_the_command_said_not_where_the_plan_is(repo):
    proposed(repo)
    seen, _ = watch(repo, ["G", "d"])
    assert "graphene node drop schema: schema dropped" in seen["status"]
    assert "(the plan of" not in seen["status"]


# Recheck 40 (partly)
def test_stop_leaves_alone_a_process_a_stale_run_lock_names(repo):
    import subprocess

    import pytest

    proposed(repo)
    bystander = subprocess.Popen(["sleep", "30"])  # the pid a SIGKILLed run left, now someone else's
    (repo / ".graphene" / "run.lock").write_text(str(bystander.pid))
    try:
        seen, _ = watch(repo, ["colon", *"stop", "enter"])
        assert "no run to stop" in seen["status"]
        with pytest.raises(subprocess.TimeoutExpired):
            bystander.wait(timeout=0.5)
    finally:
        bystander.kill()
        bystander.wait()


# Recheck 41 (partly)
def test_colon_graphene_ask_gives_the_planner_the_sentence_alone(repo, monkeypatch):
    proposed(repo)
    asked = []
    monkeypatch.setattr(Watch, "background", lambda self, argv: asked.append(argv))
    watch(repo, ["colon", *"graphene ask add a login page", "enter"])
    assert asked == [["ask", "add a login page"]]


# Recheck 42 (fixed)
def test_a_title_that_starts_with_a_dash_is_a_title_not_an_option(repo):
    proposed(repo)
    person("plan", "accept")
    seen, _ = watch(repo, ["j", "j", "a", *"--dry-run for deploys", "enter"])
    with Store.open(repo) as store:
        [new] = [n for n in plan.nodes(store) if n.title == "--dry-run for deploys"]
    assert new.parent == "api" and "✗" not in seen["status"]


# Recheck 43 (partly)
def test_at_80_columns_a_leaf_that_came_back_says_why_and_its_keys_before_its_contract(repo):
    proposed(repo)
    person("plan", "accept")
    with Store.open(repo) as store:
        bot = plan.Caller("claude:aaaa1111", False, "aaaa1111-session")
        plan.start(store, "schema", bot, repo)
        wanted = {"path": "migrations/001.sql"}
        store.log_node("schema", plan._now(), "denied", None, bot.session_id, None, wanted)
        plan.release(store, "schema", bot, "the column needs a migration")
    seen, _ = watch(repo, ["G"])
    top = [line.strip() for line in seen["detail"].splitlines()[:4]]
    assert top[:2] == ["the schema", "schema · came back"]  # say came back once, in the header
    assert top[2] == "the column needs a migration" and top[3].startswith("w  widen its scope")


# Recheck 70 (fixed)
def test_colon_ui_is_refused_and_the_screen_still_answers(repo, monkeypatch):
    """`:ui` ran the page's server on the screen's own thread: no key was read again."""
    import socketserver
    import webbrowser

    served = []
    monkeypatch.setattr(socketserver.BaseServer, "serve_forever", lambda self, *a, **k: served.append(self))
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: True)
    proposed(repo)
    seen, _ = watch(repo, ["colon", *"ui", "enter"])
    assert "`graphene ui` takes a terminal of its own" in seen["status"]
    seen, _ = watch(repo, ["colon", *"ui", "enter", "j"])
    assert not served and seen["cursor"] == "api"  # j after it was taken


# Recheck 76 (fixed)
def test_visual_from_a_sub_goal_accepts_it_and_its_leaves_with_no_refusal(repo):
    """`V j j y` on api: accepting api accepted ids and docs, and then their own accepts said ✗."""
    proposed(repo)
    seen, _ = watch(repo, ["j", "V", "j", "j", "y"])
    assert [states(repo)[i] for i in ("api", "ids", "docs", "schema")] == ["open", "open", "open", "proposed"]
    assert "✗" not in seen["status"] and "graphene plan accept api ids docs" in seen["status"]


# Recheck 77 (partly)
def test_the_readme_shows_the_screen_from_a_file_the_repo_holds():
    """Review finding 77: the README embedded docs/assets/watch.gif, which no commit held."""
    import re
    import subprocess
    from pathlib import Path

    import graphene_map

    root = Path(graphene_map.__file__).resolve().parents[2]
    listed = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=True)
    held = set(listed.stdout.split())
    links = re.findall(r"\]\((?!https?:|#)([^)#\s]+)", (root / "README.md").read_text(encoding="utf-8"))
    assert "docs/assets/watch.gif" in links and not [p for p in links if p not in held]


# -- the polish: one grammar, a pane per kind, the status line, the keys (driven at 80 and at 120) ----

SIZES = ((80, 24), (120, 36))
RUN = plan.Caller("run:claude", False, "7e1f00aa-run-session")
SESSION = plan.Caller("claude:aaaa1111", False, "aaaa1111-session")
LONG_TITLE = "the contract test names every enabled source and runs each one of them end to end"


def every_state(repo):
    """A plan with a leaf in every state a person meets: running (with its hooks' record and an empty
    log), came back, waiting, yours, to fill in, review, done, ready, and a proposal."""
    import subprocess
    import time

    from graphene_map.model import ToolEvent

    def commit():
        subprocess.run(
            ["git", "-c", "user.email=t@e.com", "-c", "user.name=T", "commit", "-qam", "x"], cwd=repo
        )

    alex = plan.Caller("alex", True)
    with Store.open(repo) as store:
        plan.set_goal(store, "users come back with their ids, and the schema says so", alex)
        plan.propose(store, [
            {"id": "api", "title": "the API"},
            {"id": "ids", "title": "users returns ids", "parent": "api", "scope": ["api.py"], "check": "true",
             "goal": "users() returns each user's id, so a caller can come back with it"},
            {"id": "docs", "title": "document it", "parent": "api", "scope": ["README.md"], "check": "true"},
            {"id": "more", "title": LONG_TITLE, "parent": "api", "scope": ["tests/test_contract.py"],
             "check": "true", "needs": ["ids"]},
            {"id": "later", "title": "the rest, to be split", "parent": "api"},
            {"id": "mine", "title": "read it over", "parent": "api", "owner": "alex"},
            {"id": "schema", "title": "the schema"},
            {"id": "rule", "title": "a rule for ids", "parent": "schema", "scope": ["rules.py"],
             "check": "true", "signoff": True},
            {"id": "table", "title": "the users table", "parent": "schema", "scope": ["schema.py"],
             "check": "true"},
            {"id": "ready1", "title": "a sample", "parent": "schema", "scope": ["sample.txt"],
             "check": "true"},
        ], alex)  # fmt: skip
        plan.start(store, "table", RUN, repo)
        (repo / "schema.py").write_text("TABLES = ['users']\n")
        plan.finish(store, "table", RUN, checkout=repo)
        commit()
        plan.start(store, "rule", RUN, repo)
        (repo / "rules.py").write_text("RULES = []\n")
        plan.finish(store, "rule", RUN, checkout=repo)
        subprocess.run(["git", "add", "rules.py"], cwd=repo)
        commit()
        plan.start(store, "docs", SESSION, repo)
        store.log_node("docs", plan._now(), "denied", None, SESSION.session_id, None, {"path": "docs/api.md"})
        plan.release(store, "docs", SESSION, "it needs docs/api.md, and ids has to land first")
        plan.start(store, "ids", RUN, repo)
        log = repo / ".graphene" / "runs" / "ids-1.txt"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("")
        attempt = {"attempt": 1, "log": str(log)}
        store.log_node("ids", plan._now(), "attempt", RUN.label, RUN.session_id, None, attempt)
        now = time.time()
        for k, (tool, given) in enumerate(
            [("Read", {"file_path": "api.py"}), ("Bash", {"command": "cat api.py"})]
        ):
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(now - 30 + k * 10))
            event = ToolEvent(
                f"e{k}", RUN.session_id, None, stamp, tool, given, file_path=given.get("file_path")
            )
            store.add_event(event)
        plan.propose(store, [{"id": "idea", "title": "an idea", "scope": ["x.py"], "check": "true"}], SESSION)


def at(repo, node_id, size, keys=(), before=None):
    """The screen with the cursor on a node, found by search as a person finds it."""
    seen, app = watch(repo, ["slash", *node_id, "enter", "escape", *keys], size=size, before=before)
    assert seen["cursor"] == node_id, (node_id, seen["cursor"])
    return seen, app


def test_every_row_reads_in_one_grammar_at_80_and_120(repo):
    """The tree's rows were three ragged columns, overflowed into a horizontal scroll and cut ids in
    half. Now: glyph, title cut at a word, id, state word, in fixed columns at any depth."""
    every_state(repo)
    words = {"api": "0/5 done", "ids": "running", "docs": "came back", "more": "waiting",
             "later": "to fill in", "mine": "yours", "schema": "1/3 done", "rule": "review", "table": "done",
             "ready1": "ready", "idea": "proposed"}  # fmt: skip
    for size in SIZES:  # all open: at 80x24 its twelve rows are taller than the pane, and fold
        seen, app = watch(repo, ["z", "R"], size=size)
        end, _ = watch(repo, ["z", "R", "G"], size=size)  # at 80x24 the tree scrolls: its top, then its end
        rows = [r.rstrip() for r in [*seen["tree"], *end["tree"]] if r.strip()]
        assert rows[0].startswith("▼ ○ users come back with their ids") and rows[0].endswith("1/8 done"), rows
        mine = {i: next(r for r in rows if f"  {i} " in r + " ") for i in words}
        assert len({r.index(f"  {i} ") for i, r in mine.items()}) == 1, (size, mine)  # one id column
        at_word = {r.index(words[i], r.index(f"  {i} ") + len(i)) for i, r in mine.items()}
        assert len(at_word) == 1  # one column of state words
        assert all(r.endswith(words[i]) for i, r in mine.items()), (size, mine)  # never cut
        long = mine["more"]
        title = long[long.index("◌ ") + 2 : long.index("…")]
        assert LONG_TITLE.startswith(title) and LONG_TITLE[len(title)] == " "  # cut at a word
        assert seen["sideways"] == end["sideways"] == 0  # never a horizontal scroll


def test_the_tree_takes_what_its_rows_need_from_110_columns_and_sits_above_the_pane_below(repo):
    every_state(repo)

    async def before(app, pilot):
        tree, side = app.query_one("#tree").region, app.query_one("#side").region
        if app.size.width >= 110:
            assert side.x == tree.right and side.width >= 44 and tree.width >= 60  # side by side
        else:
            assert side.y > tree.y and side.width == app.size.width  # the pane under the tree
            assert tree.height <= (app.size.height - 3) // 2

    for size in SIZES:
        watch(repo, [], size=size, before=before)
    with Store.open(repo) as store:  # short titles: the tree is only as wide as they need
        plan.drop(store, "more", plan.Caller("alex", True))

    async def short(app, pilot):
        assert app.query_one("#tree").region.width < 60 and app.query_one("#side").region.width > 60

    watch(repo, [], size=(120, 36), before=short)


def test_the_node_pane_has_a_section_for_each_kind_and_nothing_blank_or_twice(repo):
    every_state(repo)
    said = {
        "api": ["api · 0/5 done", "users returns ids", "more on ids (running)", "mine is yours"],
        "ids": ["ids · running", "executor claude, started by graphene run", "worktree", "cat api.py"],
        "docs": ["docs · came back", "it needs docs/api.md", "w widen its scope to docs/api.md",
                 "b a sibling leaf for docs/api.md", "n wait on ids", "? ask the planner"],
        "more": ["more · waiting", "needs ids (running)"],
        "later": ["later · to fill in", "no scope and no leaves yet"],
        "mine": ["mine · yours", "owner alex"],
        "rule": ["rule · review", "its check passed; it waits for your sign-off", "changed rules.py"],
        "table": ["table · done at ", "changed schema.py"],
        "ready1": ["ready1 · ready", "scope sample.txt", "check true"],
        "idea": ["idea · proposed by a Claude Code session (aaaa1111)", "scope x.py"],
    }  # fmt: skip
    for size in SIZES:
        for node_id, parts in said.items():
            seen, _ = at(repo, node_id, size)
            pane, flat = seen["detail"], " ".join(seen["detail"].split())
            for part in parts:
                assert part in flat, (size, node_id, part, pane)
            assert "revision" not in pane and "\n\n\n" not in pane  # no bookkeeping, no blank section
            keyed = [
                ln
                for ln in pane.splitlines()
                if re.match(r"(why|goal|scope|check|needs|owner|changed)  ", ln)
            ]
            assert all(len(ln.split()) > 1 for ln in keyed), (node_id, pane)  # no key without its value
            assert len({len(ln) - len(ln.split(" ", 1)[1].lstrip()) for ln in keyed}) <= 1, pane  # aligned
            assert flat.count("running") == 1 or node_id != "ids"  # said once
        seen, _ = at(repo, "ids", size)
        goal = "users() returns each user's id, so a caller can come back with it"
        assert goal in " ".join(seen["detail"].split())  # wrapped at words: every word whole


def test_the_offers_are_rows_of_one_shape_with_the_command_at_the_right(repo):
    """Each offer keeps its command, at 80 and at 120 (where the pane is narrow and the commands had
    gone): on its row, at the pane's edge, when every one fits whole; else under it, for all alike."""
    every_state(repo)
    commands = ["graphene node widen docs", "graphene node sibling docs",
                "graphene node set docs --needs ids", "graphene ask … --about docs"]  # fmt: skip
    for size in [*SIZES, (220, 40)]:
        seen, _ = at(repo, "docs", size)
        lines = [ln.rstrip() for ln in seen["detail"].splitlines()]
        keys = [k for k, ln in enumerate(lines) if re.match(r"  [wbn?]  ", ln)]
        assert [lines[k][2] for k in keys] == ["w", "b", "n", "?"], size
        on_row = [any(lines[k].endswith(c) for c in commands) for k in keys]
        if all(on_row):
            assert len({len(lines[k]) for k in keys}) == 1  # the commands at one edge
        else:
            assert not any(on_row), size  # never some one way and some the other
            for k, c, end in zip(keys, commands, [*keys[1:], None], strict=True):
                under = [ln.strip() for ln in lines[k + 1 : end] if ln.strip().startswith("graphene ")]
                cut = under[0].removesuffix("…") if under else ""
                assert cut and (cut.startswith(c) or c.startswith(cut)), (size, lines[k:end])
    assert all(on_row)  # at 220 columns every one fits on its row


def test_the_record_is_a_laid_out_pane_not_node_show_pasted(repo):
    every_state(repo)
    for size in SIZES:
        seen, _ = at(repo, "docs", size, keys=["enter"])
        record = seen["detail"]
        assert record.splitlines()[0] == "record · it scrolls"  # its keys are on the status line
        for section in (
            "contract",
            "came back",
            "holds",
            "the check",
            "refused",
            "coverage",
            "what people did",
        ):
            assert re.search(rf"^{section}\b", record, re.M), (size, section, record)
        assert "`" not in record and "graphene node" not in record  # the keys are on the status line
        assert "a Claude Code session (aaaa1111)" in record and "handed back" in record
        assert seen["status"].splitlines()[1].startswith("ctrl-d ctrl-u scroll · Enter back · w widen")


def test_l_shows_the_hooks_tool_calls_while_the_executors_log_is_empty(repo):
    every_state(repo)
    for size in SIZES:
        seen, _ = at(repo, "ids", size, keys=["l"])
        lines = seen["detail"].splitlines()
        assert lines[:2] == ["ids · output of attempt 1", ".graphene/runs/ids-1.txt"]
        assert "tool calls the hooks recorded" in " ".join(seen["detail"].split())
        calls = [ln for ln in lines if re.match(r"\d\d:\d\d:\d\d  ", ln)]
        assert [c.split("  ", 1)[1] for c in calls] == ["Read api.py", "Bash cat api.py"]  # newest last


def test_colour_says_who_has_the_move_and_red_is_only_a_command_that_failed(repo):
    from rich.style import Style

    from graphene_map.tui import _walk

    every_state(repo)
    palette = {word: plan.look(word)[1] for word in ("came back", "review", "yours", "running", "proposed")}
    assert palette == {"came back": "magenta", "review": "magenta", "yours": "magenta", "running": "yellow",
                       "proposed": "cyan"}  # fmt: skip

    async def before(app, pilot):
        for node in _walk(app.tree.root):
            label = app.tree.render_label(node, Style(), Style())
            styles = " ".join(str(span.style) for span in label.spans)
            assert plan.look(app.words[node.data])[1] in styles and "red" not in styles, (node.data, styles)
        assert "red" not in " ".join(str(s.style) for s in app.query_one("#status").render().spans)

    watch(repo, [], size=(120, 36), before=before)


def test_the_status_line_is_two_lines_fitted_at_a_word_at_80_and_120(repo):
    every_state(repo)
    wide, _ = at(repo, "rule", (120, 36))
    top, bottom = wide["status"].splitlines()
    assert top == "waiting on you: 4 · executors: 1 running · R runs 1 ready · 1/8 done · plan first: on (P)"
    assert bottom == "y sign off · x send back · Enter record · ? help · q quit"
    narrow, _ = at(repo, "rule", (80, 24))
    top, bottom = narrow["status"].splitlines()
    assert top == "you: 4 · 1 running · R: 1 ready · 1/8 done · plan first: on"
    long = "graphene node edit rule: " + "the scope changed from one path to a longer list of them " * 3

    async def said(app, pilot):
        app.message = long
        app.say_status()
        await pilot.pause()
        bottom = str(app.query_one("#status").render()).splitlines()[1]
        assert len(bottom) <= 78 and bottom.endswith("…") and long.startswith(bottom[:-1] + " ")  # at a word

    watch(repo, [], before=said)


def test_an_empty_plan_says_what_to_do_in_two_lines(repo):
    for size in SIZES:
        seen, _ = watch(repo, [], size=size)
        said = seen["detail"].splitlines()
        assert len(said) <= 2 and " ".join(ln.strip() for ln in said) == (
            "Nothing is planned here yet. Tell your agent what you want, in a paragraph: it proposes the "
            "tree here. Or :ask <what you want>. ? lists the keys."
        )  # one paragraph wrapped to the pane, which has the whole width: there is no tree to show


def test_y_signs_off_a_leaf_in_review_and_marks_your_own_leaf_done(repo, monkeypatch):
    every_state(repo)
    asked = []
    monkeypatch.setattr(Watch, "background", lambda self, argv: asked.append(argv))
    at(repo, "rule", (80, 24), keys=["y"])
    at(repo, "mine", (80, 24), keys=["y"])
    assert asked == [["node", "signoff", "rule"], ["node", "done", "mine"]]


def test_s_is_refused_on_what_is_running_in_review_or_done_without_starting_a_planner(repo, monkeypatch):
    every_state(repo)
    asked = []
    monkeypatch.setattr(Watch, "background", lambda self, argv: asked.append(argv))
    for node_id, word in (("ids", "running"), ("rule", "review"), ("table", "done")):
        seen, _ = at(repo, node_id, (120, 36), keys=["s"])
        assert (
            f"{node_id} is {word}: s splits a leaf still to do, so no planner was started" in seen["status"]
        )
    assert asked == []
    at(repo, "later", (80, 24), keys=["s"])
    assert asked == [["node", "split", "later"]]


def test_P_turns_plan_first_off_and_on_and_the_status_line_says_which(repo):
    every_state(repo)
    for now in (False, True):
        seen, _ = watch(repo, ["P"], size=(120, 36))
        with Store.open(repo) as store:
            assert plan.plan_first(store) is now
        assert f"plan first: {'on' if now else 'off'} (P)" in seen["status"]


def test_keys_typed_after_colon_or_slash_go_to_the_line_not_to_the_tree(repo, monkeypatch):
    """Recorded: `:node signoff x` typed fast ran s (split), r (run), d (drop) and u (undo) on the tree
    before the line took the keyboard."""
    every_state(repo)
    asked = []
    monkeypatch.setattr(Watch, "background", lambda self, argv: asked.append(argv))
    was = states(repo)

    from textual.widgets import Input

    async def typed(app, pilot, *keys):
        focus = Input.focus  # the line takes the keyboard only after the next refresh: type before it does
        Input.focus = lambda self, scroll_visible=True: self
        try:
            await pilot.press(*keys)
            await pilot.pause()
        finally:
            Input.focus = focus

    seen, _ = watch(
        repo, ["j"], before=lambda app, pilot: typed(app, pilot, "colon", *"node signoff rule", "enter")
    )
    assert asked == [["node", "signoff", "rule"]] and states(repo) == was  # no s, r, d or u on the tree
    assert seen["cursor"] == "api"  # and the keyboard is the tree's again
    seen, _ = watch(repo, [], before=lambda app, pilot: typed(app, pilot, "slash", *"table", "enter"))
    assert seen["cursor"] == "table" and states(repo) == was


def test_a_busy_store_never_crashes_the_screen(repo):
    """Two `graphene watch` started at once on a new store: one crashed with `database is locked`."""
    import sqlite3

    every_state(repo)
    busy = {"on": False}

    def open_store():
        if busy["on"]:
            raise sqlite3.OperationalError("database is locked")
        return Store.open(repo)

    async def go():
        app = Watch(repo, open_store, every=60)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            first = shown(app, app.query_one("#tree").region)[0]
            busy["on"] = True
            app.refresh_plan()
            for key in ("j", "y", "x", "w"):  # keys that read the plan, while it cannot be read
                await pilot.press(key)
                await pilot.pause()
            assert "the plan's store did not open (database is locked)" in str(
                app.query_one("#status").render()
            )
            assert shown(app, app.query_one("#tree").region)[0] == first  # the last screen stays up
            busy["on"] = False
            app.refresh_plan()
            await pilot.pause()
            assert "did not open" not in str(app.query_one("#status").render())
            busy["on"] = True

        fresh = Watch(repo, open_store, every=60)  # locked from the first look
        async with fresh.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert "did not open" in str(fresh.query_one("#status").render())

    asyncio.run(go())


def burst(*typed: str):
    """Keys as a terminal sends a fast typist's or a paste's: all queued at once, before the screen
    has acted on the first (pilot.press waits after each, which hid what a burst does)."""
    from textual import events

    names = {":": "colon", "/": "slash", " ": "space", "\r": "enter"}

    async def go(app, pilot):
        for text in typed:
            for ch in text:
                app.post_message(events.Key(names.get(ch, ch), None if ch == "\r" else ch))
        await pilot.pause()
        await pilot.pause()

    return go


def test_a_burst_after_colon_is_the_lines_not_the_trees(repo, monkeypatch):
    """Recorded in WezTerm: `:plan lo` typed fast opened the add prompt (the a of plan) and the
    executor's output (the l): the colon's action ran after the keys sent with it."""
    every_state(repo)
    was = states(repo)
    seen, app = watch(repo, [], before=burst(":plan log\r"))
    assert seen["screen"] != "Ask" and states(repo) == was
    assert "graphene plan log" in seen["status"] and app.view == "said"


def test_a_title_typed_at_once_after_a_goes_into_the_prompt(repo):
    """Recorded: `A` and a title typed in one burst opened the prompt empty and lost the words."""
    every_state(repo)
    watch(repo, [], before=burst("A", "tidy the tests\r"))
    with Store.open(repo) as store:
        assert any(n.title == "tidy the tests" for n in plan.nodes(store))


def test_a_leaf_in_review_that_did_not_land_says_why_and_what_lands_it(repo):
    """Recorded: the pane said "its check passed; it waits for your sign-off" and y, of a leaf whose
    work was on its branch only, because the person's README edit was uncommitted."""
    every_state(repo)
    why = ("git merge --no-ff --no-edit failed in /x: error: Your local changes to the following files "
           "would be overwritten by merge: README.md Please commit your changes or stash them")  # fmt: skip
    with Store.open(repo) as store:
        store.log_node("rule", plan._now(), "unlanded", "graphene run", None, None,
                       {"branch": "graphene/rule", "worktree": "/x", "why": [why]})  # fmt: skip
    for size in SIZES:
        seen, _ = at(repo, "rule", size)
        said = " ".join(seen["detail"].split())
        assert "did not land here: README.md has uncommitted changes in your checkout" in said
        assert "git merge graphene/rule, and y signs it off" in said and "waits for your sign-off" not in said


def test_search_finds_a_row_by_the_word_its_state_reads_as(repo):
    """What a person sees on a row is what `/` finds: `/came back` is the leaf that came back."""
    every_state(repo)
    seen, _ = watch(repo, ["slash", *"came back", "enter"])
    assert seen["cursor"] == "docs"


# -- folding (the Nemotron directive, item 7): a thirty-leaf plan at 80x24 --------------------------


def land(repo, store, node_id, path, text):
    """A leaf done by an executor, its work committed, as a run leaves it."""
    import subprocess

    plan.start(store, node_id, RUN, repo)
    (repo / path).write_text(text)
    plan.finish(store, node_id, RUN, checkout=repo)
    git = ["git", "-c", "user.email=t@e.com", "-c", "user.name=T"]
    subprocess.run([*git, "add", path], cwd=repo, check=True)
    subprocess.run([*git, "commit", "-qm", node_id], cwd=repo, check=True)


def api_done(repo):
    """TREE accepted, and both leaves under the API done: a finished subtree beside a ready leaf."""
    proposed(repo)
    person("plan", "accept")
    with Store.open(repo) as store:
        land(repo, store, "ids", "api.py", "def users():\n    return ['ids']\n")
        land(repo, store, "docs", "README.md", "users come back with their ids\n")


def rows_of(seen):
    return [r.rstrip() for r in seen["tree"] if r.strip()]


def test_a_finished_subtree_opens_folded_and_its_row_counts_its_leaves(repo):
    """A folded row read `done` or `2/5 done`, the same as open: nothing said what was inside. Now its
    word, in the word's column, is how many leaves are inside and in which states."""
    api_done(repo)
    for size in SIZES:
        seen, _ = watch(repo, ["j"], size=size)
        rows = rows_of(seen)
        api, schema = (next(r for r in rows if title in r) for title in ("the API", "the schema"))
        assert "▶ ✓ the API" in api and api.endswith("  2 done"), rows
        assert not any("users returns ids" in r for r in rows)
        assert api.index("  api ") == schema.index("  schema ")  # ids under ids
        assert api.index("2 done") == schema.index("ready")  # words under words
        assert "za unfold" in seen["status"]
        opened, _ = watch(repo, ["j", "z", "o"], size=size)
        rows = rows_of(opened)
        assert next(r for r in rows if "the API" in r).endswith("  done")  # open: its own word again
        assert any("users returns ids" in r for r in rows) and "za unfold" not in opened["status"]
        goal, _ = watch(repo, ["z", "a"], size=size)  # the goal's row folds like any other: every leaf
        assert rows_of(goal) == [rows_of(goal)[0]] and rows_of(goal)[0].endswith("  1 ready, 2 done")
        assert "za unfold" in goal["status"]


def test_a_folded_row_says_whose_move_is_inside_first_and_counts_the_rest(repo):
    """The states inside, as many as fit whole, whose move first (the person's, then the executors'),
    the rest as `n more`; each state in its own colour, the glyph the node's own."""
    from graphene_map.tui import inside, row

    assert inside(["done"] * 12) == "12 done"
    assert inside(["done", "running", "done", "done"]) == "1 running, 3 done"
    assert inside(["done", "running", "came back", "waiting", "proposed", "done"]) == "1 came back, 5 more"
    label = row("○", "0/5 done", "the API", "api", 60, 3, 19, inside="1 came back, 4 more")
    styles = {label.plain[s.start : s.end].strip(): str(s.style) for s in label.spans}
    assert styles.get("1 came back") == "magenta" and "4 more" not in styles and "○" not in styles
    every_state(repo)
    for size in SIZES:
        seen, _ = watch(repo, ["j", "z", "c"], size=size)  # the API: running, came back, waiting, …
        rows = rows_of(seen)
        api = next(r for r in rows if "the API" in r)
        assert api.endswith("  1 came back, 4 more") and api.lstrip("├└│ ").startswith("▶ ○ the API"), rows
        assert rows[0].index("1/8 done") == api.index("1 came back")  # the goal's word, above it
        seen, _ = at(repo, "schema", size, keys=["z", "c"])
        schema = next(r for r in rows_of(seen) if "  schema " in r)
        assert schema.endswith("  1 review, 2 more"), schema


def test_a_subtree_folds_when_it_finishes_on_screen_and_opens_when_it_is_reopened(repo):
    """It folded only when the screen opened: a sub-goal that finished while you watched stayed open,
    with all its leaves. A fold you make yourself stays until something inside changes."""
    from graphene_map.tui import _walk

    proposed(repo)
    person("plan", "accept")
    with Store.open(repo) as store:
        land(repo, store, "ids", "api.py", "def users():\n    return ['ids']\n")

    async def before(app, pilot):
        def api():
            return next(n for n in _walk(app.tree.root) if n.data == "api")

        async def then(act):
            with Store.open(repo) as store:
                act(store)
            app.refresh_plan()
            await pilot.pause()

        assert api().is_expanded  # docs is still to do
        await then(lambda s: land(repo, s, "docs", "README.md", "ids\n"))
        assert not api().is_expanded  # it finished while the screen was open
        await then(lambda s: plan.reopen(s, "docs", plan.Caller("alex", True), "the example is wrong"))
        assert api().is_expanded  # something inside moved: open again
        await then(lambda s: land(repo, s, "docs", "README.md", "ids, with an example\n"))
        assert not api().is_expanded
        app.tree.move_cursor(api())
        for key in ("z", "o"):
            await pilot.press(key)
        await then(lambda s: plan.start(s, "schema", RUN, repo))  # something else moves: a rebuild
        assert api().is_expanded  # the person opened it: it stays open

    watch(repo, [], before=before)


def test_zx_folds_as_the_screen_opened_and_keeps_the_cursor_in_sight(repo):
    """vim's zx: the folds as they were when the screen opened, then the row under the cursor shown."""
    api_done(repo)
    seen, _ = watch(repo, ["z", "R", "z", "x"])
    rows = rows_of(seen)
    assert next(r for r in rows if "the API" in r).endswith("  2 done")
    assert not any("users returns ids" in r for r in rows)
    seen, _ = watch(repo, ["z", "R", "j", "j", "z", "x"])  # on ids, inside the finished subtree
    assert seen["cursor"] == "ids" and any("users returns ids" in r for r in rows_of(seen))


def six_parts(store, by=None, parts=range(6)):
    """The goal, and sub-goals of five leaves each: accepted when a person proposes them, else the
    planner's tree, proposed."""
    alex = plan.Caller("alex", True)
    plan.set_goal(store, "csv feeds import cleanly, and every bad row is named", alex)
    plan.propose(store, [
        item
        for s in parts
        for item in ({"id": f"s{s}", "title": f"the part number {s} of the importer"}, *(
            {"id": f"s{s}-{k}", "title": f"leaf {k} of part {s}", "parent": f"s{s}",
             "scope": [f"f{s}{k}.py"], "check": "true"} for k in range(5)))
    ], by or alex)  # fmt: skip


def thirty(repo):
    """Six sub-goals of five leaves: one finished, one with a leaf that came back, one with a
    proposal under it, three ready."""
    with Store.open(repo) as store:
        six_parts(store)
        for k in range(5):
            land(repo, store, f"s0-{k}", f"f0{k}.py", "x\n")
        plan.start(store, "s1-0", SESSION, repo)
        plan.release(store, "s1-0", SESSION, "it needs the sku table, which is outside its scope")
        plan.propose(store, [{"id": "s2-new", "title": "an empty row is skipped", "parent": "s2",
                              "scope": ["n.py"], "check": "true"}], SESSION)  # fmt: skip


def test_a_thirty_leaf_plan_reads_at_80x24_as_its_outline(repo):
    """A tree taller than the screen, finished subtrees folded, opens as its outline: each sub-goal one
    row that counts what is inside, what waits on the person first, and the goal's pane names it. At
    120x36 it fits, and opens with only the finished subtree folded."""
    thirty(repo)
    seen, _ = watch(repo, [])
    rows = rows_of(seen)
    words = ["5 done", "1 came back, 4 ready", "1 proposed, 5 ready", "5 ready", "5 ready", "5 ready"]
    words = {f"s{s}": w for s, w in enumerate(words)}
    assert len(rows) == 7 and seen["sideways"] == 0, rows  # the goal and its six sub-goals, whole
    for i, word in words.items():
        mine = next(r for r in rows if f"  {i} " in r)
        assert mine.lstrip("├└│ ").startswith("▶") and mine.endswith(f"  {word}"), (i, mine)
    assert "s1-0 came back" in " ".join(" ".join(seen["side"]).split())
    wide, _ = watch(repo, [], size=(120, 36))
    rows = rows_of(wide)
    assert len(rows) == 1 + 6 + 5 * 5 + 1 and any("leaf 0 of part 1" in r for r in rows)
    assert next(r for r in rows if "  s0 " in r).endswith("  5 done")


def test_the_outline_is_measured_against_the_tree_pane_not_the_screen(repo):
    """The outline's rule compared the tree with the whole screen (21 rows at 80x24), but below 110
    columns the tree has half of it (10 rows): thirty leaves with four parts done are 17 rows, and the
    leaf that came back, in the last part, opened out of sight."""
    with Store.open(repo) as store:
        six_parts(store)
        for s in range(4):
            for k in range(5):
                land(repo, store, f"s{s}-{k}", f"f{s}{k}.py", "x\n")
        plan.start(store, "s5-4", SESSION, repo)
        plan.release(store, "s5-4", SESSION, "it needs the sku table, which is outside its scope")
    seen, _ = watch(repo, [])
    rows = rows_of(seen)
    assert len(rows) == 7 and rows[-1].endswith("  1 came back, 4 ready"), rows
    wide, _ = watch(repo, [], size=(120, 36))  # 17 rows fit its 33: only the finished parts fold
    rows = rows_of(wide)
    assert len(rows) == 17 and rows[-1].endswith("  came back"), rows


def test_a_plan_that_arrives_while_the_screen_is_open_reads_as_it_would_have_opened(repo):
    """The outline was drawn only when the screen opened: a plan landing on an open screen (the
    planner's, the demo's) came in whole, ten rows of 33 in sight at 80x24. A sub-goal that arrives in
    a tree taller than its pane comes in folded; one the person opened stays open."""
    from graphene_map.tui import _walk

    alex = plan.Caller("alex", True)
    with Store.open(repo) as store:
        plan.set_goal(store, "csv feeds import cleanly, and every bad row is named", alex)

    async def arrive(app, pilot):
        thirty(repo)
        app.refresh_plan()
        await pilot.pause()

    seen, _ = watch(repo, [], before=arrive)
    fresh, _ = watch(repo, [])
    assert rows_of(seen) == rows_of(fresh) and len(rows_of(seen)) == 7, rows_of(seen)
    got = {}

    async def grow(app, pilot):
        for key in ["slash", *"s1", "enter", "escape", "z", "o"]:  # the part with the leaf that came back
            await pilot.press(key)
        with Store.open(repo) as store:
            six_parts(store, SESSION, parts=[6])  # the planner proposes one part more
        app.refresh_plan()
        await pilot.pause()
        got.update({n.data: n.is_expanded for n in _walk(app.tree.root) if n.data in ("s1", "s6")})
        got["s6 says"] = app.tree.rows["s6"][5]  # below the pane's last row: what its row reads

    watch(repo, [], before=grow)
    assert got == {"s1": True, "s6": False, "s6 says": "5 proposed"}


def test_a_leaf_with_a_proposal_under_it_is_counted_and_shown_as_the_leaf_it_is(repo):
    """A leaf with an executor's proposal under it (`node add --parent`) is still a leaf. Its folded
    sub-goal left it out of the count, and said `1 proposed, 4 ready` of a part whose leaf came back;
    and the outline folded the leaf too, so opening its sub-goal still hid the proposal."""
    thirty(repo)
    with Store.open(repo) as store:
        plan.start(store, "s3-0", SESSION, repo)
        plan.propose(store, [{"id": "s3-0a", "title": "the sku table first", "parent": "s3-0",
                              "scope": ["sku.py"], "check": "true"}], SESSION)  # fmt: skip
        plan.release(store, "s3-0", SESSION, "it needs the sku table, proposed under it")
    seen, _ = watch(repo, [])
    assert next(r for r in rows_of(seen) if "  s3 " in r).endswith("  1 came back, 5 more")
    seen, _ = at(repo, "s3", (80, 24), keys=["z", "o"])
    assert any("  s3-0a " in r and r.endswith("  proposed") for r in rows_of(seen)), rows_of(seen)


def test_help_lists_the_fold_keys(repo):
    proposed(repo)
    for size in SIZES:

        async def before(app, pilot):
            await pilot.press("question_mark")
            await pilot.pause()
            text = "\n".join(shown(app, app.screen.query_one("#help").region))
            for key in ("za", "zo zc", "zR zM", "zx"):
                assert key in text, (key, text)

        watch(repo, [], size=size, before=before)
    from graphene_map.tui import HELP

    fold = dict(dict(HELP)["fold"])
    assert "counts the leaves inside" in fold["zo zc"] and "as it opened" in fold["zx"]


def test_the_bill_is_on_the_status_line_and_in_the_leafs_pane(repo):
    """What the Nemotron executors cost, from Token Factory's usage at list price: the plan's in the
    status line, the leaf's in its pane. Nothing is said about a bill where no model was called."""
    person("node", "add", "users returns ids", "--id", "ids", "--scope", "api.py", "--check", "true")
    plain, _ = watch(repo, ["j"], size=(120, 36))
    assert "list price" not in plain["status"] and "bill" not in plain["detail"]
    with Store.open(repo) as store:
        for dollars in (0.0101, 0.0022):
            store.log_node("ids", plan._now(), "usage", "run:nemotron", None, None,
                           {"model": "nvidia/Nemotron-3-Nano-fake", "calls": 3, "prompt_tokens": 900,
                            "completion_tokens": 80, "dollars": dollars})  # fmt: skip
        store.log_node("*", plan._now(), "usage", "planner:nemotron", None, None,
                       {"model": "nvidia/Nemotron-3-Ultra-fake", "calls": 2, "dollars": 0.02})  # fmt: skip
    seen, _ = watch(repo, ["j"], size=(120, 36))
    assert seen["status"].splitlines()[0].endswith("$0.03 at list price")  # the planner's and the leaf's
    assert "bill $0.0123 at list price · 6 calls · Nemotron-3-Nano-fake" in " ".join(seen["detail"].split())


# -- the forks, the step up and the sandbox (what the Nemotron executor writes on the leaf's log) -----

NANO, SUPER = "nvidia/Nemotron-3-Nano-fake", "nvidia/Nemotron-3-Super-fake"
NEMOTRON = plan.Caller("run:nemotron", False, "5e55-run-session")
WHY = {"lost": "another fork's check passed first", "passed": "its check passed first",
       "check failed": "its check failed (exit 1), then it stopped calling tools",
       "gave up": "the greeting is also in other.py"}  # fmt: skip


def forked(repo, states, model=NANO, box=None, attempt=1):
    """A leaf held by the Nemotron executor, with its model's row and a row for each fork in ``states``,
    as executor.fork_and_pick writes them; ``box``: each fork's sandbox, as its rows carry it."""
    alex = plan.Caller("alex", True)
    with Store.open(repo) as store:
        if not plan.goal(store):
            plan.set_goal(store, "a friendlier app", alex)
            leaves = [{"id": "greet", "title": "say hello", "scope": ["api.py"], "check": "true"},
                      {"id": "schema", "title": "the schema", "scope": ["schema.py"], "check": "true"}]
            plan.propose(store, leaves, alex)
            plan.start(store, "greet", NEMOTRON, repo)
        store.log_node("greet", plan._now(), "model", NEMOTRON.label, NEMOTRON.session_id, None,
                       {"attempt": attempt, "model": model})  # fmt: skip
        for k, state in enumerate(states, 1):
            said = {"fork": k, "of": len(states), "model": model, "state": state, "why": WHY.get(state, "")}
            store.log_node("greet", plan._now(), "fork", NEMOTRON.label, NEMOTRON.session_id, None,
                           said | (box or {}))  # fmt: skip


def test_a_leaf_with_forks_shows_each_under_it_in_the_one_row_grammar(repo):
    """fork_and_pick ran N conversations and only the bill at the end said so. Each fork is now a row
    under its leaf: its model where a title goes, which fork where an id goes, its state in the word's
    column and colour (a fork that lost is nobody's move: dim; red is still only a failed command)."""
    from rich.style import Style

    from graphene_map.tui import _walk

    forked(repo, ["running", "lost", "check failed"])

    async def before(app, pilot):
        for node in _walk(app.tree.root):
            if isinstance(node.data, tuple):
                spans = app.tree.render_label(node, Style(), Style()).spans
                word = app.forks["greet"][node.data[1] - 1]["state"]
                colour = {"running": "yellow", "lost": "dim", "check failed": "dim"}[word]
                assert colour in " ".join(str(s.style) for s in spans) and "red" not in str(spans), word

    for size in SIZES:
        seen, _ = watch(repo, [], size=size, before=before)
        rows = [r.rstrip() for r in seen["tree"] if r.strip()]
        leaf = next(k for k, r in enumerate(rows) if "  greet " in r)
        forks = rows[leaf + 1 : leaf + 4]
        assert rows[leaf].endswith("running")
        for k, (r, word) in enumerate(zip(forks, ["running", "lost", "check failed"], strict=True), 1):
            assert "Nemotron-3-Nano-fake" in r and r.endswith(word), (size, r)
            assert r.index(f"fork {k}") == rows[leaf].index("  greet ") + 2  # which fork, in the id's column
            assert r.index(word) == rows[leaf].index("running")  # its state, in the word's column
        assert seen["sideways"] == 0


def test_forks_that_arrive_on_an_open_screen_are_drawn_and_fold_away_with_their_finished_leaf(repo, finish):
    """A screen reads the store every second: the rows come in as the executor writes them, the cursor
    stays on a fork's row as its state changes, and goes to the leaf when the finished leaf folds."""
    forked(repo, [])

    async def before(app, pilot):
        def tree():
            app.refresh_plan()
            rows = shown(app, app.query_one("#tree").scrollable_content_region)
            return [r.rstrip() for r in rows if r.strip()]

        forked(repo, ["running", "running"])
        assert any(r.endswith("fork 1  running") for r in tree())
        for key in ("j", "j"):
            await pilot.press(key)
        forked(repo, ["lost", "passed"])
        rows = tree()
        assert any(r.endswith("fork 1  lost") for r in rows) and app.tree.cursor_node.data == ("greet", 1)
        with Store.open(repo) as store:
            finish(store, repo, "greet", NEMOTRON)
        assert "fork 1" not in " ".join(tree()) and app.tree.cursor_node.data == "greet"

    watch(repo, [], before=before)


def test_every_key_on_a_fork_row_acts_on_its_leaf_or_says_why_not(repo, monkeypatch):
    """A fork is not a node, and no command takes one: on its row each key is its leaf's, the bottom
    line says so, and nothing crashes."""
    forked(repo, ["running", "running"])
    started = []
    monkeypatch.setattr(Watch, "background", lambda self, argv: started.append(argv))
    monkeypatch.setenv("EDITOR", "true")  # an editor that changes nothing
    on_fork = ["j", "j"]  # the goal, greet, its fork 1
    seen, _ = watch(repo, on_fork)
    assert seen["cursor"] == "greet" and "greet · running" in seen["detail"]
    assert seen["status"].splitlines()[1].startswith("fork 1: keys act on greet · l output · x release")
    seen, _ = watch(repo, [*on_fork, "enter"])
    assert seen["detail"].startswith("record · it scrolls") and "greet · running" in seen["detail"]
    seen, _ = watch(repo, [*on_fork, "l"])
    assert "greet · output of attempt" in seen["detail"]
    for key, said in [("y", "graphene plan accept greet"), ("s", "greet is running"),
                      ("w", "greet has no 'w'"), ("b", "greet has no 'b'"), ("n", "greet has no 'n'"),
                      ("e", "graphene node edit greet"), ("E", "graphene plan edit greet")]:  # fmt: skip
        seen, _ = watch(repo, [*on_fork, key])
        assert said in seen["status"], (key, seen["status"])
    watch(repo, [*on_fork, "r"])
    watch(repo, [*on_fork, "a", "escape", "A", "escape", "V", "escape", "z", "a", "question_mark", "escape"])
    assert started == [["run", "--parallel", "4", "--node", "greet"]]
    seen, _ = watch(repo, [*on_fork, "x"])
    assert "graphene node release greet" in seen["status"] and states(repo)["greet"] == "open"
    with Store.open(repo) as store:  # held again, and d on its fork's row drops the leaf, as on the leaf's
        plan.start(store, "greet", NEMOTRON, repo)
    forked(repo, ["running"])
    seen, _ = watch(repo, [*on_fork, "d"])
    assert "graphene node drop greet" in seen["status"] and states(repo)["greet"] == "dropped"


def test_a_step_up_the_ladder_names_the_model_on_the_bottom_line_and_in_the_leafs_pane(repo):
    """--model given twice stepped up on attempt 2 and nothing on screen named it. At 80x24, with the
    cursor on the goal (nobody pointed at the leaf), the bottom line says it; the leaf's pane keeps it."""
    forked(repo, [])  # attempt 1, on Nano
    seen, _ = watch(repo, [])
    assert "stepped up" not in seen["status"]
    why = "attempt 1 refused: greet is not done: `true` failed"
    with Store.open(repo) as store:  # the executor's row for attempt 2, as it began
        store.log_node("greet", plan._now(), "model", NEMOTRON.label, NEMOTRON.session_id, None,
                       {"attempt": 2, "model": SUPER, "from": NANO, "why": why})  # fmt: skip
    seen, _ = watch(repo, [])
    said = "greet stepped up to Nemotron-3-Super-fake: attempt 1 refused"
    assert seen["cursor"] is None and seen["status"].splitlines()[1].startswith(said)
    seen, _ = watch(repo, ["j"])
    assert f"model Nemotron-3-Super-fake, stepped up from Nemotron-3-Nano-fake: {why}" in " ".join(
        seen["detail"].split()
    )


def test_a_step_up_waits_for_a_free_bottom_line_and_none_is_lost(repo):
    """The news of a step up replaced what a command had just said, a failure included, and of two
    leaves that stepped up between refreshes only the last was ever said. Now each is said when the
    bottom line is free, one at a time, while its leaf runs."""
    forked(repo, [])  # greet, attempt 1 on Nano
    other = plan.Caller("run:nemotron", False, "5e56-run-session")
    with Store.open(repo) as store:
        plan.start(store, "schema", other, repo)

    def up(node_id: str) -> None:
        step = {"attempt": 2, "model": SUPER, "from": NANO, "why": f"{node_id} refused"}
        with Store.open(repo) as store:
            store.log_node(node_id, plan._now(), "model", NEMOTRON.label, None, None, step)

    async def before(app, pilot):
        async def bottom(*keys: str) -> str:
            for key in keys:
                await pilot.press(key)
                await pilot.pause()
            app.refresh_plan()
            return str(app.query_one("#status").render()).splitlines()[1]

        assert (await bottom("j", "s")).startswith("✗ greet is running")  # a command's refusal
        up("greet")
        up("schema")  # both between two refreshes
        assert (await bottom()).startswith("✗ greet is running")  # what the command said stays
        assert (await bottom("k")).startswith("greet stepped up to Nemotron-3-Super-fake: greet refused")
        assert (await bottom()).startswith("greet stepped up")  # said until the person moves on
        assert (await bottom("j")).startswith("schema stepped up to Nemotron-3-Super-fake: schema refused")
        assert "stepped up" not in await bottom("j")  # each said once: the keys again

    watch(repo, [], before=before)


def test_the_leafs_pane_shows_its_sandbox_its_operations_and_seconds_and_its_bill(repo, finish, monkeypatch):
    """The pane said nothing of where a leaf ran. Now: the checkpoint it made or forked (its image, short),
    and once the attempt is over, the operations and seconds its sandbox took (its forks', added up)."""
    from graphene_map.node_record import sandbox

    image = "sha256:3f2a1b9c0d4e5f6a7b8c9d0e"
    made = {"placement": "sandbox", "box": "docker", "image": image, "checkpoint": "made", "ops": 4,
            "seconds": 7.5}  # fmt: skip
    box = {"image": image, "checkpoint": "forked"}
    forked(repo, [])
    with Store.open(repo) as store:
        store.log_node("greet", plan._now(), "placement", NEMOTRON.label, None, None, made)
    forked(repo, ["running", "running"], box=box | {"ops": 0, "seconds": 0.0}, attempt=1)
    seen, _ = watch(repo, ["j"])  # running: its checkpoint, and no count until the attempt is over
    flat = " ".join(seen["detail"].split())
    assert "sandbox made, image 3f2a1b9c0d4e" in flat and "operations" not in flat, seen["detail"]
    with Store.open(repo) as store:
        for k, (state, ops, seconds) in enumerate([("passed", 9, 12.25), ("lost", 3, 4.0)], 1):
            said = {"fork": k, "of": 2, "model": NANO, "state": state, "why": WHY[state], "ops": ops}
            store.log_node("greet", plan._now(), "fork", NEMOTRON.label, None, None,
                           said | box | {"seconds": seconds})  # fmt: skip
        store.log_node("greet", plan._now(), "usage", NEMOTRON.label, None, None,
                       {"model": NANO, "calls": 7, "dollars": 0.0031, "forks": 2, "winner": 1})  # fmt: skip
        monkeypatch.setattr(plan, "sandboxed", lambda store, node: None)  # its check here: no sandbox to fork
        finish(store, repo, "greet", NEMOTRON)
    for size in SIZES:
        seen, _ = at(repo, "greet", size)
        flat = " ".join(seen["detail"].split())
        assert "sandbox made, image 3f2a1b9c0d4e · 12 operations · 16.2 s in its 2 forks" in flat, size
        assert "bill $0.0031 at list price · 7 calls · Nemotron-3-Nano-fake" in flat
    ended = made | {"ops": 14, "seconds": 23.4}  # a leaf that did not fork: its row at the attempt's end
    rows = [{"kind": "started", "detail": {}}, {"kind": "placement", "detail": made},
            {"kind": "placement", "detail": ended}]  # fmt: skip
    assert sandbox(rows) == ended


def test_the_record_says_which_fork_won_and_why_each_other_one_did_not(repo):
    forked(repo, ["lost", "passed", "gave up", "check failed"], box={"ops": 5, "seconds": 3.25})
    for size in SIZES:
        seen, _ = at(repo, "greet", size, keys=["enter"])
        record = " ".join(seen["detail"].split())
        assert re.search(r"^forks$", seen["detail"], re.M), seen["detail"]
        said = [f"fork 2 of 4 won: {WHY['passed']} · Nemotron-3-Nano-fake · 5 operations, 3.2 s",
                f"fork 1 of 4 lost: {WHY['lost']}", f"fork 3 of 4 gave up: {WHY['gave up']}",
                f"fork 4 of 4 check failed: {WHY['check failed']}"]  # fmt: skip
        assert all(s in record for s in said), (size, record)
        assert [record.index(s) for s in said] == sorted(record.index(s) for s in said)  # the winner first


def test_the_forks_of_a_run_stopped_mid_fork_read_stopped_not_running(repo):
    """:stop or Ctrl-C mid-fork: the run hands the leaf back, and the fork threads end before they write
    their end. Its forks read running, in the executor's yellow, on its row and in its record, while
    nothing ran. Now they read stopped (dim: nobody's move), and the record says why, with no count."""
    from rich.style import Style

    from graphene_map.run import STOPPED
    from graphene_map.tui import _walk

    forked(repo, ["running", "running"], box={"checkpoint": "forked", "ops": 0, "seconds": 0.0})
    with Store.open(repo) as store:
        plan.release(store, "greet", NEMOTRON, STOPPED)

    async def before(app, pilot):
        for node in _walk(app.tree.root):
            if isinstance(node.data, tuple):
                spans = " ".join(str(s.style) for s in app.tree.render_label(node, Style(), Style()).spans)
                assert "yellow" not in spans and "dim" in spans, spans

    for size in SIZES:
        seen, _ = watch(repo, [], size=size, before=before)
        rows = rows_of(seen)
        leaf = next(k for k, r in enumerate(rows) if "  greet " in r)
        assert rows[leaf].endswith("came back")
        for k, r in enumerate(rows[leaf + 1 : leaf + 3], 1):
            assert r.endswith(f"fork {k}  stopped"), rows
        assert not any(r.endswith("running") for r in rows), rows
        seen, _ = at(repo, "greet", size, keys=["enter"])
        record = " ".join(seen["detail"].split())
        said = "fork 1 of 2 stopped: its executor was stopped before this fork ended · Nemotron-3-Nano-fake"
        assert said in record and "fork 1 of 2 running" not in record and "operations" not in record, record
