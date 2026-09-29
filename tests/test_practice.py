"""docs/test/practice.sh, the ladder for the first hour with a key, climbed whole against the stand-ins: the
scripted fake Token Factory (tests/fake_tokenfactory.py, started by the ladder itself) and Docker in place of
ConTree, as tests/test_escape.py uses it. Only the live calls are new when the key comes, on the ladder's
own path: rung 6's arms are not arm_a.py or arm_bprime.py, which first meet the live service in the
evidence runs."""

import contextlib
import importlib.util
import inspect
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
    here = {"PRACTICE_STATE": str(tmp_path / "state"), "PRACTICE_WORK": str(tmp_path / "work"),
            "GRAPHENE_NIGHT_LEDGER": str(tmp_path / "night.jsonl")}  # never the real night's  # fmt: skip
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
    assert "(not arm_bprime.py): 2 of 2 leaves landed" in said and "a scripted stand-in" in said
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
        assert "runs rungs 2-7 only when the person started the session with GRAPHENE_AGENT_LIVE_USD set" in (
            " ".join(done.stdout.split()))
        assert f"    docs/test/practice.sh {n}\n" in done.stdout
        assert "most likely: a live rung is yours to run" in done.stdout
        assert not (tmp_path / "work").exists()  # nothing was built, nothing was run
        assert not (tmp_path / "night.jsonl").exists()  # and nothing was counted
    dry = ladder(tmp_path, "--dry", "2", CLAUDECODE="1",  # the dry run spends nothing and records no one
                 PRACTICE_STATE=str(tmp_path / "dry-state"))  # fmt: skip
    assert dry.returncode == 0 and "· PASS · rung 2 · " in dry.stdout, dry.stdout + dry.stderr


