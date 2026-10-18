"""The cockpit screen as lines: a frame is a function of the model, so it is tested without a terminal."""

from cockpit_scene import scene

from graphene_map.cockpit import rows


def plain(lines) -> list[str]:
    return [line.plain() for line in lines]


def test_every_line_fits_the_width_asked():
    for width in (60, 80, 120):
        assert all(line.width() <= width for line in rows.build_cockpit(scene(), width))


def test_the_header_says_what_waits_for_the_person_what_runs_and_what_is_proven():
    top = plain(rows.build_cockpit(scene(), 80))
    assert "users come back with their ids" in top[0] and "your plan" in top[0]
    assert top[1].split() == ["2", "need", "you", "1", "running", "1/5", "proven"]


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
    assert "t tell" in text and "w give it db/" in text and "x pull back" in text
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
