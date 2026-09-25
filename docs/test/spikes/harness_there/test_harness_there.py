"""Placement B, "the harness there", driven by a real `graphene run`: OpenCode runs in the leaf's Docker
sandbox against the recorded fake, which scripts it to edit the in-scope file, try a write outside the
scope, make a new file outside it, and look for the key. The leaf lands; what the gate saw is asserted.

Skipped without Docker or without the image (`docker build -t graphene-harness-there:opencode-1.18.31
docs/test/spikes/harness_there`). `python docs/test/spikes/harness_there/test_harness_there.py` runs the
measurement in RESULTS.md: both placements, the same leaf, landing and handing back, three times each.
"""

import contextlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tests"))
from fake_tokenfactory import Fake, call  # noqa: E402

from graphene_map import plan  # noqa: E402
from graphene_map import tokenfactory as tf  # noqa: E402
from graphene_map.plan import DONE, OPEN, Caller  # noqa: E402
from graphene_map.run import named, run_plan  # noqa: E402
from graphene_map.store import Store  # noqa: E402

HERE = Path(__file__).resolve().parent
IMAGE = "graphene-harness-there:opencode-1.18.31"
NANO = "nvidia/Nemotron-3-Nano-fake"
CHECK = "python3 -c 'import app; assert app.greet() == \"hello\"'"
PROBE = ('test -n "$NEBIUS_API_KEY" && echo key-in-env || echo no-key-in-env; '
         "test -r /tmp/graphene/key && echo key-file-readable || echo no-key-file")  # fmt: skip
WITH = {"A": f"nemotron --model {NANO} --placement sandbox",
        "B": f"{sys.executable} {HERE / 'wrapper.py'} --model {NANO}"}  # fmt: skip


def usable() -> bool:
    if shutil.which("docker") is None or subprocess.run(["docker", "info"], capture_output=True).returncode:
        return False
    return subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode == 0


needs_image = pytest.mark.skipif(not usable(), reason=f"needs a running Docker and the image {IMAGE}")


def make_repo(root: Path) -> Path:
    root.mkdir(parents=True)
    git = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)  # noqa: E731
    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (root / ".gitignore").write_text(".graphene/\n__pycache__/\n")
    (root / "app.py").write_text('def greet():\n    return "hi"\n')
    (root / "other.py").write_text("x = 1\n")
    git("add", "-A")
    git("commit", "-qm", "start")
    return root


def steps(placement: str, scenario: str) -> list[dict]:
    """The same leaf, said in each placement's tools: A's are Graphene's own, B's are OpenCode's."""
    if placement == "A":
        read, edit = call("view", path="app.py"), call("edit", path="app.py", old='"hi"', new='"hello"')
        out = call("write", path="other.py", content="x = 2\n")
        stray = call("run", command="echo x > stray.txt")
        probe, check, finish = call("run", command=PROBE), call("run", command=CHECK), call("done")
        back = call("release", why="the greeting is also set in other.py", wants=["other.py"])
    else:
        read = call("read", filePath="/work/app.py")
        edit = call("edit", filePath="/work/app.py", oldString='"hi"', newString='"hello"')
        out = call("write", filePath="/work/other.py", content="x = 2\n")
        stray = call("bash", command="echo x > /work/stray.txt", description="a new file outside the scope")
        probe = call("bash", command=PROBE, description="where is the key")
        check = call("bash", command=CHECK, description="the leaf's check")
        finish = {"content": "The greeting says hello and the check passes."}
        back = {"content": "I cannot finish inside app.py.\nRELEASE: the greeting is also set in other.py\n"
                "WANTS: other.py"}  # fmt: skip
    if scenario == "land":
        return [read, edit, out, stray, probe, check, finish]
    return [read, out, back]


def scripted(placement: str, scenario: str):
    said = steps(placement, scenario)

    def reply(body):
        if not body.get("tools"):  # OpenCode's session title (asked without tools unless --title)
            return {"content": "one leaf"}
        k = sum(1 for m in body["messages"] if m["role"] == "assistant")
        return said[k] if k < len(said) else {"content": "nothing more"}

    return reply


