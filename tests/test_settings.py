# ruff: noqa: F811  (pytest fixtures imported from test_plan are named again as arguments)
"""The settings a person states once: shown as text, edited as text, refused by line number, written
all or none, and the person's alone to change."""

import pytest
from test_plan import ALEX, BOT, repo, store  # noqa: F401  (fixtures)

from graphene_map import settings as S
from graphene_map.plan import Refused

TEXT = """\
# mine
protected: vendor/**, legacy/
protected: .env
readonly: docs/**
never: add a dependency
never: rewrite the # of retries
size: finer
"""


def test_nothing_set_reads_as_empty_and_auto(store):
    assert (S.protected(store), S.readonly(store), S.never(store), S.size(store)) == ([], [], [], "auto")
    assert S.conditions_for_planner(store) == ""
    assert S.render(store).endswith("size: auto\nboard: auto\n") and S.board(store) == "auto"


def test_a_person_writes_them_and_they_read_back(store):
    S.apply(store, TEXT, ALEX)
    assert S.protected(store) == ["vendor/**", "legacy/", ".env"]
    assert S.readonly(store) == ["docs/**"]
    assert S.never(store) == ["add a dependency", "rewrite the # of retries"]
    assert S.size(store) == "finer"
    said = S.conditions_for_planner(store)
    assert "vendor/**" in said and "docs/**" in said and "add a dependency" in said
    assert "finer" not in said  # the size is told once, by the sizing sentence (ask.prompt_for)
    again = S.render(store)
    S.apply(store, again, ALEX)
    assert S.render(store) == again
    assert [r["detail"]["changed"].keys() for r in store.node_log("*", ("settings",))] == [
        {"protected", "readonly", "never", "size"}
    ]


def test_a_setting_left_out_is_cleared(store):
    S.apply(store, TEXT, ALEX)
    S.apply(store, "readonly: docs/**\n", ALEX)
    assert (S.protected(store), S.never(store), S.size(store)) == ([], [], "auto")


@pytest.mark.parametrize(
    "bad, no, words",
    [
        ("size: huge", 2, "auto, finer or coarser"),
        ("colour: blue", 2, "not a setting"),
        ("protected: /etc/**", 2, "not inside the repo"),
        ("protected: a, , b", 2, "none empty"),
        ("readonly: !docs", 2, "'!'"),
        ("never:", 2, "never propose"),
        ("protected: .env  # secrets", 2, "a note goes on a line of its own"),
        ("size: auto\nsize: finer", 3, "line 2"),
        ("board: off", 2, "board is auto or on"),
        ("board: auto\nboard: on", 3, "line 2"),
    ],
)
def test_a_bad_line_is_refused_by_its_number_and_nothing_is_written(store, bad, no, words):
    S.apply(store, TEXT, ALEX)
    before = S.render(store)
    with pytest.raises(Refused) as got:
        S.apply(store, f"protected: other/**\n{bad}\n", ALEX)
    assert str(got.value).startswith(f"line {no}: ") and words in str(got.value)
    assert S.render(store) == before


def test_only_the_person_changes_them(store):
    with pytest.raises(Refused, match="person's to do"):
        S.apply(store, "size: coarser\n", BOT)
    assert S.size(store) == "auto"


def test_a_failure_inside_the_claim_writes_nothing(store, monkeypatch):
    S.apply(store, TEXT, ALEX)
    before = S.render(store)
    monkeypatch.setattr(store, "log_node", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk")))
    with pytest.raises(RuntimeError):
        S.apply(store, "size: coarser\n", ALEX)
    assert S.render(store) == before


def test_the_board_setting_is_auto_unset_and_on_once_said(store):
    assert S.board(store) == "auto"  # study 4's rule: the board did not cost the outline's or less
    S.apply(store, "board: on\n", ALEX)
    assert S.board(store) == "on" and "board: on\n" in S.render(store)
    assert store.node_log("*", ("settings",))[-1]["detail"]["changed"] == {"board": ["auto", "on"]}
    S.apply(store, "size: auto\n", ALEX)  # left out, it is cleared: auto, as before it was said
    assert S.board(store) == "auto"
