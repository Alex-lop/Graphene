"""docs/test/practice.sh, the ladder for the first hour with a key, climbed whole against the stand-ins: the
scripted fake Token Factory (tests/fake_tokenfactory.py, started by the ladder itself) and Docker in place of
ConTree, as tests/test_escape.py uses it. Only the live calls are new when the key comes."""

import contextlib
import importlib.util
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
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
    here = {"PRACTICE_STATE": str(tmp_path / "state"), "PRACTICE_WORK": str(tmp_path / "work")}
    return base | here | {"GRAPHENE_KEYCHAIN": "off"} | env  # never the person's real keychain


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


def test_in_a_terminal_of_your_own_the_access_rung_runs_the_check_itself(tmp_path):
    """Live, with no agent's mark: rung 1 runs access.py itself and prints no `!` line. There is no key,
    no ConTree profile and a proxy that answers nothing, so nothing is sent."""
    (tmp_path / "no-contree").mkdir()
    done = ladder(tmp_path, "1", CONTREE_HOME=str(tmp_path / "no-contree"), HTTPS_PROXY="http://127.0.0.1:9",
                  HTTP_PROXY="http://127.0.0.1:9", NO_PROXY="")  # fmt: skip
    assert done.returncode == 1 and "FAIL · rung 1 · " in done.stdout, done.stdout + done.stderr
    assert "NEBIUS_API_KEY is not set in the shell the ladder runs in; nothing was sent" in done.stdout
    assert "docs/test/access.py --out" in (tmp_path / "state" / "rung-1.log").read_text()
    assert (tmp_path / "state" / "access.json").exists() and "! " not in done.stdout


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
    dry = ladder(tmp_path, "--dry", "2", CLAUDECODE="1",  # the dry run spends nothing and records no one
                 PRACTICE_STATE=str(tmp_path / "dry-state"))  # fmt: skip
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
    """Rung 6 with graphene stubbed by a python that says the failure: it is started as graphene is, so its
    command line is logged, and a stand-in paragraph (not the sealed one) is passed. Its apostrophes are
    what shlex quotes as '"'"' in a logged command line."""
    practice = load_practice(tmp_path, monkeypatch)
    words = "Stand-in words that don't stay out in the open:\nthe second line of them, it's sealed as well."
    (tmp_path / "paragraph.md").write_text(words + "\n")
    monkeypatch.setattr(practice, "PARAGRAPH", tmp_path / "paragraph.md")
    built = []

    def feeds(r, name, recorder=None):
        built.append(name)
        (tmp_path / name).mkdir()
        return tmp_path / name, None

    def graphene(r, repo, *args, timeout=900):  # a failure that says the paragraph back, whole and in part
        failing = args[0] == ("run" if fails == "arm A's run" else "ask")
        said = f"could not do it: {words}\n{words.splitlines()[1]}" if failing else "ok"
        script = "import os, sys; print(os.environ['SAID']); sys.exit(int(os.environ['FAILING']))"
        return r.sh([sys.executable, "-c", script, *args], repo, timeout, SAID=said, FAILING=f"{failing:d}")

    monkeypatch.setattr(practice.Rung, "feeds", feeds)
    monkeypatch.setattr(practice.Rung, "propose", lambda r, repo, nodes: None)
    monkeypatch.setattr(practice.Rung, "graphene", graphene)
    arm_a = "failed" if fails == "arm A's run" else "done"
    monkeypatch.setattr(practice, "leaves", lambda repo: {"arm-a": arm_a})
    assert practice.climb(6) == "FAIL"
    said = capsys.readouterr().out
    assert "FAIL · rung 6 · " in said
    log = (tmp_path / "state" / "rung-6.log").read_text()
    for line in words.splitlines():
        for part in [line, *line.split("'")]:  # whole, and in the pieces shlex quotes around an apostrophe
            assert part not in said and part not in log, part
    if fails == "arm A's run":
        assert built == ["arm-a"] and "arm B was not started" in said  # nothing more is spent
    else:
        assert built == ["arm-a", "arm-b"] and "`graphene ask <the sealed paragraph of feeds>" in said


