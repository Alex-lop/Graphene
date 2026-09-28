"""docs/test/practice.sh, the ladder for the first hour with a key, climbed whole against the stand-ins: the
scripted fake Token Factory (tests/fake_tokenfactory.py, started by the ladder itself) and Docker in place of
ConTree, as tests/test_escape.py uses it. Only the live calls are new when the key comes."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from graphene_map.plan import AGENT_MARKS

ROOT = Path(__file__).resolve().parents[1]
PRACTICE = ROOT / "docs" / "test" / "practice.py"
MARKS = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT", "CODEX_SESSION_ID",
         "CODEX_SANDBOX", "AI_AGENT", *AGENT_MARKS)  # fmt: skip


def docker_runs() -> bool:
    return (
        shutil.which("docker") is not None
        and subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    )


def environment(tmp_path: Path, **env: str) -> dict[str, str]:
    """This environment without a key, an agent's mark or the ladder's settings, its state in tmp_path."""
    gone = ("GRAPHENE_", "PRACTICE_", "NEBIUS_", "CONTREE_")
    base = {k: v for k, v in os.environ.items() if k not in MARKS and not k.startswith(gone)}
    return base | {"PRACTICE_STATE": str(tmp_path / "state"), "PRACTICE_WORK": str(tmp_path / "work")} | env


def ladder(tmp_path: Path, *args: str, **env: str) -> subprocess.CompletedProcess:
    """practice.py as practice.sh starts it, its progress and its repos in tmp_path."""
    return subprocess.run([sys.executable, str(PRACTICE), *args], env=environment(tmp_path, **env),
                          capture_output=True, text=True, timeout=900)  # fmt: skip


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
    # the line to type holds the rung's cap and the locked environment, and names the rung as `next` does
    typed = "GRAPHENE_SPEND_CAP_USD=0.2500 uv run --frozen --extra sandbox python docs/test/access.py"
    assert typed in done.stdout
    assert "then `! docs/test/practice.sh 1` again" in done.stdout
    assert "next: docs/test/practice.sh 1" in done.stdout


def test_in_an_agents_shell_no_live_rung_runs(tmp_path):
    """Live, rungs 2-7 spend on the person's key and are recorded as the person: an agent's shell runs
    none of them. Should one run anyway, nothing leaves the machine: no key, and a proxy that answers
    nothing."""
    dead = {"HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}
    for n, mark in zip(range(2, 8), MARKS, strict=False):
        done = ladder(tmp_path, str(n), **{mark: "1"}, **dead)
        assert done.returncode == 1 and f"FAIL · rung {n} · " in done.stdout, done.stdout + done.stderr
        assert f"an agent's mark ({mark})" in done.stdout
        assert f"    docs/test/practice.sh {n}\n" in done.stdout
        assert "most likely: a live rung is yours to run" in done.stdout
        assert not (tmp_path / "work").exists()  # nothing was built, nothing was run
    dry = ladder(tmp_path, "--dry", "2", CLAUDECODE="1")  # the dry run spends nothing and records no one
    assert dry.returncode == 0 and "· PASS · rung 2 · " in dry.stdout, dry.stdout + dry.stderr


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


def load_practice(tmp_path: Path, monkeypatch):
    """practice.py in this process, live (not dry), its state in tmp_path and no agent's mark set."""
    monkeypatch.delenv("PRACTICE_DRY", raising=False)
    for mark in MARKS:
        monkeypatch.delenv(mark, raising=False)
    spec = importlib.util.spec_from_file_location("practice_under_test", PRACTICE)
    practice = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(practice)
    state = tmp_path / "state"
    state.mkdir()
    for name, path in {"STATE": state, "WORK": tmp_path / "work", "LEDGER": state / "ledger.jsonl",
                       "PROGRESS": state / "progress.json"}.items():  # fmt: skip
        monkeypatch.setattr(practice, name, path)
    return practice


@pytest.mark.parametrize("fails", ["arm A's run", "arm B's ask"])
def test_a_failing_rung_6_never_prints_the_paragraph_and_stops_where_it_failed(tmp_path, monkeypatch, capsys,
                                                                                 fails):  # fmt: skip
    """Rung 6 with graphene stubbed: nothing runs, and a stand-in paragraph (not the sealed one) is passed."""
    practice = load_practice(tmp_path, monkeypatch)
    words = "Stand-in words that must stay sealed:\nthe second line of them, also sealed."
    (tmp_path / "paragraph.md").write_text(words + "\n")
    monkeypatch.setattr(practice, "PARAGRAPH", tmp_path / "paragraph.md")
    built = []

    def feeds(r, name, recorder=None):
        built.append(name)
        (tmp_path / name).mkdir()
        return tmp_path / name, None

    def graphene(r, repo, *args, timeout=900):  # a failure that says the paragraph back, whole and in part
        failing = args[0] == ("run" if fails == "arm A's run" else "ask")
        return (1, f"could not do it: {words}\n{words.splitlines()[1]}") if failing else (0, "ok")

    monkeypatch.setattr(practice.Rung, "feeds", feeds)
    monkeypatch.setattr(practice.Rung, "propose", lambda r, repo, nodes: None)
    monkeypatch.setattr(practice.Rung, "graphene", graphene)
    arm_a = "failed" if fails == "arm A's run" else "done"
    monkeypatch.setattr(practice, "leaves", lambda repo: {"arm-a": arm_a})
    assert practice.climb(6) is False
    said = capsys.readouterr().out
    assert "FAIL · rung 6 · " in said
    for line in words.splitlines():
        assert line not in said and line not in (tmp_path / "state" / "rung-6.log").read_text()
    if fails == "arm A's run":
        assert built == ["arm-a"] and "arm B was not started" in said  # nothing more is spent
    else:
        assert built == ["arm-a", "arm-b"] and "`graphene ask <the sealed paragraph of feeds>" in said
