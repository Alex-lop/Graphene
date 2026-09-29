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
