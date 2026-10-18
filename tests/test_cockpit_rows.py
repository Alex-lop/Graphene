"""The cockpit screen as lines: a frame is a function of the model, so it is tested without a terminal."""

from cockpit_scene import scene

from graphene_map.cockpit import rows
from graphene_map.cockpit.model import Model, Task


def plain(lines) -> list[str]:
    return [line.plain() for line in lines]


def test_every_line_fits_the_width_asked():
    for width in (60, 80, 120):
        assert all(line.width() <= width for line in rows.build_cockpit(scene(), width))


def test_the_header_says_what_waits_for_the_person_what_runs_and_what_is_proven():
    top = plain(rows.build_cockpit(scene(), 80))
    assert "users come back with their ids" in top[0] and "your plan" in top[0]
    assert top[1].split() == ["3", "need", "you", "1", "running", "1/5", "proven"]  # a proposal counts


def test_the_question_comes_first_and_the_default_and_the_options_are_buttons():
    lines = rows.build_cockpit(scene(), 80)
    question = next(line for line in lines if line.row == "q")
    assert plain([question])[0].lstrip().startswith("?") and "Keep old ids working?" in question.plain()
    actions = [s.action for s in question.segs if s.action]
    assert actions == ["take", "pick:1"]


def test_a_running_row_has_its_agent_and_its_numbers_and_the_selected_one_opens():
    m = scene()
    text = "\n".join(plain(rows.build_cockpit(m, 100)))
    assert "fox" in text and "✎2/9" in text and "✓1/3" in text and "!1" in text
    assert "t tell" in text and "w give it db/ids_2.py" in text and "x pull back" in text
    m.selected = "docs"  # a proposed row does not open with an agent's verbs
    assert "t tell" not in "\n".join(plain(rows.build_cockpit(m, 100)))


def test_a_row_waiting_for_sign_off_and_a_proposal_name_their_key():
    text = "\n".join(plain(rows.build_cockpit(scene(), 100)))
    assert "⏎ sign off" in text and "⏎ accept" in text


def test_a_task_that_waits_says_for_whom_and_a_finished_one_says_what_it_changed():
    text = "\n".join(plain(rows.build_cockpit(scene(), 100)))
    assert "← fox oak" in text and "3 files" in text


def test_a_task_that_changed_a_file_outside_its_scope_says_so():
    m = scene()
    m.tasks["schema"].scope = ["db/schema.py"]
    assert "OUTSIDE" in "\n".join(plain(rows.build_cockpit(m, 100)))


def test_the_cockpit_stays_light_at_80_columns_with_one_agent_open():
    tokens = " ".join(plain(rows.build_cockpit(scene(), 80))).split()
    words = sum(1 for t in tokens if any(c.isalnum() for c in t))
    assert words <= 110, words


def test_finished_tasks_the_rows_left_out_are_counted():
    m = scene()
    m.folded_done = 7
    assert "7 more proven" in "\n".join(plain(rows.build_cockpit(m, 80)))


def test_the_tell_box_shows_under_the_selected_agent_while_it_is_open():
    text = "\n".join(plain(rows.build_cockpit(scene(), 100, tell="keep ids as strings")))
    assert "tell fox: keep ids as strings▌" in text


def test_files_outside_the_scope_are_flagged_and_a_note_that_cannot_be_heard_says_when_it_is_read():
    m = scene()
    m.tasks["ids"].outside = ["db/schema.py"]
    assert "1 OUTSIDE" in "\n".join(plain(rows.build_cockpit(m, 120)))
    m.tasks["ids"].told = [("keep ids as strings", 90.0, 0.0)]
    assert "sending…" in "\n".join(plain(rows.build_cockpit(m, 120)))
    m.tasks["ids"].hears = False
    assert "it reads this when it next starts" in "\n".join(plain(rows.build_cockpit(m, 120)))


def test_a_leaf_that_came_back_shows_what_it_offers_as_keys():
    m = scene()
    m.selected = "migrate"
    m.tasks["migrate"].state = "came back"
    m.tasks["migrate"].offers = {"w": ["node", "widen", "migrate"], "b": ["node", "sibling", "migrate"]}
    text = "\n".join(plain(rows.build_cockpit(m, 120)))
    assert "w widen it" in text and "b a sibling" in text and "n wait on it" not in text
    line = next(line for line in rows.build_cockpit(m, 120) if "b a sibling" in line.plain())
    assert "offer:b" in [s.action for s in line.segs]


def test_a_plan_with_nothing_in_it_says_what_to_do_in_three_short_lines():
    m = Model("no goal yet")
    lines = plain(rows.build_cockpit(m, 80))
    text = "\n".join(lines)
    assert "Nothing is planned yet." in text and "Or type :ask" in text
    assert all(len(line) <= 80 for line in lines)


def test_a_running_agent_that_is_not_selected_shows_its_last_move_in_one_dim_line():
    m = scene()
    m.selected = "docs"
    text = "\n".join(plain(rows.build_cockpit(m, 100)))
    assert "┊ edit models/m0.py" in text  # fox's last event, under its row
    m.selected = "ids"  # selected, it opens into three lines and the verbs instead
    assert "┊ edit models/m0.py" in "\n".join(plain(rows.build_cockpit(m, 100)))


def test_a_narrow_banner_keeps_what_it_is_and_where_it_is():
    m = scene()
    m.banner = "replay · as it ran, live · 2026-10-09 · 120 of 138"
    wide = plain(rows.build_cockpit(m, 120))[0]
    narrow = plain(rows.build_cockpit(m, 60))[0]
    assert "as it ran, live · 2026-10-09" in wide
    assert narrow.rstrip().endswith("replay · 120 of 138") and len(narrow) <= 60


def test_a_long_reason_a_leaf_came_back_with_is_cut_on_its_row_and_whole_when_the_row_is_open():
    m = scene()
    note = "I need README.md and tests/test_api.py, but my scope covers only src/ and the gate stopped both"
    back = Task("back", "retry the migration", "came back", agent="wren", note=note)
    m.tasks["back"] = back
    for width in (60, 80, 120):
        lines = rows.build_cockpit(m, width)
        assert all(line.width() <= width for line in lines)
        row = next(line for line in lines if line.row == "back")
        assert "retry the" in row.plain() and "…" in row.plain() and "⏎ try again" in row.plain()
    m.selected = "back"
    text = " ".join(line.plain() for line in rows.build_cockpit(m, 80))
    assert "gate stopped both" in " ".join(text.replace("┊", " ").split())


def test_a_title_with_wide_characters_is_measured_in_cells_so_no_row_is_wider_than_the_screen():
    from rich.cells import cell_len

    m = scene()
    m.tasks["ids"].title = "ユーザーのIDを返す ✅ 日本語のタスク"
    m.tasks["migrate"].title = "emoji 🎉🎉🎉 in a title"
    for width in (60, 80, 120):
        lines = rows.build_cockpit(m, width)
        assert all(cell_len(line.plain()) <= width for line in lines)  # counted by the terminal, not by len
        assert len({cell_len(line.plain()) for line in lines if line.row in ("ids", "migrate", "tests")}) == 1
