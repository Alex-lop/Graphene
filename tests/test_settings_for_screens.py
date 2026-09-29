"""What the screen lanes call to show the settings and to re-ask a plan finer or coarser: `?` in
graphene watch, the root row of the page's board and graph, and a replay. tui.py wires them later."""

import json
import subprocess

from graphene_map import ask as A
from graphene_map import demo, server
from graphene_map import plan as P
from graphene_map import settings as S
from graphene_map.store import Store

ALEX = P.Caller("alex", True)


def test_the_help_screen_gets_every_setting_as_lines(tmp_path):
    with Store.open(tmp_path) as store:
        S.apply(store, "protected: secrets/**\nnever: add a dependency\nsize: finer\n", ALEX)
        lines = S.lines_for_screen(store)
    assert "protected: secrets/**" in lines and "never: add a dependency" in lines
    assert "size: finer · board: on" in lines  # the one-value settings share a line
    assert any(line.startswith("planner: ") for line in lines)
    assert not any(line.startswith("#") for line in lines)
    assert lines[-1] == "graphene config edit changes them"


def test_the_page_and_a_replay_carry_the_settings(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    with Store.open(tmp_path) as store:
        S.apply(store, "readonly: README.md\nsize: coarser\n", ALEX)
        said = json.loads(server.payload(store, []))["plan"]["settings"]
    assert said == {"protected": [], "readonly": ["README.md"], "never": [], "size": "coarser"}
    assert {f"settings:{k}" for k in ("protected", "readonly", "never", "size")} <= set(demo.META)


def test_the_reask_key_gets_the_command_it_runs(tmp_path):
    with Store.open(tmp_path) as store:
        assert A.reask_argv(store, "finer") is None  # nothing asked yet
        store.log_node("*", P._now(), "asked", "alex", None, None, {"note": "add ids", "about": None})
        store.log_node("*", P._now(), "asked", "alex", None, None, {"note": "why?", "about": "ids"})
        assert A.reask_argv(store, "coarser") == ["graphene", "ask", "add ids", "--coarser"]
