"""The cockpit screen as lines: a frame is a function of the model, so it is tested without a terminal."""

from cockpit_scene import scene

from graphene_map.cockpit import rows
from graphene_map.cockpit.model import Model, Task


def plain(lines) -> list[str]:
    return [line.plain() for line in lines]


def test_every_line_fits_the_width_asked():
    for width in (40, 60, 80, 120):  # the head at the narrowest the screen draws (40)
        assert all(line.width() <= width for line in rows.build_head(scene(), width))
    for width in (60, 80, 120):
        assert all(line.width() <= width for line in rows.build_cockpit(scene(), width))


def test_the_head_says_what_waits_for_the_person_what_runs_and_what_is_proven_in_one_line():
    top = plain(rows.build_head(scene(), 80))
    assert top[0].strip() == "users come back with their ids"
    assert top[1].split()[:7] == ["4", "need", "you", "1", "running", "1/5", "proven"]  # a proposal counts,
    # and so does the running task with a write the gate stopped (`ids`)
    assert top[1].split()[7].startswith("▰") and len(top) == 3  # the bar on the same line; then the rule
    bar = [s for s in rows.build_head(scene(), 80)[1].segs if "▰" in s.text]
    assert [s.style for s in bar] == ["#8ab17d", "#e9c46a"] and len(bar[0].text) == len(bar[1].text)  # 1, 1
    scrolled = plain(rows.build_cockpit(scene(), 80))  # the rows, which scroll, have neither
    assert not any("need you" in line or "users come back" in line for line in scrolled)


def test_the_headline_is_your_goal_and_with_none_it_says_how_to_give_one():
    head = rows.build_head(scene(), 80)[0]
    assert head.plain().strip() == "users come back with their ids" and head.segs[0].style == "bold"
    m = scene()
    m.source = "replay"
    assert rows.build_head(m, 80)[0].plain().rstrip().endswith("users come back with their ids · replay")
    for none in ("", "no goal yet"):  # the second is what the plan's reader says of a plan with no goal
        m = scene()
        m.goal = none
        head = rows.build_head(m, 80)[0]
        assert ':plan goal "' in head.plain() and not any("bold" in s.style for s in head.segs)
        assert head.width() <= 80 and rows.build_head(m, 60)[0].width() <= 60


def test_the_question_comes_first_and_the_default_and_the_options_are_buttons():
    lines = rows.build_cockpit(scene(), 80)
    question = next(line for line in lines if line.row == "q")
    assert plain([question])[0].lstrip().startswith("?") and "Keep old ids working?" in question.plain()
    actions = [s.action for s in question.segs if s.action]
    assert actions == ["take", "pick:1"]


def test_a_question_a_proposal_and_a_risk_have_marks_of_their_own_and_their_words_line_up():
    from graphene_map.cockpit.model import Question

    m = scene()
    m.questions.append(Question("r", "Old ids have no checksum", "noted", [], kind="risk"))
    m.questions[0].options = ["drop old ids now", "keep them until July"]
    lines = {}
    for line in rows.build_cockpit(m, 120):
        lines.setdefault(line.row, line)  # a row's first line: an open one has more under it
    marks = {row: lines[row].plain()[2] for row in ("q", "r", "docs")}
    assert marks == {"q": "?", "r": "!", "docs": "+"}
    assert "#e9a23b" in lines["r"].segs[1].style and "#4cc9f0" in lines["docs"].segs[1].style
    starts = {lines[row].plain().index(words) for row, words in (
        ("q", "Keep old ids"), ("r", "Old ids"), ("ids", "users return"), ("docs", "docs for"))}  # fmt: skip
    assert len(starts) == 1  # one left edge
    assert "1 drop old ids now" in lines["q"].plain() and "2 keep them until July" in lines["q"].plain()
    assert all(line.width() <= 60 for line in rows.build_cockpit(m, 60))


def test_a_running_row_has_its_agent_and_its_numbers_and_the_selected_one_opens():
    m = scene()
    text = "\n".join(plain(rows.build_cockpit(m, 100)))
    assert "● 1  users return ids" in text and "✎2/9" in text and "✓1/3" in text
    assert all(k in text for k in ("t tell", "w widen db/ids_2.py", "x hand back", "i details"))
    assert not any(old in text for old in ("give it", "pull back", "everything"))  # one word for each key
    m.selected = "docs"  # a proposed row does not open with an agent's verbs
    assert "t tell" not in "\n".join(plain(rows.build_cockpit(m, 100)))


