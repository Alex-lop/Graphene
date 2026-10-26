"""Any CLI agent as the executor (26 October): `--with '<command>'` gets the prompt last, as before; a command
that takes it elsewhere says where with `{prompt}`, or `{prompt_file}` for the path of a file holding it,
written in the run's own log directory, outside every scope. Such an agent is held by git at `done`."""

import subprocess
import sys
from pathlib import Path

import pytest

from graphene_map import plan
from graphene_map.plan import DONE, Caller
from graphene_map.run import command_for, run_plan
from graphene_map.store import Store

ALEX = Caller("alex", True)
# an agent that takes the prompt as --message: it writes the leaf's id, read from the prompt, into api.py
BY_FLAG = """
import pathlib, sys
prompt = sys.argv[sys.argv.index("--message") + 1]
assert sys.argv[-1] == "--yes", sys.argv  # the prompt was put where the command said, not last
leaf = prompt.split(" (revision")[0].split("\\n")[-1]
pathlib.Path("api.py").write_text(f"LEAF = {leaf!r}\\n")
"""
# an agent that reads the prompt from a file named after --message-file
BY_FILE = """
import pathlib, sys
path = pathlib.Path(sys.argv[sys.argv.index("--message-file") + 1])
prompt = path.read_text()
leaf = prompt.split(" (revision")[0].split("\\n")[-1]
pathlib.Path("api.py").write_text(f"LEAF = {leaf!r}\\nFROM = {str(path)!r}\\n")
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "api.py").write_text("LEAF = None\n")
    (tmp_path / ".gitignore").write_text(".graphene/\n")
    git("add", "-A")
    git("-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "start")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_the_prompt_is_last_unless_the_command_says_where_it_goes(tmp_path):
    assert command_for("my-agent --flag", "do it", "s-1", False) == ["my-agent", "--flag", "do it"]
    argv = command_for("gemini -p {prompt} --yolo", "do it", "s-1", False)
    assert argv == ["gemini", "-p", "do it", "--yolo"]
    assert command_for("agent --message={prompt}", "do it", "s-1", False) == ["agent", "--message=do it"]
    argv = command_for("aider --message-file {prompt_file} --yes", "do it\n- a note", "s-1", False, tmp_path)
    assert argv[:2] == ["aider", "--message-file"] and argv[3:] == ["--yes"]
    assert Path(argv[2]).parent == tmp_path and Path(argv[2]).read_text() == "do it\n- a note"
    assert Path(argv[2]).name.startswith("prompt-s-1-")


def test_claude_keeps_its_session_flags_and_the_prompt_after_the_dashes():
    argv = command_for("claude -p", "do it", "s-1", False)
    assert argv == ["claude", "-p", "--session-id", "s-1", "--", "do it"]


@pytest.mark.parametrize("source, how", [(BY_FLAG, "--message {prompt} --yes"),
                                         (BY_FILE, "--message-file {prompt_file}")])  # fmt: skip
def test_an_agent_that_takes_the_prompt_elsewhere_runs_and_is_held_by_git_at_done(repo, source, how):
    script = repo.parent / f"{repo.name}-agent.py"
    script.write_text(source)
    with Store.open(repo) as store:
        plan.propose(store, [{"id": "greet", "title": "api says greet", "scope": ["api.py"],
                              "check": "grep -q \"LEAF = 'greet'\" api.py"}], ALEX)  # fmt: skip
        said = []
        done = run_plan(store, repo, f"{sys.executable} {script} {how}", 1, None, said.append,
                        repo / ".graphene" / "runs")  # fmt: skip
        assert [n.id for n in done] == ["greet"] and plan.get(store, "greet").state == DONE
    text = (repo / "api.py").read_text()
    assert text.startswith("LEAF = 'greet'\n")
    if "FROM" in text:  # the prompt file: in the run's own log directory, outside every scope, and kept
        where = Path(text.split("FROM = ")[1].strip().strip("'"))
        assert where.parent == repo / ".graphene" / "runs" and "greet (revision" in where.read_text()
