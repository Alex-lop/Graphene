# ruff: noqa: F811  (pytest fixtures imported from test_plan_cli are named again as arguments)
"""The text form at the command line: `plan --text`, `plan edit` and `node edit` through the person's
$EDITOR, `plan propose -` in text, and `plan undo`. The editor here is a script that edits the file
the way a person would, and `propose -` is run on a real terminal, where it used to wait for ever."""

import os
import pty
import select
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_plan_cli import agent, person, repo, runner  # noqa: F401  (fixtures)

from graphene_map.cli import build

TEXT = """\
goal: users come back with their ids
- the API  [api]
  - users returns ids  [ids]
      scope: api.py
      check: grep -q ids api.py
  - document it  [docs]
      scope: README.md
      check: test -f README.md
      needs: ids
"""


def person_with(*args, input=None):
    return runner.invoke(build(), list(args), env={"GRAPHENE_AS": "person:alex"}, input=input)


def editor(monkeypatch, tmp_path, python: str) -> None:
    """$EDITOR as a script that rewrites the file: `text` holds what the person sees."""
    script = tmp_path / "edit.py"
    script.write_text(
        f"import sys\np = sys.argv[1]\ntext = open(p).read()\n{python}\nopen(p, 'w').write(text)\n"
    )
    monkeypatch.setenv("EDITOR", f"{sys.executable} {script}")
    monkeypatch.delenv("VISUAL", raising=False)


def test_an_agent_proposes_in_text_and_the_person_reads_it_back(repo):
    proposed = agent("plan", "propose", "-", input=TEXT)
    assert proposed.exit_code == 0, proposed.output
    assert "proposed ids: users returns ids" in proposed.stdout
    assert "3 proposed: nobody can start them until the person accepts" in proposed.stdout
    shown = person("plan", "--text")
    assert (
        "? users returns ids  [ids]" in shown.stdout
        and "goal: users come back with their ids" in shown.stdout
    )


def test_a_person_edits_the_plan_in_their_editor_and_the_save_is_applied(repo, monkeypatch, tmp_path):
    agent("plan", "propose", "-", input=TEXT)
    editor(
        monkeypatch,
        tmp_path,
        "text = text.replace('? ', '- ').replace('check: test -f README.md', 'check: true')",
    )
    edited = person("plan", "edit")
    assert edited.exit_code == 0, edited.output
    assert "accepted api" in edited.stdout and "docs: check changed" in edited.stdout
    assert "(the plan of" in edited.stderr  # which repository, on every write
    assert "- document it  [docs]" in person("plan", "--text").stdout
    assert not list((repo / ".graphene" / "edits").iterdir())
    undone = person("plan", "undo")
    assert undone.exit_code == 0 and "undid: plan edit" in undone.stdout
    assert "? document it  [docs]" in person("plan", "--text").stdout


def test_a_refused_save_names_the_line_and_keeps_the_text(repo, monkeypatch, tmp_path):
    person_with("plan", "propose", "-", input=TEXT)
    editor(
        monkeypatch,
        tmp_path,
        "text = text.replace('scope: README.md', 'scope: README.md\\n    signoff: maybe')",
    )
    refused = person("plan", "edit", "docs")
    assert refused.exit_code == 1
    assert "signoff is yes or no, not 'maybe'. Nothing was applied" in refused.stderr
    [kept] = (repo / ".graphene" / "edits").iterdir()
    assert "signoff: maybe" in kept.read_text()
    assert "signoff: yes" not in person("plan", "--text").stdout


def test_node_edit_opens_one_contract_and_a_line_under_it_is_a_child(repo, monkeypatch, tmp_path):
    person_with("plan", "propose", "-", input=TEXT)
    seen = tmp_path / "seen.txt"
    child = "\\n    - the id column  [col]\\n        scope: schema.py\\n        check: true"
    change = f"text = text.replace('check: grep -q ids api.py', 'check: grep -q ids api.py{child}')"
    editor(monkeypatch, tmp_path, f"open({str(seen)!r}, 'w').write(text)\n{change}")
    edited = person("node", "edit", "ids")
    assert edited.exit_code == 0, edited.output
    assert "[ids]" in seen.read_text() and "[docs]" not in seen.read_text()  # one node, not its siblings
    assert "added col: the id column" in edited.stdout
    text = person("plan", "--text").stdout
    assert "  - users returns ids  [ids]\n" in text and "    - the id column  [col]" in text