def test_a_running_rows_pace_is_drawn_in_the_running_amber_not_in_its_agents_colour():
    from graphene_map.cockpit.look import SPARK, STATE_GLYPH, color_of

    row = next(line for line in rows.build_cockpit(scene(), 100) if line.row == "ids")
    [pace] = [s for s in row.segs if any(c in SPARK for c in s.text)]
    assert pace.style.startswith(STATE_GLYPH["running"][1].split()[-1]) and color_of("1") not in pace.style


def test_a_row_whose_write_was_stopped_says_on_its_right_the_key_that_widens_it_and_the_path():
    m = scene()
    m.selected = "docs"
    for width in (60, 80, 120):
        row = next(line for line in rows.build_cockpit(m, width) if line.row == "ids")
        [hint] = [s for s in row.segs if s.action == "allow"]
        assert hint.text.startswith("w widen ") and hint.text.strip().endswith("ids_2.py")
        assert "#e9a23b" in hint.style  # amber: a key to press, not an alarm
        assert row.width() <= width and "!1" not in row.plain()
    m.tasks["ids"].stopped.append(("db/other.py", 97.0))
    row = next(line for line in rows.build_cockpit(m, 120) if line.row == "ids")
    assert "w widen db/other.py +1" in row.plain()  # the last one stopped, and how many more


def test_a_row_waiting_for_sign_off_and_a_proposal_name_their_key():
    text = "\n".join(plain(rows.build_cockpit(scene(), 100)))
    assert "⏎ sign off" in text and "⏎ accept" in text
    lines = rows.build_cockpit(scene(), 100)
    keys = {s.text.strip(): s.style for line in lines for s in line.segs if s.action == "take"}
    assert {keys["⏎ accept"], keys["⏎ sign off"], keys["⏎ keep both"]} == {"bold #c77dff"}  # each, your move


def test_a_selected_proposal_opens_to_show_what_accepting_it_agrees_to():
    m = scene()
    docs = m.tasks["docs"]
    docs.scope, docs.needs = ["models/**", "README.md"], ["ids", "schema"]  # schema is done: it waits on ids
    row = next(line for line in rows.build_cockpit(m, 100) if line.row == "docs")
    assert "10 files" in row.plain() and "⏎ accept" in row.plain()  # nine tracked, and one still to make
    m.selected = "docs"
    text = "\n".join(plain(rows.build_cockpit(m, 100)))
    assert "files  models/**, README.md" in text and "waits  users return ids  " in text
    assert all(k in text for k in ("⏎ accept", "d drop", "e edit", "i details")) and "t tell" not in text
    assert "no check" not in text  # it has one; a proposal with none says so
    docs.checks = 0
    assert "no check yet: nothing can prove it done" in "\n".join(plain(rows.build_cockpit(m, 100)))
    docs.check = "pytest -q tests/test_docs.py"  # its words, once the plan's reader gives them
    assert "check  pytest -q tests/test_docs.py" in "\n".join(plain(rows.build_cockpit(m, 100)))
    keys = next(line for line in rows.build_cockpit(m, 100) if "d drop" in line.plain())
    assert [s.action for s in keys.segs if s.action] == ["take", "drop", "edit", "details"]
    assert all(line.width() <= 60 for line in rows.build_cockpit(m, 60))


def test_a_task_that_waits_says_for_whom_and_a_finished_one_says_what_it_changed():
    text = "\n".join(plain(rows.build_cockpit(scene(), 100)))
    assert "← agent 1, agent 2" in text and "3 files" in text
    m = scene()
    m.tasks["ids"].agent = ""  # nobody on it yet: it is named by what it is, never by its id
    assert "← users return ids, agent 2" in "\n".join(plain(rows.build_cockpit(m, 100)))


def test_a_task_that_changed_a_file_outside_its_scope_says_so():
    m = scene()
    m.tasks["schema"].scope = ["db/schema.py"]
    assert "OUTSIDE" in "\n".join(plain(rows.build_cockpit(m, 100)))


def test_the_cockpit_stays_light_at_80_columns_with_one_agent_open():
    tokens = " ".join(plain(rows.build_cockpit(scene(), 80))).split()
    words = sum(1 for t in tokens if any(c.isalnum() for c in t))
    assert words <= 110, words


def test_when_every_task_is_proven_the_rows_say_so_and_what_comes_next():
    m = scene()
    m.questions = []
    for t in m.tasks.values():
        t.state = "done"
    said = plain(rows.build_cockpit(m, 80))[-1].strip()
    assert said == "Every task is proven. Next: :ask, or tell Claude Code."
    m.source = "replay"  # nothing comes next in a recording
    assert plain(rows.build_cockpit(m, 80))[-1].strip() == "Every task is proven."
    m.tasks["ids"].overruled = True  # done over its check is not proven
    assert "proven." not in plain(rows.build_cockpit(m, 80))[-1]


