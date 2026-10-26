"""A port per task (26 October): every executor `graphene run` starts gets PORT and GRAPHENE_PORT, distinct
per running leaf and per fork (PORT_BASE + slot * 10 + fork), free when it is handed out, said in the
prompt and on the attempt row, and given to the leaf's check too."""

import json
import socket
import subprocess
import sys

import pytest

from graphene_map import plan
from graphene_map import run as R
from graphene_map.plan import DONE, Caller
from graphene_map.run import PORT_BASE, Ports, prompt_for, run_parallel
from graphene_map.store import Store

ALEX = Caller("alex", True)
# the executor writes its PORT into its leaf's file; the check passes only when it sees the same PORT
WORKER = """
import json, os, pathlib, sys, time
node = os.environ["GRAPHENE_NODE"]
told = f"bind $PORT ({os.environ['PORT']})" in sys.argv[-1]
pathlib.Path(f"{node}.txt").write_text(os.environ["PORT"] + "\\n")
with open(sys.argv[1], "a") as log:
    log.write(json.dumps({"node": node, "port": os.environ["PORT"], "fork": os.environ.get("GRAPHENE_FORK"),
                          "graphene_port": os.environ["GRAPHENE_PORT"], "told": told}) + "\\n")
time.sleep(0.6)
"""
FORKED = WORKER.replace('pathlib.Path(f"{node}.txt")', 'pathlib.Path("api.py")')


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "T")
    (root / ".gitignore").write_text(".graphene/\n")
    (root / "api.py").write_text("none\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "start")
    monkeypatch.chdir(root)
    return root


def env_of(port: int) -> dict:
    return {"PORT": str(port), "GRAPHENE_PORT": str(port)}


def go(repo, source, leaves, workers=2, **kw):
    script, log = repo.parent / "worker.py", repo.parent / "ports.log"
    script.write_text(source)
    with Store.open(repo) as store:
        plan.propose(store, leaves, ALEX)
    said: list[str] = []
    command = f"{sys.executable} {script} {log}"
    done = run_parallel(lambda: Store.open(repo), repo, repo, workers, command, say=said.append, attempts=1,
                        **kw)  # fmt: skip
    ran = [json.loads(line) for line in log.read_text().splitlines()]
    return done, ran, said


def test_two_leaves_at_once_get_different_ports_and_each_check_sees_its_leafs_port(repo):
    leaves = [{"id": n, "title": n, "scope": [f"{n}.txt"], "check": f'grep -qx "$PORT" {n}.txt'}
              for n in ("n1", "n2")]  # fmt: skip
    done, ran, said = go(repo, WORKER, leaves)
    assert sorted(n.id for n in done) == ["n1", "n2"], said
    ports = {r["node"]: int(r["port"]) for r in ran}
    assert len(set(ports.values())) == 2 and all(p >= PORT_BASE for p in ports.values())
    assert all(r["graphene_port"] == r["port"] and r["told"] for r in ran)  # said in the prompt too
    with Store.open(repo) as store:
        for n in ("n1", "n2"):
            assert plan.get(store, n).state == DONE
            assert store.node_log(n, ("attempt",))[-1]["detail"]["port"] == ports[n]  # on record
            assert plan.port_env(store, plan.get(store, n)) == env_of(ports[n])


def test_forks_get_different_ports_and_each_forks_check_sees_its_own(repo):
    leaves = [{"id": "api", "title": "api", "scope": ["api.py"], "check": 'grep -qx "$PORT" api.py'}]
    done, ran, said = go(repo, FORKED, leaves, forks=R.Forks(3))
    assert [n.id for n in done] == ["api"], said
    ports = {r["fork"]: int(r["port"]) for r in ran}
    assert sorted(ports) == ["a", "b", "c"] and len(set(ports.values())) == 3
    assert all(r["told"] for r in ran)
    with Store.open(repo) as store:
        forks = [e["detail"] for e in store.node_log("api", ("fork",)) if "paths" in e["detail"]]
        kept = store.node_log("api", ("picked",))[-1]["detail"]["fork"]
        assert plan.port_env(store, plan.get(store, "api")) == env_of(ports[kept])  # the hold's: the kept's
    assert {f["fork"]: f["state"] for f in forks} == {"a": "passed", "b": "passed", "c": "passed"}  # each own
    assert (repo / "api.py").read_text() == f"{ports[kept]}\n"  # the kept fork's work landed under its port


def test_ports_skip_one_something_holds_and_come_back_when_a_leaf_ends():
    ports = Ports()
    with socket.socket() as s:
        s.bind(("", PORT_BASE + 20))
        assert ports.take(2, 2) == [PORT_BASE + 21, PORT_BASE + 22]
    assert ports.take(0) == [PORT_BASE] and ports.take(0) == [PORT_BASE + 1]  # taken here: the next
    ports.give_back([PORT_BASE])
    assert ports.take(0) == [PORT_BASE]


def test_the_prompt_says_the_port_only_when_the_run_gave_one():
    node = plan.Node(id="n1", title="n1", scope=["n1.txt"])
    assert "bind $PORT (41000): it is this leaf's own" in prompt_for(node, [], None, port=41000)
    assert "PORT" not in prompt_for(node, [], None)