def test_saved_unchanged_nothing_changes(repo, monkeypatch, tmp_path):
    person_with("plan", "propose", "-", input=TEXT)
    editor(monkeypatch, tmp_path, "pass")
    same = person("plan", "edit")
    assert same.exit_code == 0 and same.stdout == "nothing changed\n"


def test_a_check_that_names_a_missing_file_is_warned_about_on_add(repo):
    added = person(
        "node", "add", "csv still loads", "--scope", "tests/x.py", "--check", "python3 test/test_csv.py"
    )
    assert added.exit_code == 0
    assert "warning: n1's check names test/test_csv.py" in added.stderr


@pytest.mark.skipif(not hasattr(pty, "openpty"), reason="needs a pseudo-terminal")
def test_propose_dash_on_a_terminal_with_nothing_piped_says_so_at_once(repo):
    """On 22 September `graphene plan propose -` typed at a terminal waited for ever."""
    graphene = shutil.which("graphene", path=str(Path(sys.executable).parent)) or shutil.which("graphene")
    main, sub = pty.openpty()
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID")}
    started = time.monotonic()
    proc = subprocess.Popen(
        [graphene, "plan", "propose", "-"], stdin=sub, stdout=sub, stderr=sub, cwd=repo, env=env
    )
    os.close(sub)
    said = b""
    while time.monotonic() - started < 20:
        if select.select([main], [], [], 0.2)[0]:
            try:
                chunk = os.read(main, 4096)
            except OSError:  # the other side is closed: the command has ended
                break
            if not chunk:
                break
            said += chunk
        elif proc.poll() is not None:
            break
    os.close(main)
    proc.kill()
    code = proc.wait(timeout=5)
    assert code == 1 and time.monotonic() - started < 20
    assert b"nothing is piped here" in b" ".join(said.split())


def test_an_executor_run_started_is_told_to_stop_not_to_take_the_next_leaf(repo, monkeypatch):
    """On 22 September `release` told a run's executor "next: n9 … `graphene node start n9`", while
    its prompt said "Do not start any other node"."""
    person_with("plan", "propose", "-", input=TEXT.replace("? ", "- "))
    person("plan", "accept")
    env = {
        "GRAPHENE_NODE": "ids",
        "CLAUDECODE": "1",
        "CLAUDE_CODE_SESSION_ID": "5e55105e-0000-4000-8000-000000000009",
    }
    runner.invoke(build(), ["node", "start", "ids"], env=env)
    released = runner.invoke(build(), ["node", "release", "ids", "--why", "needs schema.py"], env=env)
    assert "next: stop here" in released.stdout and "graphene node start" not in released.stdout


def test_the_log_keeps_what_a_goal_said_before(repo):
    person("plan", "goal", "the first aim")
    person("plan", "goal", "the second aim")
    assert "the second aim  (it said: the first aim)" in person("plan", "log").stdout


def test_a_prompts_leaf_or_a_finished_leaf_does_not_hide_a_typo_in_a_check(repo, finish):
    """Recheck: once a leaf made from a prompt (scope **) was in the plan, every path counted as one a
    leaf may create, and the warning went silent for the whole plan until it was archived. A finished
    leaf's scope creates nothing more either. The warning said "cannot pass" of what is a guess."""
    from graphene_map import plan
    from graphene_map.store import Store

    alex, old = plan.Caller("alex", True), {"id": "old", "title": "old tests", "scope": ["test/**"]}
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "typed", "title": "fix the typo", "scope": ["**"]}], alex, aside=True)
        plan.propose(store, [{**old, "check": "true"}], alex)
        plan.start(store, "old", alex, repo)
        finish(store, repo, "old", alex, checkout=repo)
    check = "python -m pytest test/test_csvfeed.py"
    added = person("node", "add", "csv feed", "--scope", "feeds/csv.py", "--check", check)
    assert added.exit_code == 0, added.output
    said = " ".join(added.stderr.split())
    assert "names test/test_csvfeed.py, which is not in the repo and no leaf's scope may create it" in said
    assert "check the spelling" in said
