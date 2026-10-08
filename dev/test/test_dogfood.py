"""dev/process/meter/dogfood.py's ask step, with a stand-in `claude` on the PATH and this checkout's CLI:
`graphene ask` holds the planner on the night, so the step holds nothing of its own."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from graphene_map.store import Store

DOGFOOD = Path(__file__).resolve().parents[1] / "process" / "meter" / "dogfood.py"


def test_the_ask_step_holds_the_planner_once_and_settles_it_at_what_its_stream_says(tmp_path, monkeypatch):
    """The fourth review of 8 October: the step held $1.50 around `graphene ask`, which holds the planner
    itself, so one ask was booked twice, each at its worst case."""
    spec = importlib.util.spec_from_file_location("dogfood", DOGFOOD)
    dogfood = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dogfood)
    repo, bin_ = tmp_path / "repo", tmp_path / "bin"
    repo.mkdir()
    bin_.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@e.com"], ["config", "user.name", "T"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True)
    (repo / "a.py").write_text("x = 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "start"], check=True)
    with Store.open(repo) as store:
        store.set_meta("planner", dogfood.PLANNER)
    plan = "```plan\n? the leaf  [leaf]\n    scope: a.py\n    check: true\n```"
    result = {"type": "result", "subtype": "success", "result": plan, "total_cost_usd": 0.12}
    (tmp_path / "stream.jsonl").write_text(json.dumps(result) + "\n")
    (tmp_path / "text.txt").write_text(plan + "\n")  # asked for no stream, Claude Code prints the answer
    (bin_ / "claude").write_text(f'#!/bin/sh\ncase "$*" in *stream-json*) cat {tmp_path}/stream.jsonl ;; '
                                 f"*) cat {tmp_path}/text.txt ;; esac\n")  # fmt: skip
    cli = "import sys; from graphene_map.cli import app; sys.argv[0] = 'graphene'; app()"
    (bin_ / "graphene").write_text(f'#!/bin/sh\nexec {sys.executable} -c "{cli}" "$@"\n')
    for name in ("claude", "graphene"):
        (bin_ / name).chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("GRAPHENE_AGENT_LIVE_USD", "10")
    monkeypatch.setattr(sys, "argv", ["dogfood.py", str(repo), "ask"])
    assert dogfood.main() == 0
    rows = [json.loads(line) for line in (tmp_path / "night.jsonl").read_text().splitlines()]
    assert [(r["kind"], r["dollars"], r["purpose"]) for r in rows] == [
        ("reserve", 1.5, "dogfood"), ("settle", 0.12, "dogfood")]  # fmt: skip
