"""An edit in the target checkout while an agent works must survive the attempted merge."""

import os
import shlex
import subprocess
import sys
import time

import test_run as R

from graphene_map import plan
from graphene_map.store import Store


def test_a_human_edit_during_a_worktree_run_survives_and_holds_the_merge(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    repo = R.repo.__wrapped__(root, monkeypatch)
    ready, release = tmp_path / "ready", tmp_path / "release"
    script = tmp_path / "agent.py"
    script.write_text(
        "from pathlib import Path\nimport time\n"
        f"Path({str(ready)!r}).touch()\n"
        f"while not Path({str(release)!r}).exists(): time.sleep(0.05)\n"
        'Path("api.py").write_text("ids = [1]\\n")\n'
    )
    with Store.open(repo) as store:
        plan.propose(store, [R.users_node()], R.ALEX)
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
    env = {
        **os.environ,
        "NEBIUS_API_KEY": "fake-key",
        "GRAPHENE_KEYCHAIN": "off",
        "GRAPHENE_TOKENFACTORY_URL": "http://127.0.0.1:9",
        "ZDOTDIR": "/private/tmp/graphene-verify-empty-zdot",
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from graphene_map.cli import app; app()",
            "run",
            "--with",
            command,
            "--attempts",
            "1",
        ],
        cwd=repo,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        until = time.monotonic() + 15
        while not ready.exists() and process.poll() is None and time.monotonic() < until:
            time.sleep(0.05)
        assert ready.exists()
        (repo / "api.py").write_text('human = "keep this"\n')
        release.touch()
        said, _ = process.communicate(timeout=30)
    finally:
        release.touch()
        if process.poll() is None:
            process.communicate(timeout=30)
    assert (repo / "api.py").read_text() == 'human = "keep this"\n', said
    with Store.open(repo) as store:
        node = plan.get(store, "n1")
        assert node.state == plan.REVIEW, said
        assert not store.node_log("n1", ("landed",))
    saved = subprocess.check_output(["git", "-C", str(repo), "show", "graphene/n1:api.py"], text=True)
    assert saved == "ids = [1]\n"