@pytest.mark.skipif(not docker_runs(), reason="needs a running Docker (the sandbox stand-in)")
def test_ctrl_c_stops_a_rung_and_says_what_is_left(tmp_path):
    """Ctrl-C twice during the dry escape test, as a terminal sends it (to the whole process group): no
    traceback, the sandbox cleaned up whole, the rung recorded as stopped, and the cleanup command."""
    ladder_ = subprocess.Popen([sys.executable, str(PRACTICE), "--dry", "4"], env=environment(tmp_path),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               start_new_session=True)  # fmt: skip
    log, deadline = tmp_path / "state" / "rung-4.log", time.monotonic() + 600
    while not (log.exists() and "[redirect]" in log.read_text()):  # inside the sandbox, mid-test
        assert ladder_.poll() is None and time.monotonic() < deadline, ladder_.communicate()
        time.sleep(0.1)
    os.killpg(ladder_.pid, signal.SIGINT)
    time.sleep(0.1)
    with contextlib.suppress(PermissionError, ProcessLookupError):  # gone already: it cleaned up that fast
        os.killpg(ladder_.pid, signal.SIGINT)  # impatient: the second one lands while it cleans up
    said, err = ladder_.communicate(timeout=600)
    assert ladder_.returncode == 130 and "Traceback" not in err, said + err
    assert "· STOPPED · rung 4 · " in said and "stopped by you" in said
    left = [ln for ln in said.splitlines() if "to clean: rm -rf " in ln]
    assert left and str(tmp_path / "work" / "4-escape-") in left[0]
    assert json.loads((tmp_path / "state" / "progress.json").read_text())["4"]["result"] == "STOPPED"
    assert "next: docs/test/practice.sh --dry 4" in said


@pytest.mark.skipif(not docker_runs(), reason="needs a running Docker (the sandbox stand-in)")
@pytest.mark.parametrize("verb, nth", [("create", 1), ("create", 2), ("commit", 1)])
def test_ctrl_c_as_docker_makes_something_leaves_nothing_in_docker(tmp_path, verb, nth):
    """Ctrl-C twice, to the whole process group, the moment `docker <verb>` has made the dry escape rung's
    nth container or image and before its id is back (a docker on PATH holds it back two seconds): the rung
    stops, and no container (none left in the Created state) and no image it made is left in Docker."""
    real, here, stub = shutil.which("docker"), tmp_path / "made", tmp_path / "bin" / "docker"
    here.mkdir()
    stub.parent.mkdir()
    q, h = shlex.quote, shlex.quote(str(tmp_path / "made"))
    stub.write_text(f"""#!/bin/sh
case "$1" in create|commit) ;; *) exec {q(real)} "$@" ;; esac
{q(real)} "$@" > {h}/out; code=$?
cat {h}/out; cat {h}/out >> {h}/"$1"
n=$(wc -l < {h}/"$1"); [ "$1" = {verb} ] && [ $n -eq {nth} ] && touch {h}/held && sleep 2
exit $code
""")  # fmt: skip
    stub.chmod(0o755)
    env = environment(tmp_path, PATH=f"{stub.parent}{os.pathsep}{os.environ['PATH']}")
    ladder_ = subprocess.Popen([sys.executable, str(PRACTICE), "--dry", "4"], env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)  # fmt: skip
    made = {kind: here / kind for kind in ("create", "commit")}
    try:
        deadline = time.monotonic() + 300
        while not (here / "held").exists():
            assert ladder_.poll() is None and time.monotonic() < deadline, ladder_.communicate()
            time.sleep(0.05)
        os.killpg(ladder_.pid, signal.SIGINT)
        time.sleep(0.1)
        with contextlib.suppress(PermissionError, ProcessLookupError):
            os.killpg(ladder_.pid, signal.SIGINT)
        said, err = ladder_.communicate(timeout=300)
        assert ladder_.returncode == 130 and "Traceback" not in err, said + err
        assert "· STOPPED · rung 4 · " in said and "next: docs/test/practice.sh --dry 4" in said
        boxes = made["create"].read_text().split()
        images = made["commit"].read_text().split() if made["commit"].exists() else []
        assert len(boxes) == nth if verb == "create" else len(images) == nth

        def listed(*args: str) -> set[str]:
            return set(subprocess.run(["docker", *args], capture_output=True, text=True).stdout.split())

        assert not set(boxes) & listed("ps", "-aq", "--no-trunc")
        assert not listed("ps", "-aq", "--filter", f"name=graphene-{ladder_.pid}-")
        assert not set(images) & listed("images", "-aq", "--no-trunc")
    finally:
        if ladder_.poll() is None:
            os.killpg(ladder_.pid, signal.SIGKILL)
        for kind, rm in (("create", "rm"), ("commit", "rmi")):  # what a failure left is not left to the next
            if made[kind].exists() and made[kind].read_text().split():
                subprocess.run(["docker", rm, "-f", *made[kind].read_text().split()], capture_output=True)


