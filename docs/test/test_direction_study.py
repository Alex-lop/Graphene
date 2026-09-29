"""The direction study's harness: both arms read the state its answer key describes, the wrapper
refuses what an arm does not allow, and the table scores a run by the key."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import direction_study as S  # noqa: E402

from graphene_map import direction as D  # noqa: E402
from graphene_map.store import Store  # noqa: E402


@pytest.fixture(autouse=True)
def not_an_agent(monkeypatch):
    for name in (*S.UNMARK, "GRAPHENE_AS"):
        monkeypatch.delenv(name, raising=False)


def test_the_direction_arm_reads_the_state_the_key_describes(tmp_path):
    S.fixture(tmp_path / "d", "direction")
    repo = tmp_path / "d" / "repo"
    with Store.open(repo) as store:
        st = D.status(store, D.read(repo))
    assert D.head(st, "repo").startswith("you: 4 · 3 running · next: email")  # 4 waiting, 3 running, 1 next
    words = {w["short"]: (w["word"], w["node"]) for w in st["sessions"]}
    assert words == {
        "5a1e0c3b": ("running", "plan"),
        "b7c24d1e": ("your turn", "billing"),
        "c3d4e5f6": ("running", "billing"),
        "a1b2c3d4": ("running", "billing"),
        "d9e8f7a6": ("idle", None),
    }
    assert (st["plan"]["node"], st["plan"]["you"], st["plan"]["running"]) == ("pdf", 2, 1)  # render, q-paper
    assert [n["id"] for n in st["nodes"] if n["word"] == "proposed"] == ["mobile"]


def test_the_morning_arm_names_every_answer_and_the_brief_keeps_its_contract():
    for items in S.KEY.values():
        for item in items:
            assert any(i in S.MORNING for i in item), item
    brief = S.MORNING.split("## The brief", 1)[1].split("---", 1)[0].strip().splitlines()
    assert len([line for line in brief if line.strip()]) <= 20  # the brief's contract: twenty lines at most


def test_the_wrapper_refuses_another_arms_command_and_the_table_scores_by_the_key(tmp_path, capsys):
    run = tmp_path / "m"
    S.fixture(run, "morning")
    S.run(run, ["graphene", "direction"])
    assert "refused in this arm" in capsys.readouterr().out
    S.run(run, ["head", "-n", "20", "morning.md"])
    assert "## The brief" in capsys.readouterr().out
    S.answer(run, "waiting", "render, q-paper, mobile, b7c24d1e")
    S.answer(run, "running", "template, c3d4e5f6")
    S.answer(run, "next", "email, download")
    got = S.score(run)
    assert (got["acts"], got["right"], got["false"], got["answered"]) == (2, 7, 1, 3)  # a1b2c3d4 missed
    log = [json.loads(line) for line in (run / "runlog.jsonl").read_text().splitlines()]
    assert log[0]["allowed"] is False and log[0]["words"] == 0 and log[1]["words"] > 50
    assert got["seconds"] == round(S.K * got["typed"] + S.M * 2 + got["words"] / S.WPM * 60, 1)
    assert "| m | morning |" in S.table([run])


def test_only_reads_of_the_arms_own_material_pass_the_wrapper(tmp_path):
    """Review, 29 September: `graphene direction accept` ran in the person's seat and changed the
    fixture, and `cat <the other arm's file> morning.md` passed because only the last word was read."""
    (tmp_path / "morning.md").write_text("x")
    (tmp_path / "repo").mkdir()
    reads = ("direction", "direction --width 80", "plan --view tree", "board", "watch --once")
    for said in reads:
        assert S._allowed(tmp_path, "direction", ["graphene", *said.split()]), said
    writes = ("direction accept mobile", "direction edit", "watch", "board take q", "plan accept")
    for said in writes:
        assert not S._allowed(tmp_path, "direction", ["graphene", *said.split()]), said
    assert not S._allowed(tmp_path, "direction", ["cat", "morning.md"])
    assert S._allowed(tmp_path, "morning", ["head", "-n", "20", "morning.md"])
    assert S._allowed(tmp_path, "morning", ["grep", "-n", "waits", "morning.md"])
    for argv in (["cat", "repo/.graphene/direction.txt", "morning.md"], ["cat", "repo", "morning.md"],
                 ["sed", "1,5p", "morning.md"], ["graphene", "direction"]):  # fmt: skip
        assert not S._allowed(tmp_path, "morning", argv), argv
    assert '[["render"], ["q-paper"]' not in Path(S.__file__).read_text()  # the key is not in the file named


def test_the_direction_print_alone_names_every_waiting_and_running_item_inside_80_columns(tmp_path, capsys):
    """Study of 29 September, after the fact: every direction stand-in read "you 4" and found two of
    the four ids, then ran `graphene plan` and `graphene board` for the rest. The print now names each
    item that waits on the person, and each piece of running work once, by the id they act on; at 80
    columns and at the wrapper's default 100 no line is wider and no id is cut."""
    run = tmp_path / "d"
    S.fixture(run, "direction")
    for width in ("80", "100"):
        S.run(run, ["graphene", "direction", "--width", width])
        said = capsys.readouterr().out
        lines = said.splitlines()
        assert all(len(line) <= int(width) for line in lines), width
        words = {w.strip("`·,():") for w in said.split()}
        for question in ("waiting", "running"):
            for item in S.KEY[question]:
                assert any(i in words for i in item), (width, question, item)
        assert "next: email" in said
        rows = [line.split() for line in lines]
        # next: the leaf it names has a row of its own, in the row grammar: title, id, state word
        assert any(r[1:4] == ["next:", "email", "ready"] for r in rows), said
        assert "attach the PDF to the monthly email" in " ".join(said.split()), said  # whole, if wrapped
        # a running row says which id is the work and which holds it
        held = [" ".join(r) for r in rows if "template" in r and "running" in r]
        assert held and "held by session 5a1e0c3b" in held[0], said
