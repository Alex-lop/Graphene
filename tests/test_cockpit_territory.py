"""The cockpit's territory: which folders each task may write, computed with Graphene's own scope rule."""

from graphene_map.cockpit import territory as T

FILES = [f"models/m{i}.py" for i in range(6)]
FILES += [f"api/a{i}.py" for i in range(4)] + ["docs/a.md", "docs/b.md"]


def running(scope, **more):
    return {"state": "running", "scope": scope, **more}


def test_a_scope_claims_the_files_it_covers_and_the_summary_counts_them():
    groups, summary = T.compute(FILES, {"ids": running(["models/**"])})
    assert summary["files"] == 12 and summary["may"] == 6 and summary["percent"] == 50
    by_name = {g.name: g for g in groups}
    assert by_name["models/"].owners["ids"] == 6
    assert not by_name["api/"].owners


def test_a_scope_that_matches_nothing_tracked_is_a_place_for_new_files():
    groups, summary = T.compute(FILES, {"ids": running(["models/**", "extra/tests/**"])})
    assert summary["new"] == 1
    assert any(g.new and g.name == "extra/tests/ (new)" for g in groups)


def test_a_finished_task_claims_nothing_and_what_it_changed_outside_its_scope_is_counted():
    tasks = {"api": {"state": "done", "scope": ["api/**"], "changed": ["api/a0.py", "docs/a.md"]}}
    groups, summary = T.compute(FILES, tasks, lens="changed")
    assert summary["may"] == 0 and summary["outside"] == 1
    assert {g.name: g.outside for g in groups}["docs/"] == 1


def test_a_stopped_write_is_counted_at_the_folder_it_was_stopped_at():
    groups, _ = T.compute(FILES, {"ids": running(["models/**"], stopped=["docs/c.md"])}, lens="live")
    docs = next(g for g in groups if g.name == "docs/")
    assert docs.stopped == 1 and docs.stopped_by == ["ids"]


def test_protected_folders_are_flagged():
    groups, summary = T.compute(FILES, {}, protected=["docs/**"])
    assert summary["protected"] == ["docs/"]


def test_a_bar_is_as_wide_as_asked_and_shares_a_folder_between_tasks():
    low, high = [f"models/m{i}.py" for i in range(3)], [f"models/m{i}.py" for i in range(3, 6)]
    groups, _ = T.compute(FILES, {"ids": running(low), "api": running(high)})
    models = next(g for g in groups if g.name == "models/")
    runs = T.bar(models, 20, "plan", lambda tid: tid)
    assert sum(len(text) for text, _ in runs) == 20
    assert {style for _, style in runs} >= {"ids", "api"}
