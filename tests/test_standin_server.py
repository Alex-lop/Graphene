"""dev/proof/standin.py, the scripted stand-in as a server of its own: it prints its URL first, serves until
it is killed, and `graphene auto` against it runs a race for $0 that changes the store as a live run would."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from graphene_map import plan
from graphene_map.store import Store

ROOT = Path(__file__).resolve().parents[1]
STANDIN = ROOT / "dev" / "proof" / "standin.py"
MAKE = ROOT / "dev" / "proof" / "make_wordkit.py"
GOAL = ("wordkit grows three things at once: a --top N option on the CLI that prints the N most common "
        "words with their counts; a reading time in whole minutes, rounded up, at 200 words a minute; and "
        "hyphenated words like well-known counted as one word.")


@pytest.mark.skipif(shutil.which("graphene") is None, reason="needs graphene on PATH (uv run puts it there)")
def test_the_standin_serves_until_killed_and_auto_races_against_it_for_nothing(tmp_path):
    server = subprocess.Popen([sys.executable, str(STANDIN)], stdout=subprocess.PIPE, text=True)
    try:
        url = server.stdout.readline().strip()
        assert url.startswith("http://127.0.0.1:") and url.endswith("/v1/"), url
        assert "NEBIUS_API_KEY=fake-key" in server.stdout.readline()
        repo = tmp_path / "wordkit"
        subprocess.run([sys.executable, str(MAKE), str(repo)], check=True, capture_output=True)
        # as test_demo_auto strips them: the race is the person's, not a move of the agent whose shell this is
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GRAPHENE_", "CLAUDE", "CODEX"))
               and k not in ("AI_AGENT", "NEBIUS_PROJECT_ID")}
        env |= {"GRAPHENE_TOKENFACTORY_URL": url, "NEBIUS_API_KEY": "fake-key", "GRAPHENE_KEYCHAIN": "off",
                "HOME": str(tmp_path), "GRAPHENE_PERSON": "the test"}
        subprocess.run(["graphene", "init", "--planner", "nemotron", "--executor", "nemotron"], cwd=repo,
                       env=env, check=True, capture_output=True, timeout=120)
        # a short take: one round, so the three tasks land and the goal's red check ends it
        done = subprocess.run(["graphene", "auto", GOAL, "--budget", "2", "--forks", "3", "--rounds", "1",
                               "--parallel", "4", "--check", "python3 -m unittest"], cwd=repo, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
        assert "3 tasks can run at once" in done.stdout, done.stdout
        assert "the goal's check failed" in done.stdout, done.stdout
        with Store.open(repo) as store:
            states = {n.id: n.state for n in plan.nodes(store)}
        assert {states[t] for t in ("top", "reading", "hyphens")} == {"done"}, states
        assert server.poll() is None  # still serving after the run
    finally:
        server.terminate()
        server.wait(timeout=10)