@pytest.mark.parametrize("n", [1, 3])  # rung 1's access check runs the sandbox smoke on ConTree
@pytest.mark.parametrize("killed", [False, True])
def test_a_stopped_live_sandbox_rung_says_what_may_still_run(tmp_path, monkeypatch, capsys, killed, n):
    """Live, a stop does not cancel a ConTree operation already sent; and a command killed after 120 s
    did not clean up: the STOPPED line says so rather than that all was cleaned up. Nothing runs."""
    practice = load_practice(tmp_path, monkeypatch)

    def stopped(r):
        r.killed = killed
        raise KeyboardInterrupt

    monkeypatch.setitem(practice.RUNGS, n, (*practice.RUNGS[n][:3], stopped))
    try:
        assert practice.climb(n) == "STOPPED"
    finally:
        signal.signal(signal.SIGINT, signal.default_int_handler)
    said = capsys.readouterr().out
    assert "left running, maybe: a ConTree operation already sent runs on to its own time limit" in said
    assert ("was killed, so what it made may be left" in said) is killed
    assert ("was ended and cleaned up" in said) is not killed


def test_a_word_shaped_like_a_key_is_taken_out_whole(tmp_path, monkeypatch):
    """A key not in the ladder's environment (the keychain's, say) is masked by its shape: the whole word
    goes, not its first twenty characters. The tokens are made up."""
    practice = load_practice(tmp_path, monkeypatch)
    for fake in ("Ab1" + "x" * 17 + "SECRETTAILpart9876543210", "sk-" + "a1B2" * 12):
        said = practice.mask(f"Authorization: Bearer {fake}")
        assert said == "Authorization: Bearer [removed: shaped like a key]", said


def test_contree_without_its_credentials_is_named_on_rungs_3_and_4(tmp_path, monkeypatch):
    """What sandbox.Contree says with a key but no project id (a stub SDK, nothing sent) is read as that,
    both said by the rung (4) and only in the log under a leaf that did not land (3)."""
    import types

    from graphene_map import sandbox

    practice = load_practice(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, "contree_sdk", types.SimpleNamespace(ContreeSync=None))
    monkeypatch.setenv("CONTREE_HOME", str(tmp_path / "no-contree"))
    monkeypatch.setenv("GRAPHENE_KEYCHAIN", "off")
    monkeypatch.setenv("NEBIUS_API_KEY", "fake")
    monkeypatch.delenv("NEBIUS_PROJECT_ID", raising=False)
    with pytest.raises(RuntimeError) as no:
        sandbox.choose("contree")
    said = f"RuntimeError: {no.value}"
    landed = f"the leaf did not land (it is open): run: 1 came back\n| the executor stopped: {said}"
    for text in (said, landed):
        assert practice.likely(text)[0] == "ConTree has no credentials: NEBIUS_PROJECT_ID is not set"


def test_a_rung_an_agents_shell_refused_is_not_recorded(tmp_path):
    """A refused rung ran nothing: `status` does not show it as failed, and a result already on record
    (the person's PASS) stays."""
    state = tmp_path / "state"
    state.mkdir()
    (state / ".made-by-the-practice-ladder").touch()
    passed = {"result": "PASS", "at": "2026-09-28 09:00", "seconds": 60.0, "dollars": 0.1}
    (state / "progress.json").write_text(json.dumps({"3": passed}))
    for n in ("1", "2", "3"):
        assert ladder(tmp_path, n, CLAUDECODE="1").returncode == 1
    assert json.loads((state / "progress.json").read_text()) == {"3": passed}
    status = ladder(tmp_path, "status").stdout
    assert " FAIL " not in status and "3. one leaf in a Sandbox" in status and " PASS " in status


def test_the_dry_run_and_the_live_ladder_never_share_a_state(tmp_path):
    """With one PRACTICE_STATE for both, the dry run removes nor writes nothing of the live ladder's (its
    ledger is real spend), and the live ladder reads nothing a dry run wrote."""
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "docker").write_text("#!/bin/sh\nexit 1\n")  # were it to climb, it stops at rung 3, fast
    (stub / "docker").chmod(0o755)
    path = f"{stub}{os.pathsep}{os.environ['PATH']}"
    assert ladder(tmp_path, "status").returncode == 0  # the live ladder makes its state
    state = tmp_path / "state"
    real = '{"at": 1, "tag": "access", "dollars": 0.37}\n'
    (state / "ledger.jsonl").write_text(real)
    for args in (["--dry"], ["--dry", "2"], ["--dry", "status"]):
        done = ladder(tmp_path, *args, PATH=path)
        assert done.returncode == 2 and "the live ladder's" in done.stdout, done.stdout + done.stderr
        assert (state / "ledger.jsonl").read_text() == real and not (state / "progress.json").exists()
    assert "bill so far $0.3700" in ladder(tmp_path, "status").stdout
    dry = {"PRACTICE_STATE": str(tmp_path / "dry-state")}
    assert ladder(tmp_path, "--dry", "2", PATH=path, **dry).returncode == 0
    for args in (["status"], ["2"]):  # and the live ladder refuses the dry run's
        done = ladder(tmp_path, *args, **dry)
        assert done.returncode == 2 and "the dry run's" in done.stdout, done.stdout + done.stderr
