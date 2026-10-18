"""The territory screen as lines."""

from cockpit_scene import scene

from graphene_map.cockpit import territory_view as TV


def plain(lines) -> str:
    return "\n".join(line.plain() for line in lines)


def test_the_header_says_how_much_of_the_repository_the_plan_may_touch():
    lines, groups = TV.build_territory(scene(), 100)
    assert "may be touched" in plain(lines) and groups
    assert all(line.width() <= 100 for line in lines)


def test_the_selected_tasks_folders_are_its_own_and_every_folder_row_is_a_button():
    m = scene()
    lines, groups = TV.build_territory(m, 100)
    assert any(g.owners.get("ids") for g in groups)
    folder_rows = [line for line in lines if any(s.action.startswith("group:") for s in line.segs)]
    assert len(folder_rows) == len(groups)


def test_the_live_lens_shows_a_stopped_write_and_offers_to_allow_it():
    m = scene()
    m.lens = "live"
    text = plain(TV.build_territory(m, 100)[0])
    assert "stopped" in text and "allow fox" in text


def test_the_changed_lens_names_what_a_finished_task_changed_and_flags_what_was_outside_its_scope():
    m = scene()
    m.lens = "changed"
    m.tasks["schema"].changed = ["db/d0.py", "db/d1.py", "models/m0.py"]
    m.tasks["schema"].scope = ["db/**"]
    text = plain(TV.build_territory(m, 100)[0])
    assert "schema 2" in text and "1 OUTSIDE" in text


def test_a_task_that_waits_for_files_another_owns_is_told_why_it_is_not_parallel():
    m = scene()
    m.tasks["tests"].scope = ["models/**"]  # it wants what fox owns
    assert "waits for fox: it owns the same files" in plain(TV.build_territory(m, 100)[0])