def test_finished_tasks_the_rows_left_out_are_counted():
    m = scene()
    m.folded_done = 7
    assert "7 more proven" in "\n".join(plain(rows.build_cockpit(m, 80)))


def test_the_tell_box_shows_under_the_selected_agent_while_it_is_open():
    text = "\n".join(plain(rows.build_cockpit(scene(), 100, tell="keep ids as strings")))
    assert "tell agent 1: keep ids as strings▌" in text


def test_the_tell_box_under_a_task_nobody_is_on_yet_says_its_agent_reads_it_when_it_starts():
    m = scene()
    for sel, whom in (("tests", "its agent"), ("docs", "its agent")):  # waiting, and proposed
        m.selected = sel
        text = "\n".join(plain(rows.build_cockpit(m, 120, tell="use tabs")))
        assert f"tell {whom}: use tabs▌" in text and f"{whom} reads this when it starts" in text
    m.tasks["tests"].state, m.tasks["tests"].agent = "came back", "3"  # it keeps its number
    m.selected = "tests"
    assert "agent 3 reads this when it starts" in "\n".join(plain(rows.build_cockpit(m, 120, tell="x")))
    m.selected = "ids"  # running, and hooked: it hears it with its next write, so no more is said
    assert "reads this" not in "\n".join(plain(rows.build_cockpit(m, 120, tell="x")))


def test_a_long_line_being_told_shows_its_end_where_you_type_and_fits_the_row():
    m = scene()
    long = "keep the ids as strings everywhere, the API returns them quoted and the tests expect that too"
    for width in (60, 80):
        [line] = [line for line in rows.build_cockpit(m, width, tell=long) if "tell agent 1:" in line.plain()]
        said = line.plain().rstrip()
        assert line.width() <= width and said.endswith("the tests expect that too▌") and "…" in said


def test_files_outside_the_scope_are_flagged_and_a_note_that_cannot_be_heard_says_when_it_is_read():
    m = scene()
    m.tasks["ids"].outside = ["db/schema.py"]
    assert "1 OUTSIDE" in "\n".join(plain(rows.build_cockpit(m, 120)))
    m.tasks["ids"].told = [("keep ids as strings", 90.0, 0.0)]
    assert "sending…" in "\n".join(plain(rows.build_cockpit(m, 120)))
    m.tasks["ids"].hears = False
    assert "it reads this when it next starts" in "\n".join(plain(rows.build_cockpit(m, 120)))


def test_a_note_told_to_an_agent_shows_once_in_its_open_row_with_whether_it_was_heard():
    from graphene_map.cockpit.model import Ev

    m = scene()
    ids = m.tasks["ids"]
    ids.told = [("keep ids as strings", 97.0, 98.0)]
    ids.events.append(Ev(97.0, "you", text="“keep ids as strings”"))  # as the plan's reader adds it
    shown = plain(rows.build_cockpit(m, 120))
    told = [line for line in shown if "keep ids as strings" in line]
    assert len(told) == 1 and "heard 2s ago" in told[0]
    assert any("read tests/util.py" in line for line in shown)  # its own moves keep their place


def test_a_leaf_that_came_back_shows_what_it_offers_as_keys():
    m = scene()
    m.selected = "migrate"
    m.tasks["migrate"].state = "came back"
    m.tasks["migrate"].offers = {"w": ["node", "widen", "migrate"], "b": ["node", "sibling", "migrate"]}
    text = "\n".join(plain(rows.build_cockpit(m, 120)))
    assert "w widen" in text and "b a sibling" in text and "n wait on it" not in text
    m.tasks["migrate"].state = "review"  # x on a task that waits for sign-off reopens it
    assert "x reopen" in "\n".join(plain(rows.build_cockpit(m, 120)))
    m.tasks["migrate"].state = "came back"
    line = next(line for line in rows.build_cockpit(m, 120) if "b a sibling" in line.plain())
    assert "offer:b" in [s.action for s in line.segs]


