"""docs/proof/nemotron.sh, end to end against the recorded fake: the Nemotron path from nothing to
`git log --graph` reading as the tree, and the bill. The script is the demo; this runs it on a tiny
repository instead of feeds, with a scripted Ultra planner and scripted Nano executors, so every
command in it is known to work before a key spends anything on it."""

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from fake_tokenfactory import Fake, call

SCRIPT = Path(__file__).resolve().parents[1] / "docs" / "proof" / "nemotron.sh"
MAKE = textwrap.dedent('''\
    import pathlib, subprocess, sys
    d = pathlib.Path(sys.argv[1]); d.mkdir(parents=True)
    (d / ".gitignore").write_text(".graphene/\\n__pycache__/\\n")
    (d / "app.py").write_text("from words import HELLO\\n\\ndef greet():\\n    return 'hi'\\n")
    (d / "words.py").write_text("HELLO = 'hi'\\n")
    (d / "bye.py").write_text("def bye():\\n    return 'bye'\\n")
    for a in (["init", "-q"], ["config", "user.email", "t@e.com"], ["config", "user.name", "T"],
              ["add", "-A"], ["commit", "-qm", "start"]):
        subprocess.run(["git", "-C", str(d), *a], check=True)
''')
PLAN = """```plan
goal: a friendlier app
- say hello  [friendly]
  ? greet says hello  [greet]
      greet returns the word hello, from words.py
      scope: app.py, words.py
      check: python3 -c 'import app; assert app.greet() == "hello"'
  ? bye says goodbye  [farewell]
      scope: bye.py
      check: python3 -c 'import bye; assert bye.bye() == "goodbye"'
```"""
GREET_CHECK = "python3 -c 'import app; assert app.greet() == \"hello\"'"
SCRIPTS = {
    "planner": [call("list", path="."), call("read", path="app.py"), {"content": PLAN}],
    # the prune took words.py from greet's scope: its first hold comes back wanting it
    "greet (revision 2": [call("edit", path="app.py", old="return 'hi'", new="return HELLO"),
                          call("write", path="words.py", content="HELLO = 'hello'\n"),
                          call("release", why="the word lives in words.py", wants=["words.py"])],
    "greet (revision 3": [call("edit", path="app.py", old="return 'hi'", new="return HELLO"),
                          call("edit", path="words.py", old="'hi'", new="'hello'"),
                          call("run", command=GREET_CHECK), call("done")],
    "farewell (revision": [call("edit", path="bye.py", old="'bye'", new="'goodbye'"), call("done")],
}  # fmt: skip


def reply(body):
    first = body["messages"][1]["content"] if len(body["messages"]) > 1 else ""
    key = "planner" if "Ultra" in body["model"] else next((k for k in SCRIPTS if k in first), None)
    steps = SCRIPTS.get(key, [])
    k = sum(1 for m in body["messages"] if m["role"] == "assistant")
    return steps[k] if k < len(steps) else {"content": "nothing more"}


@pytest.mark.skipif(shutil.which("graphene") is None, reason="needs graphene on PATH (uv run puts it there)")
def test_the_demo_script_runs_from_nothing_to_the_bill(tmp_path):
    make = tmp_path / "make_tiny.py"
    make.write_text(MAKE)
    with Fake([reply] * 60) as f:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GRAPHENE_", "CLAUDE", "CODEX"))}
        print_it = env.pop("SHOW_DEMO", None)
        env |= f.env() | {"MAKE_REPO": f"{sys.executable} {make}", "PARAGRAPH": "make the app friendlier",
                          "PRUNE": "sed -i.bak -e 's#app.py, words.py#app.py#'",
                          "HOME": str(tmp_path)}  # fmt: skip
        env.pop("NEBIUS_PROJECT_ID", None)
        done = subprocess.run(["bash", str(SCRIPT), str(tmp_path / "demo")], capture_output=True, text=True,
                              env=env, timeout=300)  # fmt: skip
    said = done.stdout + done.stderr
    if print_it:
        print(said)
    assert done.returncode == 0, said
    assert "$ graphene init --planner nemotron --executor nemotron" in said
    assert "$ graphene node widen greet" in said  # the came-back leaf's offer, taken
    graph = subprocess.run(["git", "-C", str(tmp_path / "demo"), "log", "--merges", "--format=%s"],
                           capture_output=True, text=True).stdout.split("\n")  # fmt: skip
    assert "greet says hello (greet)" in graph and "bye says goodbye (farewell)" in graph
    assert "bill: $" in said and "at list price" in said  # the record's bill, at the end
    assert "2 of 2 passed at last run, 0 runs failed on the way; 1 write refused" in said
    assert (tmp_path / "demo" / "words.py").read_text() == "HELLO = 'hello'\n"
    models = {r["model"] for r in f.requests}
    assert models == {"nvidia/Nemotron-3-Ultra-fake", "nvidia/Nemotron-3-Nano-fake"}
    assert json.dumps(f.requests).count("fake-key") == 0
