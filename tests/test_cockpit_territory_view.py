"""The territory screen as lines."""

from cockpit_scene import scene

from graphene_map.cockpit import territory_view as TV


def plain(lines) -> str:
    return "\n".join(line.plain() for line in lines)


def test_the_header_says_how_much_of_the_repository_the_plan_may_touch():
    lines, groups = TV.build_territory(scene(), 100)
    assert "may be touched" in plain(lines) and groups
    assert all(line.width() <= 100 for line in lines)


def test_each_lens_says_what_is_true_in_it_on_the_top_line():
    m = scene()
    assert plain(TV.build_territory(m, 100)[0]).startswith(" MAP 9 of 12 files may be touched (75%)")
    m.lens = "live"
    assert plain(TV.build_territory(m, 100)[0]).startswith(" MAP 2 files being written · 1 write stopped")
    m.lens = "changed"
    m.tasks["schema"].changed = ["db/d0.py", "db/d1.py", "models/m0.py"]
    m.tasks["schema"].scope = ["db/**"]
    top = plain(TV.build_territory(m, 100)[0]).splitlines()[0]
    assert top.startswith(" MAP 3 files changed in 2 folders · 1 outside its scope")
    m.tasks["schema"].changed = []  # nothing changed yet: one calm line, not a row of zeros
    assert plain(TV.build_territory(m, 100)[0]).startswith(" MAP no files changed yet")


def test_the_selected_tasks_folders_are_its_own_and_every_folder_row_is_a_button():
    m = scene()
    lines, groups = TV.build_territory(m, 100)
    assert any(g.owners.get("ids") for g in groups)
    folder_rows = [line for line in lines if any(s.action.startswith("group:") for s in line.segs)]
    assert len(folder_rows) == len(groups)


def test_at_80_columns_the_live_lens_says_what_happens_first_and_w_widens_a_stopped_write():
    m = scene()
    m.lens = "live"
    lines = TV.build_territory(m, 80)[0]
    models = next(line.plain() for line in lines if "models/" in line.plain())
    assert models.index("● 2 now") < models.index("agent 1 (9)")  # the marks before the owners
    db = next(line for line in lines if "db/" in line.plain())
    assert "!1 stopped  w widen" in db.plain() and any(s.action == "allow" for s in db.segs)
    assert "←/→ agent 1 · users return ids" in plain(lines)  # what w acts on: the selected task
    assert "a: allow" not in plain(lines) and "p paint" not in plain(lines)  # the key bar says the keys
    assert all(line.width() <= 80 for line in lines)
    m.selected = "migrate"  # someone else's stopped write: whose, and a click selects it
    db = next(line for line in TV.build_territory(m, 80)[0] if "db/" in line.plain())
    assert "by agent 1" in db.plain() and "w widen" not in db.plain()
    assert any(s.action == "select:ids" for s in db.segs)


def test_at_80_columns_a_protected_folder_keeps_its_flag_when_a_file_is_written_and_one_stopped_there():
    m = scene()
    m.lens = "live"
    m.files = ["README.md", "pyproject.toml", "setup.cfg", *m.files]  # (root): written to, and protected
    m.protected = ["pyproject.toml", "setup.cfg"]
    m.tasks["ids"].scope = ["models/**", "*.md"]
    m.tasks["ids"].touched = {"README.md": 90.0}
    m.tasks["migrate"].state = "running"
    m.tasks["migrate"].stopped = [("setup.cfg", 97.0)]
    for selected in ("ids", "migrate"):  # someone else's stopped write, then the selected task's own
        m.selected = selected
        root = next(line for line in TV.build_territory(m, 80)[0] if line.plain()[2:].startswith("(root)"))
        assert "● 1 now  !1 stopped" in root.plain() and root.plain().rstrip().endswith("PROTECTED")
        assert root.width() <= 80


def test_an_owner_is_named_by_its_agent_or_else_its_title_never_by_its_id():
    m = scene()
    m.tasks["docs"].scope = ["db/**"]  # a proposal: no agent yet
    text = plain(TV.build_territory(m, 100)[0])
    assert "agent 1 (9)" in text and "docs for ids (3)" in text and "docs (3)" not in text


def test_the_changed_lens_names_what_a_finished_task_changed_and_flags_what_was_outside_its_scope():
    m = scene()
    m.lens = "changed"
    m.tasks["schema"].changed = ["db/d0.py", "db/d1.py", "models/m0.py"]
    m.tasks["schema"].scope = ["db/**"]
    text = plain(TV.build_territory(m, 100)[0])
    assert "schema (2)" in text and "1 OUTSIDE" in text


def test_a_task_that_waits_for_files_another_owns_is_told_why_it_is_not_parallel():
    m = scene()
    m.tasks["tests"].scope = ["models/**"]  # it wants what agent 1 owns
    assert "waits for agent 1: it owns the same files" in plain(TV.build_territory(m, 100)[0])


def test_at_80_columns_a_long_title_gives_way_in_why_a_task_waits_and_whom_it_waits_for_stays():
    m = scene()
    m.tasks["tests"].scope = ["models/**"]
    m.tasks["tests"].title = "tests for ids, for every endpoint that returns a user, the old ones and the new"
    said = TV.build_territory(m, 80)[0][-1].plain()  # the last line: why it waits
    assert said.startswith(" tests for ids, for every") and len(said) <= 80
    assert said.endswith("… waits for agent 1: it owns the same files")


def test_a_plan_with_no_tasks_is_one_line_on_the_map_not_a_row_of_nobody():
    from graphene_map.cockpit.model import Model

    m = Model("users come back with their ids")
    m.files = scene().files
    lines, groups = TV.build_territory(m, 80)
    assert [line.plain() for line in lines] == [" " + TV.EMPTY] and groups == []
    assert TV.EMPTY.startswith("Nothing is planned yet") and lines[0].width() <= 78