@pytest.mark.parametrize("n", ["2", "4"])
def test_under_the_persons_opening_an_agents_shell_climbs_a_live_rung(tmp_path, n):
    """GRAPHENE_AGENT_LIVE_USD, set here by the test as the person sets it before starting the session,
    lets an agent's shell climb: the rung runs (a leaf on Nemotron, the escape test in ConTree) and fails
    for want of a key, not for the mark. Nothing leaves the machine: no key, a proxy that answers nothing."""
    dead = {"HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}
    (tmp_path / "no-contree").mkdir()
    done = ladder(tmp_path, n, CLAUDECODE="1", CLAUDE_CODE_SESSION_ID="s", GRAPHENE_AGENT_LIVE_USD="10",
                  CONTREE_HOME=str(tmp_path / "no-contree"), **dead)  # fmt: skip
    said = done.stdout + done.stderr
    assert done.returncode == 1 and f"FAIL · rung {n} · " in done.stdout, said
    assert "an agent's mark" not in said and (tmp_path / "work").exists()  # it ran
    why = ("ConTree needs a key", "No module named 'contree_sdk'") if n == "4" else ("the leaf did not land",)
    assert any(w in said for w in why), said  # without the `sandbox` extra, the SDK's absence is said first
    assert "fake-key" not in said and json.loads((tmp_path / "state" / "progress.json").read_text())[n]


def test_under_the_opening_a_dry_rung_counts_every_call_in_a_night_of_its_own(tmp_path):
    """The dry run under the opening climbs the night's whole path against the fake: every call is reserved
    and settled, each row says practice, and none of it is on the real night's bill."""
    done = ladder(tmp_path, "--dry", "2", CLAUDECODE="1", GRAPHENE_AGENT_LIVE_USD="10")
    assert done.returncode == 0 and "· PASS · rung 2 · " in done.stdout, done.stdout + done.stderr
    calls = (tmp_path / "state" / "ledger.jsonl").read_text().splitlines()
    rows = [json.loads(r) for r in (tmp_path / "state" / "night.jsonl").read_text().splitlines()]
    settled = [r for r in rows if r["kind"] == "settle"]
    assert len(calls) >= 2 and len(settled) == len(calls) == sum(r["kind"] == "reserve" for r in rows)
    assert sum(r["dollars"] for r in settled) == pytest.approx(sum(json.loads(c)["dollars"] for c in calls))
    assert all(r["practice"] is True for r in rows) and all(json.loads(c)["practice"] for c in calls)
    assert not (tmp_path / "night.jsonl").exists()  # the night the ladder was handed: untouched
    text = (tmp_path / "state" / "night.jsonl").read_text()
    assert text.count("fake-key") == 0  # counted, never printed


def test_no_rung_starts_past_80_percent_of_the_nights_cap(tmp_path):
    """The night's bill does not reset on a rerun: at $8 of $10 spent or in flight, a rung runs nothing."""
    made = [{"kind": "reserve", "id": "a", "model": "m", "dollars": 3.0},
            {"kind": "settle", "id": "a", "model": "m", "dollars": 2.5},
            {"kind": "reserve", "id": "b", "model": "m", "dollars": 5.5}]  # fmt: skip
    (tmp_path / "night.jsonl").write_text("".join(json.dumps(r) + "\n" for r in made))
    done = ladder(tmp_path, "2", CLAUDECODE="1", GRAPHENE_AGENT_LIVE_USD="10")
    said = " ".join(done.stdout.split())
    assert done.returncode == 1 and "FAIL · rung 2 · " in said, said
    assert "the night has $2.5000 spent and $5.5000 in flight, at or past $8.00 (80% of its $10.00" in said
    assert "most likely: the night's cap" in said and "`docs/test/practice.sh night` shows the bill" in said
    assert not (tmp_path / "work").exists() and not (tmp_path / "state" / "progress.json").exists()


def test_night_prints_the_bill_ultra_first_with_the_sandboxes(tmp_path):
    tf = {"endpoint": "token factory"}
    made = [{"kind": "reserve", "id": "n", "model": "nvidia/Nano", "dollars": 0.2, **tf},
            {"kind": "settle", "id": "n", "model": "nvidia/Nano", "dollars": 0.5},
            {"kind": "reserve", "id": "u", "model": "nvidia/Ultra", "dollars": 0.3, **tf},
            {"kind": "settle", "id": "u", "model": "nvidia/Ultra", "dollars": 0.25},
            {"kind": "reserve", "id": "f", "model": "nvidia/Ultra", "dollars": 0.4, **tf},
            {"kind": "sandbox", "op": "run", "seconds": 60}, {"kind": "sandbox", "op": "read", "seconds": 30}]
    (tmp_path / "night.jsonl").write_text("".join(json.dumps(r) + "\n" for r in made))
    done = ladder(tmp_path, "night", GRAPHENE_AGENT_LIVE_USD="5")
    lines = done.stdout.splitlines()
    head = "the night's bill: $0.7500 spent, $0.4000 in flight, of a $5.00 cap; nothing new starts at $4.00"
    assert done.returncode == 0 and lines[0].startswith(head), lines
    assert lines[1:] == ["  nvidia/Ultra: 1 call, $0.2500", "  nvidia/Nano: 1 call, $0.5000",
                         "  in flight: 1 call, $0.4000 held at the worst case",
                         "  Sandboxes: 2 operations, 1.5 min, counted at $0 (price: unknown)"]  # fmt: skip


@pytest.mark.parametrize("boxed", [True, False])
def test_the_prototypes_practise_a_few_calls_each_against_the_stand_ins(tmp_path, boxed):
    """`practice.sh --dry prototypes`: cover, note and precheck on a fixed plan in a throwaway feeds, one
    PASS line each. From an agent's shell under the opening, every call is on the night's bill, as practice.
    With no sandbox (a docker that does not answer), precheck skips the proposed leaf's fork and says so."""
    if boxed and not docker_runs():
        pytest.skip("needs a running Docker (the sandbox stand-in)")
    more = {} if boxed else {"PATH": stub_docker(tmp_path)}
    done = ladder(tmp_path, "--dry", "prototypes", CLAUDECODE="1", GRAPHENE_AGENT_LIVE_USD="10", **more)
    said = done.stdout
    assert done.returncode == 0 and "· PASS · prototypes · " in said, said + done.stderr
    for name in ("cover", "note", "precheck"):
        assert f"·   {name}: PASS · " in said
    assert "your paragraph, in clauses: 3; the plan carries 2, no leaf carries 1" in said
    assert "places it on xmlfeed" in said
    assert "xmlfeed red, for the right reason; cents passes already" in said
    skipped = "rejects's check was not run: it runs only in a sandbox fork, and there is no Sandboxes"
    assert (skipped in said) is not boxed and ("rejects red" in said) is boxed
    calls = (tmp_path / "state" / "ledger.jsonl").read_text().splitlines()
    rows = [json.loads(r) for r in (tmp_path / "state" / "night.jsonl").read_text().splitlines()]
    assert len(calls) == sum(r["kind"] == "settle" for r in rows) == (5 if boxed else 4)
    assert all(r["practice"] for r in rows) and "next: `docs/test/practice.sh --dry night`" in said


def test_in_an_agents_shell_the_prototypes_need_the_opening(tmp_path):
    dead = {"HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}
    done = ladder(tmp_path, "prototypes", CLAUDECODE="1", **dead)
    assert done.returncode == 1 and "FAIL · prototypes · " in done.stdout, done.stdout + done.stderr
    assert "an agent's mark (CLAUDECODE)" in done.stdout
    assert "    docs/test/practice.sh prototypes\n" in done.stdout
    assert not (tmp_path / "work").exists()


def stub_docker(tmp_path: Path) -> str:
    """A PATH whose docker's daemon does not answer."""
    stub = tmp_path / "bin"
    stub.mkdir(exist_ok=True)
    (stub / "docker").write_text("#!/bin/sh\nexit 1\n")
    (stub / "docker").chmod(0o755)
    return f"{stub}{os.pathsep}{os.environ['PATH']}"


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


def test_rung_1_passes_on_token_factory_and_says_plainly_what_waits_for_sandboxes(tmp_path, monkeypatch):
    """Rung 1 as it ran live (2026-09-29): Token Factory answered, Sandboxes refused the project. Rung 1 is
    Token Factory's and passes; its line says the refusal and which rungs wait for it. A rung that meets
    the refusal later (3's leaf, 4's sandbox) reads as it, and a 401 next to it in rung 1's log is still
    read as the 401."""
    from datetime import date

    from graphene_map import sandbox

    practice = load_practice(tmp_path, monkeypatch)
    monkeypatch.setenv("CLAUDECODE", "1")  # rung 1 reads what the person ran today, and runs nothing
    refused = sandbox.FORBIDDEN.format(why=sandbox.NO_GRANT)
    calls = [{"model": m, "ok": True} for m in ("u", "s", "n")]
    report = {"key": True, "nvidia": [{}] * 4, "tool_calls": calls,
              "sandbox": {"ok": False, "refused": True, "said": refused}}  # fmt: skip
    (practice.STATE / "access.json").write_text(json.dumps(report))
    assert date.fromtimestamp((practice.STATE / "access.json").stat().st_mtime) == date.today()
    said = practice.access(practice.Rung(1, 0.25))
    assert said == ("Token Factory: 4 NVIDIA models, 3 tool calls as asked. Sandboxes: refused for this "
                    "project, so rungs 3, 4, 6 and 7 wait for access; rungs 2 and 5 do not need it")
    leaf = f"the leaf did not land (it is open): run: 1 came back\n| the executor stopped: {refused}"
    for text in (refused, leaf):
        means, then = practice.likely(text)
        assert means.startswith("this project may not use Sandboxes yet (ConTree's 403)"), means
        assert then.endswith("meanwhile `docs/test/practice.sh 5`, and rung 1 again once access is granted")
    means = practice.likely(f"Token Factory answered 401 to GET /models\n- {refused}")[0]
    assert means.startswith("Token Factory refused the key (401)"), means


def test_a_rung_whose_files_hold_the_key_fails_by_count_and_never_shows_it(tmp_path, monkeypatch, capsys):
    """What only a live run shows, checked on every rung: no file the rung wrote holds the key or the
    project. A rung that writes the key past mask() (as a bug would) fails with the count, and no line
    shows the key; a clean rung's line says no file holds it. The key is made up."""
    practice = load_practice(tmp_path, monkeypatch)
    key = "Kp1" + "z" * 30
    monkeypatch.setenv("NEBIUS_API_KEY", key)

    def leaky(r):
        (practice.STATE / "access.json").write_text(json.dumps({"said": f"Bearer {key}"}))
        return "done"

    monkeypatch.setitem(practice.RUNGS, 1, ("a leaky rung", 0.25, "1 min", leaky))
    assert practice.climb(1) == "FAIL"
    said = capsys.readouterr().out
    assert "a file this rung wrote holds the key or the project (counted: 1)" in said and key not in said
    assert "most likely: a secret got past the masking into a file the ladder wrote" in said
    (practice.STATE / "access.json").unlink()
    monkeypatch.setitem(practice.RUNGS, 1, ("a clean rung", 0.25, "1 min", lambda r: "done"))
    assert practice.climb(1) == "PASS"
    assert "· no file holds the key\n" in capsys.readouterr().out


def test_rung_4s_command_past_its_time_comes_back_as_exit_124_or_fails(tmp_path, monkeypatch):
    """ConTree's own time limit, live on rung 4: exit 124 soon after the limit and the next command runs;
    anything else fails, read as ConTree's limit acting unlike Docker's. Boxes stand in here; the dry climb
    runs it on Docker."""
    from types import SimpleNamespace

    from graphene_map import sandbox

    practice = load_practice(tmp_path, monkeypatch)
    r = practice.Rung(4, 0.05)

    def place(run):
        return SimpleNamespace(image="img-1", box=SimpleNamespace(run=run), run=lambda c: (0, ""))

    ok = practice.past_its_time(r, place(lambda *a: ("img-1", 124, sandbox.TIMED_OUT)))
    assert ok == "a command past its 5 s came back as exit 124 in 0 s, and the next one ran"

    def failed(*_):
        raise RuntimeError("Operation 1 has failed: killed")

    with pytest.raises(practice.Failed) as no:
        practice.past_its_time(r, place(failed))
    assert "did not come back as exit 124 within a minute: exit None" in str(no.value)
    assert practice.likely(str(no.value))[0].startswith("ConTree's own time limit ends an operation")


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


@pytest.mark.parametrize("landed", [0, 1])
def test_the_demo_rung_passes_only_when_a_leaf_landed(tmp_path, monkeypatch, capsys, landed):
    """Rung 7 with nemotron.sh and the replay stubbed: a demo that ran to the bill with nothing landed is
    a FAIL that says so, and a PASS says how many leaves landed. Nothing runs."""
    practice = load_practice(tmp_path, monkeypatch)
    monkeypatch.setattr(practice.Rung, "sh", lambda r, args, cwd, timeout=900, **more: (0, "bill: $0.01"))
    monkeypatch.setattr(practice, "leaves", lambda repo: {"one": "done" if landed else "open", "two": "open"})
    assert practice.climb(7) == ("PASS" if landed else "FAIL")
    said = capsys.readouterr().out
    if landed:
        assert "1 of 2 leaves landed" in said
    else:
        assert "nothing landed" in said and "the model did not finish the work" in said


def test_rung_6_says_its_arms_are_not_the_evidence_runs_harnesses(tmp_path, monkeypatch, capsys):
    """Rung 6 runs arm A as one Graphene leaf and B′ through `graphene run`, not arm_a.py or arm_bprime.py:
    its name and its PASS line say so. graphene is stubbed; nothing runs."""
    practice = load_practice(tmp_path, monkeypatch)
    (tmp_path / "paragraph.md").write_text("A stand-in paragraph for this test only.\n")
    monkeypatch.setattr(practice, "PARAGRAPH", tmp_path / "paragraph.md")
    monkeypatch.setattr(practice.Rung, "feeds", lambda r, name, recorder=None: (tmp_path / name, None))
    monkeypatch.setattr(practice.Rung, "propose", lambda r, repo, nodes: None)
    monkeypatch.setattr(practice.Rung, "graphene", lambda r, repo, *args, timeout=900: (0, "ok"))
    monkeypatch.setattr(practice, "leaves", lambda repo: {"arm-a": "done", "one": "done"})
    assert "arms A and B" not in practice.RUNGS[6][0]
    assert practice.climb(6) == "PASS"
    said = capsys.readouterr().out
    assert "arm A as one leaf (not arm_a.py)" in said and "B′ by `graphene run` (not arm_bprime.py)" in said


def test_practice_md_says_the_caps_are_token_factory_s_and_which_dry_rungs_need_docker(tmp_path, monkeypatch):
    """The caps bound only Token Factory's ledger, and Sandboxes are free in the beta by Nebius's own page,
    which it names with the day it was read; the dry rungs raising NO_DOCKER are the ones it names."""
    practice = load_practice(tmp_path, monkeypatch)
    said = " ".join((ROOT / "docs" / "test" / "PRACTICE.md").read_text().split())
    assert "anywhere" not in said
    assert "The caps are Token Factory's only; rung 4 calls no model" in said
    assert "are free in the beta" in said and "2026-09-29" in said
    assert "tokenfactory.nebius.com/sandboxes " in said  # the page that says so, as the index quoted it
    docker = [n for n, rung in practice.RUNGS.items() if "NO_DOCKER" in inspect.getsource(rung[3])]
    assert f"rungs {', '.join(map(str, docker[:-1]))} and {docker[-1]} need Docker running" in said
    assert f"${sum(r[1] for r in practice.RUNGS.values()):.2f} of Token Factory" in said
