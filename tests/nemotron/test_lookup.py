"""`graphene board lookup` against the scripted fake: Nano says which open questions a file already
answers; Graphene keeps an answer only when the quoted line is in the file it names, and folds the item
as settled "from the repo", which the person opens again with one key."""

import json
import subprocess

import pytest
from fake_tokenfactory import Fake
from test_board_rows import drive
from typer.testing import CliRunner

from graphene_map import board as B
from graphene_map import plan as P
from graphene_map import plan_text as T
from graphene_map.cli import build
from graphene_map.nemotron import lookup as L
from graphene_map.nemotron import tokenfactory as tf
from graphene_map.store import Store

PLAN = """goal: prices load
question: are prices in cents or in dollars?  [units]
    default: cents, as the reader writes them
    option: dollars, with two decimals
    then: goal prices + Prices are dollars with two decimals.
question: what should an empty feed do?  [empty]
    default: load nothing and exit 0
? prices  [prices]
    read prices
    scope: app.py
    check: python3 -c 'import app'
"""
CENTS = {"id": "units", "choice": "default", "file": "app.py", "line": "return int(price * 100)  # cents"}


def nano(answer) -> dict:
    return {"content": answer if isinstance(answer, str) else json.dumps(answer)}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for name in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "AI_AGENT", "GRAPHENE_AS", "GRAPHENE_SHAPE"):
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / "repo"
    root.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@e.com"], ["config", "user.name", "T"]):
        subprocess.run(["git", "-C", str(root), *args], check=True)
    (root / ".gitignore").write_text(".graphene/\n")
    (root / "app.py").write_text("def to_cents(price):\n    return int(price * 100)  # cents\n")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "start"], check=True)
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def fake(monkeypatch):
    started = []

    def start(replies):
        f = Fake(replies).__enter__()
        for k, v in f.env().items():
            monkeypatch.setenv(k, v)
        tf._listed.cache_clear()
        started.append(f)
        return f

    yield start
    for f in started:
        f.__exit__(None, None, None)
    tf._listed.cache_clear()


def planned(repo):
    with Store.open(repo) as store, store.claim():
        T.apply(store, PLAN, P.Caller("planner:nemotron", False, "s"), None, files=P.tracked(repo))


def person(*args):
    return CliRunner().invoke(build(), list(args), env={"GRAPHENE_AS": "person:alex"})


def test_a_question_the_repo_answers_is_settled_from_it_and_the_rest_stay(repo, fake):
    planned(repo)
    f = fake([nano({"answers": [CENTS, {"id": "empty", "choice": None, "file": None, "line": None}]})])
    said = person("board", "lookup")
    assert said.exit_code == 0, said.output
    assert "settled units from the repo (app.py:2): cents, as the reader writes them" in said.stdout
    assert "from the repo: 1 of 2 open questions settled; the rest stay on the board" in said.stdout
    sent = f.requests[0]["messages"][1]["content"]
    assert "[units] are prices in cents or in dollars?" in sent and "--- app.py" in sent
    with Store.open(repo) as store:
        units = B.get(store, "units")
        assert (units["state"], units["from"]) == ("taken", "app.py:2")
        assert B.get(store, "empty")["state"] == "open"
        assert B.decided(store) == ["are prices in cents or in dollars? → cents, as the reader writes them "
                                    "(from the repo: app.py:2)"]  # fmt: skip
        [bill] = store.node_log("*", ("usage",))
        assert bill["actor"] == L.ACTOR and bill["detail"]["calls"] == 1
    board = person("board").stdout.splitlines()
    assert board[0] == "the board: 1 open, 1 settled (1 from the repo)"
    assert "from the repo: app.py:2" in person("board", "--all").stdout


@pytest.mark.parametrize(
    "answer",
    [
        {**CENTS, "line": "return float(price)  # dollars"},  # a line the file does not have
        {**CENTS, "file": "nowhere.py"},  # a file it was not sent
        {**CENTS, "choice": "option 3"},  # a choice the question does not offer
        {**CENTS, "line": "# cents"},  # too short to prove anything
        {**CENTS, "id": "prices"},  # not an open question
    ],
)
def test_an_answer_that_does_not_hold_settles_nothing(repo, fake, answer):
    planned(repo)
    fake([nano({"answers": [answer]})])
    assert person("board", "lookup").exit_code == 0
    with Store.open(repo) as store:
        assert {it["state"] for it in B.items(store)} == {"open"}


