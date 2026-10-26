"""docs/HOW_IT_WORKS.md is the reference a user reads after the README: under 3,700 words, with every section
it promises, in order. The cap was 3,000 until 10 October 2026, when the reference gained what init does to
a Claude Code session and how to undo it, the run's first line and red first's warnings, and what the record
and the merge message now say; raised once, on purpose, after the words no claim pinned were cut. It was
3,300 until 19 October, when the reference gained the cockpit's keys in the night's words, the plan's text
with an example, `review: every` and `notify`; raised again after what it said twice was said once. It was
3,500 until the seam review's fixes (19 October) added three facts: a run going takes what a second run
would start, a task of yours is done on your word, and proposals ring once a batch; raised after what it
said twice (a told note, an attempt's reads, the goal's command) was cut. It was 3,600 until an adversarial
pass at the write gate (19 October) found what the hook does not read before a write; raised, since a limit
admitted is worth its words. It was 3,700 until forks (20 October): the reference gained a section on them,
with the rule that keeps one in its five steps and the commands around it, the graph's new direction and the
gate that fails closed; raised to 4,300, past the 4,000 the night's brief allowed, after what it said twice
(the meter's clocks, `node show`'s attempt line) was said once and the section still did not fit under it. It
was 4,300 until the revamp night (26 October), when the graph gained its gestures (`+` a step after a task,
`L` a link between two) and The views their one sentence; the settings table gained `auto`, `budget`,
`tasks` and `rounds` with the paragraph on `graphene config set`; and the executors section gained the other
hosts behind Graphene's own loop (`--endpoint`), the `{prompt}` and `{prompt_file}` recipes for other CLI
agents with how they are held, a port per task, and Privacy a bullet for the other hosts; raised to 5,000,
nothing cut, a row a setting being the table's own rule and a key with no sentence a key nobody finds. It
was 5,000 until the same night's later additions (`checks:`, `--plan`, `:auto`, `.git/` and the envelope's
limits); raised to 5,100."""

import re
from pathlib import Path

import pytest
from test_plan_cli import agent, repo  # noqa: F401  (repo: a fixture)

HOW = (Path(__file__).resolve().parents[1] / "docs/HOW_IT_WORKS.md").read_text(encoding="utf-8")
SECTIONS = ["The plan", "The board", "The views", "Plan first", "Ask", "Run", "Forks", "The executors",
            "The meter", "Where each mechanism ends", "The record", "The settings", "Privacy", "FAQ",
            "The rest"]  # fmt: skip


def test_it_is_under_the_cap():
    assert len(HOW.split()) < 5100


def test_every_section_is_there_in_order():
    headings = [line[3:] for line in HOW.splitlines() if line.startswith("## ")]
    assert headings == SECTIONS


def test_the_settings_table_names_every_setting_with_its_values():
    """`review` and `notify` (18 October) were in `graphene config` and missing from the table. The envelope's
    numbers (26 October: `budget`, `tasks`, `rounds`) have a row each too, and `config set` is named."""
    from graphene_map import settings as S

    bar = "\\|"  # a | inside a table cell
    for key, values in S.SCALARS.items():
        assert f"| `{key}: {bar.join(values)}` |" in HOW, key
    for key in S.NUMBERS:
        assert f"| `{key}: " in HOW, key
    assert "`graphene config set KEY VALUE` changes one" in HOW


def test_a_sign_off_lands_as_the_reference_says_checked_on_its_merge_and_one_at_a_time():
    """The review lane (18 October): `review: every` sends every task that passes to review, a sign-off's
    merge is checked as a run's is, and sign-offs take turns. The reference said a sign-off's merge was not
    checked ("that is your yes"); dropping `ran=ran` from the sign-off's land call puts that back."""
    import inspect

    from graphene_map import plan as P
    from graphene_map import settings as S

    assert S.REVIEWS == ("off", "every")
    source = inspect.getsource(P.signoff) + inspect.getsource(P._signoff)
    assert "fcntl.flock" in source and "ran=ran" in source  # one at a time; checked with what landed since
    said = " ".join(HOW.split())
    assert "A leaf that needs a sign-off, or every leaf under `review: every`, is committed" in said
    assert "or `graphene node signoff`, makes the merge, checked the same way" in said
    ends = said.split("## Where each mechanism ends")[1].split(" ## ")[0]
    assert "that is your yes" not in ends and "Sign-offs take turns" in ends
    assert "Under `review: every`, what needs a task waits for your sign-off" in ends


def test_the_views_give_each_key_the_verb_the_cockpit_runs():
    """The night's words (18 October): one verb for each key, on the screen and here. The reference said `w`
    gives, `x` hands it back, `Enter` takes and `i` opens it up, and had no `A`, no panes and no `Esc`. On 20
    October the graph turned to flow into the goal, and `f` forks a task: the reference says both."""
    from graphene_map.cockpit import app as A
    from graphene_map.cockpit import details as D

    verbs = {"t": "tell", "w": "allow", "x": "back", "A": "accept-all", "i": "details", "f": "fork"}
    assert all(A.KEYS_TO_VERBS[key] == verb for key, verb in verbs.items())
    assert [D.KEYS[k] for k in "1234c"] == [*D.PANES, "changes"] and A.TABS == ("cockpit", "graph", "map")
    views = " ".join(HOW.split("## The views")[1].split("## ")[0].split())
    said = ("opens the cockpit (`c`)", "`⏎` its own move (accept, take the default, try again, sign off)",
            "`A` accept every proposal", "`t` tell its agent a line", "`w` widen the scope",
            "`x` hand back a running task or reopen a finished one",
            "`f` fork it (N agents at once, the check", "`i` details (panes `1` to `4`; `c`",
            "`g` is the graph: what must land before what, flowing into your goal", "`m` the map",
            "`Tab` goes on, `Esc` comes back")  # fmt: skip
    for words in said:
        assert words in views, words