def test_a_plan_with_nothing_in_it_says_what_to_do_next_in_lines_that_fit_80_columns_and_counts_nothing():
    m = Model("no goal yet")
    m.executor = "claude"
    lines = plain(rows.build_cockpit(m, 80))
    text = "\n".join(lines)
    assert "Nothing is planned yet." in text and "In Claude Code, say what you want" in text
    assert ":ask what you want" in text and "graphene demo" in text and "…" not in text
    assert all(len(line) <= 79 for line in lines) and "graphene init" not in text
    m.executor = ""  # graphene init chose no one to run the tasks: that comes first
    assert "graphene init, in a terminal of your own" in plain(rows.build_cockpit(m, 80))[2]
    assert all(len(line) <= 79 and "…" not in line for line in plain(rows.build_cockpit(m, 80)))
    head = plain(rows.build_head(m, 80))
    assert len(head) == 2 and "need you" not in "\n".join(head)  # the invitation and the rule, no zeros
    m.source = "replay"  # a replay that has nothing yet only says so
    said = [line.strip() for line in plain(rows.build_cockpit(m, 80)) if line.strip()]
    assert said == ["Nothing is planned yet."]


def test_a_running_agent_that_is_not_selected_shows_its_last_move_in_one_dim_line():
    m = scene()
    m.selected = "docs"
    text = "\n".join(plain(rows.build_cockpit(m, 100)))
    assert "┊ edit models/m0.py" in text  # agent 1's last event, under its row
    m.selected = "ids"  # selected, it opens into three lines and the verbs instead
    opened = plain(rows.build_cockpit(m, 100))
    assert "┊ edit models/m0.py" in "\n".join(opened)
    assert sum("edit models/m0.py" in line for line in opened) == 1 and "t tell" in opened[-3]  # said once


def test_a_row_shows_the_whole_title_where_it_fits_and_cuts_it_with_an_ellipsis_where_it_does_not():
    m = scene()
    m.tasks["tests"].full = "The tests for ids: each endpoint returns the id it was given"
    m.tasks["tests"].title = "tests for ids"  # the plan's reader keeps five words for the graph's boxes
    m.tasks["docs"].full = "Write the docs for the ids endpoint, with an example request and its answer"
    wide = "\n".join(plain(rows.build_cockpit(m, 140)))
    assert "tests for ids " in wide and "each endpoint" not in wide  # what follows the colon is left out
    assert "Write the docs for the ids endpoint, with an example request and its answer" in wide
    narrow = next(line for line in rows.build_cockpit(m, 80) if line.row == "docs").plain()
    assert "Write the docs for" in narrow and "…" in narrow and len(narrow) <= 80


def test_a_narrow_banner_keeps_what_it_is_and_where_it_is():
    m = scene()
    m.banner = "replay · as it ran, live · 2026-10-09 · 120 of 138"
    wide = plain(rows.build_head(m, 120))[0]
    narrow = plain(rows.build_head(m, 60))[0]
    assert "as it ran, live · 2026-10-09" in wide
    assert narrow.rstrip().endswith("replay · 120 of 138") and len(narrow) <= 60


def test_a_long_reason_a_leaf_came_back_with_is_cut_on_its_row_and_whole_when_the_row_is_open():
    m = scene()
    note = "I need README.md and tests/test_api.py, but my scope covers only src/ and the gate stopped both"
    back = Task("back", "retry the migration", "came back", agent="3", note=note)
    m.tasks["back"] = back
    for width in (60, 80, 120):
        lines = rows.build_cockpit(m, width)
        assert all(line.width() <= width for line in lines)
        row = next(line for line in lines if line.row == "back")
        assert "retry the" in row.plain() and "…" in row.plain() and "⏎ try again" in row.plain()
    m.selected = "back"
    text = " ".join(line.plain() for line in rows.build_cockpit(m, 80))
    assert "gate stopped both" in " ".join(text.replace("┊", " ").split())
    row = next(line for line in rows.build_cockpit(m, 80) if line.row == "back")
    assert "I need" not in row.plain() and "⏎ try again" in row.plain()  # said once, under it, not beside
    assert row.width() == 80 and "retry the migration" in row.plain()
    assert text.count("I need README.md") == 1


def test_a_title_with_wide_characters_is_measured_in_cells_so_no_row_is_wider_than_the_screen():
    from rich.cells import cell_len

    m = scene()
    m.tasks["ids"].title = "ユーザーのIDを返す ✅ 日本語のタスク"
    m.tasks["migrate"].title = "emoji 🎉🎉🎉 in a title"
    for width in (60, 80, 120):
        lines = rows.build_cockpit(m, width)
        assert all(cell_len(line.plain()) <= width for line in lines)  # counted by the terminal, not by len
        assert len({cell_len(line.plain()) for line in lines if line.row in ("ids", "migrate", "tests")}) == 1