def drive(tmp: Path, placement: str, scenario: str) -> dict:
    """One `graphene run` of the leaf; what it took and what Graphene's store and git saw."""
    root = make_repo(tmp / f"{placement}-{scenario}")
    with Fake([scripted(placement, scenario)] * 30) as f, contextlib.chdir(root), \
            mock.patch.dict(os.environ, {**f.env(), "GRAPHENE_SANDBOX": "docker"}):  # fmt: skip
        tf._listed.cache_clear()
        with Store.open(root) as store:
            plan.set_goal(store, "say hello", Caller("alex", True))
            plan.propose(store, [{"id": "greet", "title": "say hello", "goal": "greet says hello",
                                  "scope": ["app.py"], "check": CHECK}], Caller("alex", True))  # fmt: skip
            said: list[str] = []
            began = time.monotonic()
            done = run_plan(
                store, root, named(WITH[placement]), 1, None, said.append, root / ".graphene" / "runs"
            )
            wall = time.monotonic() - began
            node = plan.get(store, "greet")
            log = {
                k: [e["detail"] for e in store.node_log("greet", (k,))]
                for k in ("denied", "breach", "released")
            }
            offers = [what for _, what, _ in plan.offers(store, node)]
        results = [m["content"] for m in f.requests[-1]["messages"] if m["role"] == "tool"]
        sizes = [len(json.dumps(r["messages"])) + len(json.dumps(r.get("tools") or [])) for r in f.requests]
    text = next((root / ".graphene" / "runs").glob("greet-*.txt")).read_text()
    tools = [(m[1], float(m[2])) for m in re.finditer(r"^\s*\d+ (\w+) .*\(([\d.]+) s\)$", text, re.M)]
    ready = re.search(r"sandbox ready[^\d]*([\d.]+) s", text)
    inside = re.search(r"opencode ended \(exit \d+\) after ([\d.]+) s", text)
    return {
        "placement": placement, "scenario": scenario, "landed": [n.id for n in done] == ["greet"],
        "state": node.state, "wall": round(wall, 2), "setup": float(ready.group(1)) if ready else None,
        "tools": tools, "denied": [d["path"] for d in log["denied"]],
        "breach": [p for d in log["breach"] for p in d["paths"]],
        "released": log["released"][-1] if log["released"] else None, "offers": offers,
        "key": next((r for r in results if "key-in-env" in r), None),
        "app": (root / "app.py").read_text(), "other": (root / "other.py").read_text(),
        "stray": (root / "stray.txt").exists(), "requests": len(f.requests), "log": text,
        "opencode": float(inside.group(1)) if inside else None, "request_chars": sizes,
    }  # fmt: skip


@needs_image
def test_opencode_in_the_sandbox_lands_the_leaf_and_the_gate_sees_what_came_back(tmp_path):
    r = drive(tmp_path, "B", "land")
    assert r["landed"] and r["state"] == DONE, r["log"]
    assert r["app"] == 'def greet():\n    return "hello"\n'
    assert r["other"] == "x = 1\n" and not r["stray"]  # layer 2 refused one, the bring-back dropped the other
    assert re.search(r"write other\.py → error: PermissionDenied", r["log"]), r["log"]
    # What the gate saw: the new files outside the scope (the check's own __pycache__ too), after the
    # fact; never the refused write, which only OpenCode's output shows.
    assert "stray.txt" in r["breach"] and r["denied"] == []
    # The key is in the sandbox, readable by the command the model wrote (not in its environment).
    assert "no-key-in-env" in r["key"] and "key-file-readable" in r["key"]
    assert "fake-key" not in r["log"]


@needs_image
def test_a_hand_back_from_the_sandbox_carries_its_reason_and_its_offer(tmp_path):
    r = drive(tmp_path, "B", "handback")
    assert not r["landed"] and r["state"] == OPEN, r["log"]
    assert r["released"]["why"] == "the greeting is also set in other.py"
    assert r["released"]["wants"] == ["other.py"]
    assert any(o.startswith("widen greet's scope to other.py") for o in r["offers"]), r["offers"]


def measure(runs: int = 3) -> None:
    """Both placements, both scenarios, ``runs`` times each: one JSON row a run, then a summary."""
    import tempfile

    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for k in range(runs):
            for placement in ("A", "B"):
                for scenario in ("land", "handback"):
                    r = drive(Path(tmp) / str(k), placement, scenario)
                    r.pop("log")
                    rows.append(r)
                    print(json.dumps(r), flush=True)
    for placement in ("A", "B"):
        for scenario in ("land", "handback"):
            mine = [r for r in rows if r["placement"] == placement and r["scenario"] == scenario]
            walls = [r["wall"] for r in mine]
            per = {}
            for r in mine:
                for name, s in r["tools"]:
                    per.setdefault(name, []).append(s)
            chars = [c for r in mine for c in r["request_chars"]]
            print(
                f"{placement} {scenario}: wall {statistics.median(walls):.2f} s median of {walls}; "
                f"setup {[r['setup'] for r in mine]}; opencode {[r['opencode'] for r in mine]}; "
                f"landed {sum(r['landed'] for r in mine)}/{len(mine)}; "
                f"model calls {[r['requests'] for r in mine]}; "
                f"request characters median {statistics.median(chars):.0f}; "
                + "; ".join(f"{n} median {statistics.median(v):.2f} s (n={len(v)})" for n, v in per.items())
            )


if __name__ == "__main__":
    measure(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