def test_an_option_the_repo_makes_is_picked_with_its_then_lines_and_unpark_opens_it_again(repo, fake):
    planned(repo)
    (repo / "README.md").write_text("Prices are dollars, with two decimals, everywhere in this repo.\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    line = "Prices are dollars, with two decimals"
    fake([nano({"answers": [{"id": "units", "choice": "option 1", "file": "README.md", "line": line}]})])
    assert person("board", "lookup").exit_code == 0
    with Store.open(repo) as store:
        assert (B.get(store, "units")["state"], B.get(store, "units")["option"]) == ("picked", 1)
        assert P.get(store, "prices").goal.endswith("Prices are dollars with two decimals.")
    back = person("board", "unpark", "units")
    assert back.exit_code == 0 and back.stdout.splitlines() == [
        "open units", "  what it changed stays: prices: goal + Prices are dollars with two decimals."
    ]
    with Store.open(repo) as store:
        units = B.get(store, "units")
        assert (units["state"], units["answer"], units.get("from")) == ("open", None, None)
        assert B.decided(store) == []


def test_nothing_is_asked_without_a_key_or_by_an_agent_and_a_reply_not_json_settles_nothing(repo, fake):
    planned(repo)
    no_key = person("board", "lookup")
    assert no_key.exit_code == 1 and "Nano could not be asked" in no_key.output
    agent = CliRunner().invoke(build(), ["board", "lookup"], env={"CLAUDECODE": "1"})
    assert agent.exit_code == 1 and "person's to do" in agent.output
    fake([nano("Sure! units is cents.")])
    said = person("board", "lookup")
    assert said.exit_code == 0 and "every question stays open" in said.stdout
    with Store.open(repo) as store:
        assert {it["state"] for it in B.items(store)} == {"open"}


def test_the_flag_looks_up_once_the_proposal_has_landed(repo, fake, monkeypatch):
    from graphene_map.ask import ask, named

    monkeypatch.setenv("GRAPHENE_SHAPE", "lookup")
    f = fake([{"content": f"```plan\n{PLAN}```"}] * 2 + [nano({"answers": [CENTS]})])  # draft, answer
    said = []
    with Store.open(repo) as store:
        ask(store, repo, "load the prices", named("nemotron"), say=said.append)
        assert B.get(store, "units")["from"] == "app.py:2" and B.get(store, "empty")["state"] == "open"
        assert P.get(store, "prices").state == P.PROPOSED  # the proposal stands
    assert len(f.requests) == 3


def test_on_the_screen_a_repo_answer_says_where_and_p_asks_you_again(repo, fake):
    planned(repo)
    fake([nano({"answers": [CENTS]})])
    assert person("board", "lookup").exit_code == 0
    first, fold, item, back = drive(repo, [[], ["j"], ["z", "o", "j"], ["p"]], (120, 36))
    assert first["at"] == "empty"  # the screen opens on what the repository does not answer
    assert fold["at"] == "fold" and "(from the repo: app.py:2)" in " ".join(fold["detail"].split())
    assert item["at"] == "units" and "p asks you" in item["status"]
    assert "from the repo app.py:2" in " ".join(item["detail"].split())
    assert back["status"].startswith("graphene board unpark units: open units")
    with Store.open(repo) as store:
        assert B.get(store, "units")["state"] == "open"


def test_a_protected_file_is_never_sent_and_an_answer_quoting_it_settles_nothing(repo, fake):
    (repo / "secrets").mkdir()
    (repo / "secrets" / "prices.txt").write_text("prices are in cents, says the vault\n")
    (repo / "prices-link.txt").symlink_to("secrets/prices.txt")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    planned(repo)
    with Store.open(repo) as store:
        from graphene_map import settings as S

        S.apply(store, "protected: secrets/**\n", P.Caller("alex", True))
    vault = "prices are in cents, says"
    quoted = {"id": "units", "choice": "default", "file": "secrets/prices.txt", "line": vault}
    linked = {**quoted, "id": "empty", "file": "prices-link.txt"}
    f = fake([nano({"answers": [quoted, linked]})])
    assert person("board", "lookup").exit_code == 0
    sent = f.requests[0]["messages"][1]["content"]
    assert "--- app.py" in sent and "vault" not in sent
    assert "secrets/" not in sent and "prices-link" not in sent  # nor where a link reaches it
    with Store.open(repo) as store:
        assert {it["state"] for it in B.items(store)} == {"open"}


def test_a_question_with_no_default_is_not_taken_by_a_default_from_the_repo(repo, fake):
    planned(repo)
    with Store.open(repo) as store:
        B.add(store, "question", "which level?", P.Caller("planner:nemotron", False, "s"), item_id="level")
    said = {"id": "level", "choice": "default", "file": "app.py", "line": "return int(price * 100)  # cents"}
    fake([nano({"answers": [said]})])
    assert person("board", "lookup").exit_code == 0
    with Store.open(repo) as store:
        assert B.get(store, "level")["state"] == "open"


def test_an_answer_that_drops_a_node_is_left_for_the_person(repo, fake):
    """Review 2026-09-29 (6): lookup took a default that drops a leaf, which accept and R leave for
    the person's key, and neither unpark nor undo brought the leaf back."""
    planned(repo)
    with Store.open(repo) as store:
        B.add(store, "question", "should prices stay?", P.Caller("planner:nemotron", False, "s"),
              default="no, drop it", then=["drop prices"], item_id="stay")  # fmt: skip
    fake([nano({"answers": [{**CENTS, "id": "stay"}]})])
    assert person("board", "lookup").exit_code == 0
    with Store.open(repo) as store:
        assert B.get(store, "stay")["state"] == "open" and P.get(store, "prices").state == P.PROPOSED


def test_a_form_feed_does_not_move_the_line_it_cites(repo, fake):
    """Review 2026-09-29 (12): lines were numbered by str.splitlines, which also breaks on a form feed,
    so the citation pointed one line past the quoted one."""
    (repo / "app.py").write_text("import os\n\x0c\ndef load():\n    return int(price * 100)  # cents\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    planned(repo)
    fake([nano({"answers": [CENTS]})])
    assert person("board", "lookup").exit_code == 0
    with Store.open(repo) as store:
        assert B.get(store, "units")["from"] == "app.py:4"  # as `grep -n cents app.py` says


@pytest.mark.parametrize("odd", [{"id": ["units"]}, {"file": ["app.py"]}, {"choice": 1}, {"line": {"a": 1}}])
def test_an_answer_of_the_wrong_shape_is_passed_over_not_a_crash(repo, fake, odd):
    """Review 2026-09-29 (13): a list for an id or a file raised TypeError after the bill was written."""
    planned(repo)
    fake([nano({"answers": [{**CENTS, **odd}]})])
    said = person("board", "lookup")
    assert said.exit_code == 0 and "from the repo: 0 of 2 open questions settled" in said.stdout, said.output
    with Store.open(repo) as store:
        assert {it["state"] for it in B.items(store)} == {"open"}