def test_the_views_say_what_needs_you_as_the_cockpit_counts_and_rings_it():
    """A write the gate stopped counts in "need you" (18 October), and what newly needs you rings the
    terminal with a notice saying why, unless `notify: off`."""
    from graphene_map.cockpit.app import needs
    from graphene_map.cockpit.model import Model, Task, needs_you

    stopped = Task("ids", "users return ids", "running", agent="1", stopped=[("db/ids.py", 1.0)])
    m = Model("users come back with their ids")
    m.tasks = {"ids": stopped}
    assert needs_you(stopped) and "agent 1 was stopped writing db/ids.py: w widens it" in needs(m).values()
    views = " ".join(HOW.split("## The views")[1].split("## ")[0].split())
    assert "A write the gate stopped needs you too" in views and "(`notify: off` quiets it)" in views


def test_the_views_say_what_rings_the_terminal_and_not_that_anything_needing_you_does():
    """The views said anything new that needs you rings the terminal. A proposal and a task of yours count
    in "need you" and ring nothing (`needs` leaves them out): what rings is a question, a task that came
    back, one waiting for its sign-off and a write the gate stopped."""
    from graphene_map.cockpit.app import needs
    from graphene_map.cockpit.model import Model, Question, Task, needs_you

    m = Model("users come back with their ids")
    m.questions = [Question("q", "which id?", "uuid", [])]
    m.tasks = {t.id: t for t in (
        Task("back", "users return ids", "came back", agent="1"), Task("review", "document it", "review"),
        Task("stop", "the schema", "running", agent="2", stopped=[("db/ids.py", 1.0)]),
        Task("new", "a proposal", "proposed"), Task("mine", "a task of yours", "yours"),
    )}  # fmt: skip
    assert all(needs_you(t) for t in m.tasks.values())
    assert {key.split(":")[0] for key in needs(m)} == {"q", "back", "review", "stop"}  # not new, nor mine
    views = " ".join(HOW.split("## The views")[1].split("## ")[0].split())
    assert "A new question, a task that came back, a sign-off or a stopped write rings the terminal" in views


def test_the_board_table_says_t_tells_the_selected_task_as_the_cockpit_runs_it(tmp_path):
    """The table said `t` puts up a note of yours (`graphene board note WORDS`); the cockpit's t needs a
    task and says the note about it (docs-audit, 18 October)."""
    from graphene_map.cockpit.model import Model, Task
    from graphene_map.cockpit.verbs import Doer

    ran = []
    doer = Doer(tmp_path, lambda said: None, lambda: None)
    doer.run = lambda argv, done="": ran.append(argv) or 0
    m = Model("users come back with their ids")
    m.tasks = {"ids": Task("ids", "users return ids", "running", agent="1")}
    doer.tell(m, "ids", "keep the old ids too")
    assert ran == [["board", "note", "keep the old ids too", "--about", "ids"]]
    assert "| `graphene board note WORDS --about ID` | `t` on a task |" in HOW


def test_it_names_every_mark_that_makes_a_caller_an_agent():
    """docs-audit (18 October): the reference named three of the marks, and `graphene init` refused an agent
    whose only one was AI_AGENT. Each variable `plan.caller` reads that makes an agent, whatever its value,
    is named, and nothing else is."""
    import inspect

    from graphene_map import plan as P

    read = {*re.findall(r"env(?:\.get\(|\[)[\"']([A-Z_]+)", inspect.getsource(P.caller)), *P.AGENT_MARKS}
    marks = {v for v in read if not any(P.caller({v: x}, tty=True).person for x in ("1", "person:me"))}
    assert {"CLAUDECODE", "CODEX_SESSION_ID", "AI_AGENT", "GRAPHENE_NODE"} <= marks
    said = " ".join(HOW.split("by the variables its CLI sets")[1].split(". ")[0].split())
    assert sorted(re.findall(r"`([A-Z_]+)`", said)) == sorted(marks)


@pytest.mark.usefixtures("repo")
def test_the_plan_texts_example_is_one_an_agent_proposes_as_it_stands():
    """A stranger wrote a plan from plan_text.py's source (18 October): the reference showed only `- title
    [id]`. Its example, as it stands, is proposed here, each key it shows read where it says."""
    from graphene_map import board as B
    from graphene_map import plan as P
    from graphene_map.store import Store

    block = HOW.split("`graphene plan --text`")[1].split("```\n")[1]
    proposed = agent("plan", "propose", "-", input=block)
    assert proposed.exit_code == 0, proposed.output
    assert "goal (proposed): customers download their invoices as PDF" in proposed.stdout
    with Store.open(Path.cwd()) as store:
        render, template = P.get(store, "render"), P.get(store, "template")
        items = {item["id"]: item for item in B.items(store)}
    assert (render.parent, template.parent) == ("pdf", "pdf")  # two leaves under a sub-goal
    assert render.scope == ["src/pdf/**", "tests/pdf/**"] and render.check == "pytest tests/pdf"
    assert render.needs == ["template"]
    lib = items["lib"]
    assert (lib["kind"], lib["default"], lib["options"][0]["text"]) == ("question", "weasyprint", "reportlab")
    assert lib["options"][0]["then"] == ["scope render + vendor/reportlab/**"]
    assert items["untested"]["kind"] == "risk"
