"""docs/test/practice.sh, the ladder for the first hour with a key, climbed whole against the stand-ins: the
scripted fake Token Factory (tests/fake_tokenfactory.py, started by the ladder itself) and Docker in place of
ConTree, as tests/test_escape.py uses it. Only the live calls are new when the key comes."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRACTICE = ROOT / "docs" / "test" / "practice.py"


def docker_runs() -> bool:
    return (
        shutil.which("docker") is not None
        and subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    )


def ladder(tmp_path: Path, *args: str, **env: str) -> subprocess.CompletedProcess:
    """practice.py as practice.sh starts it, its progress and its repos in tmp_path."""
    base = {k: v for k, v in os.environ.items() if not k.startswith(("GRAPHENE_", "PRACTICE_"))}
    base |= {"PRACTICE_STATE": str(tmp_path / "state"), "PRACTICE_WORK": str(tmp_path / "work")} | env
    return subprocess.run([sys.executable, str(PRACTICE), *args], env=base, capture_output=True, text=True,
                          timeout=900)  # fmt: skip


@pytest.mark.skipif(not docker_runs(), reason="needs a running Docker (the sandbox stand-in)")
def test_the_whole_ladder_climbs_against_the_stand_ins(tmp_path):
    done = ladder(tmp_path, "--dry")
    said = done.stdout
    assert done.returncode == 0, said + done.stderr
    lines = said.strip().splitlines()
    assert all(line.startswith("dry run, stand-ins · ") for line in lines)  # every line says so
    assert [ln.split(" · ")[1] for ln in lines if " · PASS · " in ln] == ["PASS"] * 7
    assert " · FAIL · " not in said
    for n in range(1, 7):
        assert f"· PASS · rung {n} · " in said and f"next: docs/test/practice.sh --dry {n + 1}" in said
    assert "next: the ladder is climbed" in said
    assert "arm B: 2 of 2 leaves landed" in said and "a scripted stand-in" in said
    assert "the demo ran to the bill" in said and "(a stand-in's usage)" in said
    rows = json.loads((tmp_path / "state" / "progress.json").read_text())
    assert {r["result"] for r in rows.values()} == {"PASS"} and len(rows) == 7
    ledger = (tmp_path / "state" / "ledger.jsonl").read_text().splitlines()
    assert ledger and "bill so far $0.00" in lines[-1] and sum(json.loads(r)["dollars"] for r in ledger) > 0
    assert "fake-key" not in said


def test_without_docker_the_sandbox_rungs_fail_and_say_so(tmp_path):
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "docker").write_text("#!/bin/sh\nexit 1\n")  # a docker whose daemon does not answer
    (stub / "docker").chmod(0o755)
    path = f"{stub}{os.pathsep}{os.environ['PATH']}"
    local = ladder(tmp_path, "--dry", "2", PATH=path)
    assert local.returncode == 0 and "· PASS · rung 2 · " in local.stdout, local.stdout + local.stderr
    for n in ("3", "4"):
        box = ladder(tmp_path, "--dry", n, PATH=path)
        assert box.returncode == 1 and f"· FAIL · rung {n} · " in box.stdout
        assert (
            "Docker is not running here" in box.stdout
            and f"next: docs/test/practice.sh --dry {n}" in box.stdout
        )
    status = ladder(tmp_path, "--dry", "status").stdout
    assert "2. one leaf local on Nemotron" in status and "3. one leaf in a Sandbox" in status
    assert status.count(" PASS ") == 1 and status.count(" FAIL ") == 2


def test_in_an_agents_shell_the_access_rung_is_typed_by_the_person(tmp_path):
    """Live, from a Claude Code session: the classifier refuses access.py to an agent, so the rung runs
    nothing and says what to type with `!`."""
    done = ladder(tmp_path, "1", CLAUDECODE="1")
    assert done.returncode == 1 and "FAIL · rung 1 · " in done.stdout
    assert "! GRAPHENE_LEDGER=" in done.stdout and "docs/test/access.py --out" in done.stdout
    assert "most likely: the access check is yours to run" in done.stdout
    assert not (tmp_path / "state" / "access.json").exists()  # nothing was run
    assert not done.stdout.startswith("dry run")


def test_the_dry_run_removes_only_a_state_it_made(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "mine.txt").write_text("not the ladder's")
    done = ladder(tmp_path, "--dry")
    assert done.returncode == 2 and (state / "mine.txt").read_text() == "not the ladder's"
    assert "the ladder did not make" in done.stdout and "nothing was removed" in done.stdout
    assert not (tmp_path / "work").exists()


def test_every_line_of_the_dry_run_says_so(tmp_path):
    for args in (["--dry", "nine"], ["--dry", "status"]):
        said = ladder(tmp_path, *args).stdout
        lines = said.strip().splitlines()
        assert lines and all(ln.startswith("dry run, stand-ins · ") for ln in lines)
        assert "typed by you" not in said  # the dry run types everything itself
