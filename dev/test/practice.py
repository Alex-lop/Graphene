#!/usr/bin/env python3
"""The practice ladder: the first hour with a Token Factory key, one rung at a time. Start it with
dev/test/practice.sh (dev/test/PRACTICE.md says what to type):

    practice.sh            the next rung not yet passed
    practice.sh N          rung N
    practice.sh status     every rung, pass or fail, and the bill so far
    practice.sh night      the night's bill: every live call and Sandbox operation under the opening
    practice.sh prototypes cover, note and precheck, a few Nano calls each, on a fixed plan (not a rung)
    practice.sh --dry      the whole ladder against the stand-ins: the scripted fake Token Factory
                           (tests/fake_tokenfactory.py) and Docker in place of ConTree (PRACTICE_DRY=1 too)

Each rung has its own spend cap (GRAPHENE_SPEND_CAP_USD, set for that rung only, on top of what the
ladder has spent; PRACTICE_CAP=<dollars> replaces it for one run), prints one PASS or FAIL line, the
bill so far from the ledger every Token Factory call is written to (GRAPHENE_LEDGER), how long it took,
and the next command. A failure says what it most likely means and what to try. Progress, the ledger,
each rung's log and the recordings are kept in .graphene/practice/ (git-ignored; .graphene/practice-dry/
for the dry run), and the task repos are built outside this repository, in ~/graphene-practice/
(~/graphene-practice-dry/). PRACTICE_STATE and PRACTICE_WORK move them; the dry run and the live ladder
never share a state directory (each refuses the other's).

Rung 6 reads feeds' sealed paragraph from dev/test/tasks/feeds/paragraph.md and passes it on; no line
and no log holds it (<the sealed paragraph of feeds> stands in its place), no command's output is shown on
that rung, and it stops at arm A's failure. The dry run never reads it: it passes a placeholder.

Live, only the person climbs: from a shell with an agent's mark, rungs 2-7 run nothing and say so (rung 1
prints the line to type with `!`), unless the person started the agent's session with GRAPHENE_AGENT_LIVE_USD
set. That is the opening: the ladder, and every live call and Sandbox operation made while it is set, go
under the night's cap in one ledger (nemotron/night.py), on top of each rung's own cap. A rung does
not start past 90% of it; the dry run keeps a night's ledger of its own in its state directory. Ctrl-C
stops a rung, cleans up, and says what is left and how to clean it.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from graphene_map import plan as P  # noqa: E402
from graphene_map.nemotron import keys, night  # noqa: E402
from graphene_map.nemotron import sandbox as S  # noqa: E402
from graphene_map.nemotron import tokenfactory as tf  # noqa: E402
from graphene_map.store import Store  # noqa: E402

DRY = "--dry" in sys.argv or os.environ.get("PRACTICE_DRY") == "1"
# resolved: a relative PRACTICE_WORK would name a different place once a rung runs from the task's repo
STATE = Path(os.environ.get("PRACTICE_STATE") or ROOT / ".graphene" / ("practice-dry" if DRY else "practice"))
WORK = Path(os.environ.get("PRACTICE_WORK") or Path.home() / f"graphene-practice{'-dry' if DRY else ''}")
STATE, WORK = STATE.resolve(), WORK.resolve()
LEDGER = STATE / "ledger.jsonl"
PROGRESS = STATE / "progress.json"
PARAGRAPH = HERE / "tasks" / "feeds" / "paragraph.md"  # the sealer's: passed on, never printed or shown
SEALED = "<the sealed paragraph of feeds>"  # what a line or the log says in its place
MADE_BY = ".made-by-the-practice-ladder"  # in a state directory the ladder made: only such a one is removed
MODE = "dry" if DRY else "live"  # what MADE_BY holds: a dry run and the live ladder never share a state
ME = "dev/test/practice.sh" + (" --dry" if DRY else "")
TAG = "dry run, stand-ins · " if DRY else ""  # every line of the dry run says so
# what an agent's shell carries (plan.caller reads them): the person runs the ladder, so none is passed on
MARKS = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT", "CODEX_SESSION_ID",
         "CODEX_SANDBOX", "AI_AGENT", "GRAPHENE_AS", *P.AGENT_MARKS)  # fmt: skip
SECRETS = ("NEBIUS_API_KEY", "NEBIUS_PROJECT_ID")
NO_DOCKER = "Docker is not running here, and the dry run's sandbox is Docker: nothing was run"
NEED_SANDBOXES = "rungs 3, 4, 6 and 7 wait for access; rungs 2 and 5 do not need it"
FAKE = None  # the scripted Token Factory, in this process, for the dry run

# The practice leaf: nothing to do with any task's card. A new file, and a check that fails until it is there.
LEAF = {"id": "hello", "title": "a practice leaf: practice_hello.py", "scope": ["practice_hello.py"],
        "goal": "Create practice_hello.py holding exactly one line: VALUE = 42",
        "check": "python3 -c 'import practice_hello as m; assert m.VALUE == 42'"}  # fmt: skip


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def say(line: str = "") -> None:
    print(TAG + mask(line), flush=True)


# a word a line is cut into to be masked (what whitespace, a quote, a backtick or a bracket ends), and a
# path among them: at / or ~/, or given to a variable (GRAPHENE_LEDGER=/…, in the line rung 1 prints)
PIECES = re.compile(r"""([^\s'"`()]+)""")
PATH = re.compile(r"(\w+=)?~?/")


def secrets() -> list[tuple[str, str]]:
    """The key and the project by what they are, longest first: the environment's values as set and with a
    paste's whitespace stripped (as keys.find sends the key), and the keychain's key."""
    found = {(n, v) for n in SECRETS for v in (os.environ.get(n) or "", (os.environ.get(n) or "").strip())}
    found.add((SECRETS[0], keys.find() or ""))
    return sorted(((n, v) for n, v in found if len(v) >= 6), key=lambda nv: len(nv[1]), reverse=True)


def mask(text: str) -> str:
    """The key and the project never reach a line or a log: taken out by what they are (``secrets``),
    wherever they are. A word shaped like a key is taken out whole too, but not a path the ladder names
    (one that starts at / or ~/): a repository's name beside a session's uuid looks like base64, and the
    path and the command it is in are printed to be used as they are."""
    for name, value in secrets():
        text = text.replace(value, f"[{name}]")
    return PIECES.sub(lambda w: w[0] if PATH.match(w[0]) else tf.unkeyed(w[0]), text)


def counted(r: Rung) -> int:
    """How many times the key or the project is in a file this rung wrote or added to (its log, the ledger,
    the access report, the recordings): counted, never shown. Every line is masked on its way out; this is
    the check, live, that none got through."""
    values = {v for _, v in secrets()}  # what mask() takes out: the keychain's key, and the stripped one
    if not values:
        return 0
    found = re.compile("|".join(map(re.escape, sorted(values, key=len, reverse=True))))  # each once
    files = [r.log, LEDGER, PROGRESS, STATE / "access.json", STATE / "leaf.jsonl", STATE / "demo.jsonl"]
    texts = [p.read_text(encoding="utf-8", errors="replace") for p in files if p.exists()]
    return sum(len(found.findall(text)) for text in texts)


def spent() -> float:
    """The ladder's ledger in dollars at list price, read as tokenfactory.spent() reads it."""
    total = 0.0
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            try:
                total += float(json.loads(line).get("dollars") or 0)
            except (ValueError, AttributeError):
                continue
    return total


def docker_runs() -> bool:
    return (
        shutil.which("docker") is not None
        and subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    )


class Failed(Exception):
    """A rung's FAIL, with what was seen."""


class Refused(Failed):
    """A FAIL before anything ran (an agent's shell): said, and not recorded, so what is on record stays."""


def last(out: str, n: int = 1) -> str:
    lines = [ln.strip() for ln in out.strip().splitlines() if ln.strip()]
    return " / ".join(lines[-n:]) if lines else "(no output)"


class Rung:
    """One rung's run: its environment (its cap, the ledger, the stand-ins when dry), its log, its repos."""

    def __init__(self, n: int, cap: float):
        self.n, self.cap, self.sealed, self.made = n, cap, [], []  # sealed: text no line and no log holds
        self.killed = False  # a command that did not end when told to, and was killed where it stood
        self.log = STATE / f"rung-{n}.log"
        self.log.write_text("", encoding="utf-8")
        # a shell that turned the keychain off keeps it off (every test does); the person's opening, and the
        # night's ledger, reach every command the rung starts
        keep = ("GRAPHENE_KEYCHAIN", night.OPENING, night.LEDGER)
        ours = {k for k in os.environ if k.startswith("GRAPHENE_") and k not in keep}
        env = {k: v for k, v in os.environ.items() if k not in MARKS and k not in ours}
        env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"  # this graphene
        if DRY:
            env = {k: v for k, v in env.items() if not k.startswith(("NEBIUS_", "CONTREE_"))}
            env |= FAKE.env() | {"GRAPHENE_SANDBOX": "docker", "CONTREE_HOME": str(STATE / "no-contree")}
        self.env = env | {"GRAPHENE_LEDGER": str(LEDGER), "GRAPHENE_SPEND_CAP_USD": f"{spent() + cap:.4f}"}

    def seal(self, text: str) -> str:
        """The sealed paragraph, whole or any line of it, replaced by SEALED."""
        for sealed in self.sealed:
            for part in [sealed, *sorted({ln.strip() for ln in sealed.splitlines()}, key=len, reverse=True)]:
                if len(part) >= 12:  # ponytail: a shorter line, or a fragment of one, is not caught
                    text = text.replace(part, SEALED)
        return text

    def note(self, text: str) -> None:
        with self.log.open("a", encoding="utf-8") as f:
            f.write(mask(self.seal(text)).rstrip("\n") + "\n")

    def start(self, args: list[str], cwd: Path, **more: str) -> subprocess.Popen:
        shown = [SEALED if a in self.sealed else a for a in args]  # quoted by shlex, seal() would miss it
        self.note(f"$ {shlex.join(shown)}   (in {cwd})")
        return subprocess.Popen(args, cwd=cwd, env=self.env | more, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                start_new_session=True)  # fmt: skip

    def sh(self, args: list[str], cwd: Path, timeout: float = 900, **more: str) -> tuple[int, str]:
        """A command, its output kept in the rung's log (masked), stopped whole at the timeout."""
        proc = self.start(args, cwd, **more)
        try:
            out, _ = proc.communicate(timeout=timeout)
        except KeyboardInterrupt:  # its own session misses the Ctrl-C: pass it on, and leave nothing running
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.communicate(timeout=120)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                self.killed = True
            raise
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)  # graphene takes it as Ctrl-C: every executor is ended
            try:
                out, _ = proc.communicate(timeout=120)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                out, _ = proc.communicate()
            out, proc.returncode = f"{out or ''}\n(timed out: stopped after {timeout:g} s)", 124
        self.note(out or "")
        self.note(f"(exit {proc.returncode})")
        return proc.returncode, out or ""

    def graphene(self, repo: Path, *args: str, timeout: float = 900) -> tuple[int, str]:
        return self.sh(["graphene", *args], repo, timeout)

    def must(self, repo: Path, *args: str, timeout: float = 300) -> str:
        code, out = self.graphene(repo, *args, timeout=timeout)
        if code:  # with a sealed paragraph about, no output is shown: it is in the log, sealed there
            shown = " ".join(SEALED if a in self.sealed else a for a in args[:2])
            raise Failed(f"`graphene {shown}` failed: {'rung-6.log has why' if self.sealed else last(out)}")
        return out

    def where(self, name: str) -> Path:
        WORK.mkdir(parents=True, exist_ok=True)
        self.made.append(WORK / f"{self.n}-{name}-{time.strftime('%Y%m%d-%H%M%S')}")
        return self.made[-1]

    def feeds(self, name: str, recorder: Path | None = None) -> tuple[Path, subprocess.Popen | None]:
        """feeds, built fresh outside this repository, and `graphene init` for Nemotron; with ``recorder``,
        `graphene demo --record` started before init, as nemotron.sh starts it."""
        repo = self.where(name)
        code, out = self.sh([sys.executable, str(HERE / "make_task.py"), "feeds", str(repo)], WORK, 120)
        if code:
            raise Failed(f"make_task.py could not build feeds: {last(out)}")
        rec = self.start(["graphene", "demo", "--record", str(recorder)], repo) if recorder else None
        try:
            self.must(repo, "init", "--planner", "nemotron", "--executor", "nemotron", timeout=120)
        except BaseException:
            if rec:  # no recorder is left waiting for a store that never comes
                os.killpg(rec.pid, signal.SIGTERM)
                rec.communicate(timeout=60)
            raise
        return repo, rec

    def propose(self, repo: Path, nodes: list[dict]) -> None:
        tree = repo / ".graphene" / f"practice-{self.n}.json"
        tree.write_text(json.dumps({"nodes": nodes}), encoding="utf-8")
        self.must(repo, "plan", "propose", str(tree))
        tree.unlink()
        self.must(repo, "plan", "accept")


def leaves(repo: Path) -> dict[str, str]:
    with Store.open(repo) as store:
        return {n.id: n.state for n in P.leaves(P.nodes(store))}


def placed(repo: Path) -> str:
    """Where the executor `graphene init` wrote puts the leaves, in words."""
    with Store.open(repo) as store:
        boxed = (store.meta("executor") or "").endswith("sandbox")
    return ("in Docker, the stand-in" if DRY else "in Sandboxes") if boxed else "on this machine"


def one_leaf(r: Rung, repo: Path, executor: str) -> str:
    """The practice leaf proposed, accepted and run; PASS needs it landed."""
    r.propose(repo, [LEAF])
    _, out = r.graphene(repo, "run", "--parallel", "2", "--with", executor)
    state = leaves(repo)["hello"]
    if state != P.DONE:
        raise Failed(
            f"the leaf did not land (it is {state}): {last(out)}; `graphene node show hello` in {repo}"
        )
    return f"the leaf landed: {last(out)}"


# -- the rungs ---------------------------------------------------------------------------------------------


def access(r: Rung) -> str:
    """Rung 1: the key reaches Token Factory, every Nemotron size makes a tool call, and the sandbox smoke."""
    out = STATE / "access.json"
    args = [sys.executable, str(HERE / "access.py"), "--out", str(out)]
    if DRY:
        args += ["--sandbox", "docker" if docker_runs() else "none"]
    if not DRY and marked():  # an agent's shell: the classifier refuses it
        typed = (f"! GRAPHENE_LEDGER={rel(LEDGER)} GRAPHENE_SPEND_CAP_USD={r.env['GRAPHENE_SPEND_CAP_USD']} "
                 f"uv run --frozen --extra nemotron python dev/test/access.py --out {rel(out)}")  # fmt: skip
        fresh = out.exists() and date.fromtimestamp(out.stat().st_mtime) == date.today()
        if not fresh:  # a `!` line carries the session's marks: it spends only if the session was opened
            opened = "" if night.cap() is not None else (
                f"\n(it spends only in a session started with {night.OPENING} set; else run `{ME} 1` "
                "in a terminal of your own)")  # fmt: skip
            raise Refused(f"yours to type: in this Claude Code session, type\n    {typed}\n"
                          f"then `! {ME} 1` again{opened}")  # fmt: skip
        say(f"  reading what you ran today: {out}")
    else:
        code, said = r.sh(args, ROOT, 900)
        for line in said.strip().splitlines():
            say(f"  {line}")
    try:
        report = json.loads(out.read_text(encoding="utf-8"))
    except (OSError, ValueError) as no:
        raise Failed(f"access.py left no report ({no})") from None
    if not report.get("key"):
        raise Failed("NEBIUS_API_KEY is not set in the shell the ladder runs in; nothing was sent")
    if report.get("models_error"):
        raise Failed(report["models_error"])
    calls = report.get("tool_calls") or []
    if not calls:
        raise Failed("Token Factory lists no Nemotron model for this key")
    bad = [f"{t['model']}: {t.get('misfire')}" for t in calls if not t.get("ok")]
    if bad:
        raise Failed("a tool call misfired: " + "; ".join(bad))
    box = report.get("sandbox") or {}
    sandboxes = "work" if box.get("ok") else f"not yet ({box.get('said', 'not tried')}); rung 3 needs them"
    if box.get("refused"):  # rung 1 is Token Factory's: it passes, and says what waits for Sandboxes
        sandboxes = f"refused for this project, so {NEED_SANDBOXES}"
    models = len(report.get("nvidia", []))
    return f"Token Factory: {models} NVIDIA models, {len(calls)} tool calls as asked. Sandboxes: {sandboxes}"


def local(r: Rung) -> str:
    """Rung 2: one leaf in a local worktree, on Nemotron (the executor's smallest listed model)."""
    repo, _ = r.feeds("local")
    return one_leaf(r, repo, "nemotron")


def in_sandbox(r: Rung) -> str:
    """Rung 3: the same leaf in a Sandbox (ConTree live; Docker in the dry run)."""
    if DRY and not docker_runs():
        raise Failed(NO_DOCKER)
    repo, _ = r.feeds("sandbox")
    said = one_leaf(r, repo, "nemotron --placement sandbox")
    with Store.open(repo) as store:
        placed = [e["detail"] for e in store.node_log("hello", ("placement",))]
    want = "docker" if DRY else "contree"
    if not placed or placed[-1].get("box") != want:
        raise Failed(
            f"the leaf landed, but not in a {want} sandbox: {placed[-1:] or 'no placement on record'}"
        )
    p = placed[-1]
    if p.get("lost"):  # 2 Oct: rung 3 passed while every command it ran in ConTree came back as exit 1
        raise Failed(f"the leaf landed, but {p['lost']} of its commands in the {want} sandbox came back "
                     "without their list of files, so nothing they did was brought back: it did not really "
                     "run there")
    return f"{said}; in {want}: {p.get('ops')} operations, {p.get('seconds')} s"


# The escape test's ways out of a leaf's scope that go through the sandbox (tests/nemotron/test_escape.py has
# the rest, the tool's own refusals, which do not depend on where the leaf runs): each must fail in there.
FAILS = {
    "redirect": "echo gone > other.py",
    "sed -i": "sed -i s/1/2/ other.py",
    "python open": "python3 -c \"open('other.py', 'w').write('x = 4')\"",
    "mv": "mv other.py moved.py",
    "rm": "rm -f other.py tests/test_app.py",
    "git": "git checkout -- other.py; git reset --hard; git config user.name x",
    "symlink over": "ln -sf /etc/hostname other.py",
    "chmod": "chmod 666 other.py || chmod 777 . tests",
}
MADE = {"new file beside": "echo 'import os' > tests/conftest.py", "new link": "ln -s /etc/passwd leak"}
INS = ["sed -i s/hi/hello/ app.py", "printf 'def test_new():\\n    pass\\n' > tests/test_new.py"]  # fmt: skip
LIMIT = 5  # seconds rung 4 gives a `sleep 600` in the sandbox: it must come back as exit 124, soon after


def past_its_time(r: Rung, place) -> str:
    """A sandbox operation past its time comes back as exit 124 within a minute of its limit, and the
    sandbox takes the next command: what a leaf's hung command meets (the fake and Docker show it; this
    is ConTree's own time limit, live)."""
    began = time.monotonic()
    try:
        _, code, said = place.box.run(place.image, "sleep 600", {}, LIMIT)
    except Exception as no:  # noqa: BLE001 (what ConTree does here is the finding)
        code, said = None, f"{type(no).__name__}: {no}"
    took = time.monotonic() - began
    r.note(f"[past its time] exit {code} after {took:.1f} s: {said.strip()[-300:]}")
    if code != 124 or took > LIMIT + 60:
        raise Failed(f"a command past its {LIMIT} s did not come back as exit 124 within a minute: exit "
                     f"{code} after {took:.0f} s: {last(said)}")  # fmt: skip
    code, out = place.run("true")
    if code:
        raise Failed(f"after a command past its time, the sandbox did not take the next one: {last(out)}")
    return f"a command past its {LIMIT} s came back as exit 124 in {took:.0f} s, and the next one ran"


def escape(r: Rung) -> str:
    """Rung 4: every way out of the scope fails or is refused inside the sandbox, every way in works."""
    if DRY and not docker_runs():
        raise Failed(NO_DOCKER)
    root = r.where("escape")
    (root / "tests").mkdir(parents=True)
    files = {".gitignore": ".graphene/\n__pycache__/\n", "app.py": 'def greet():\n    return "hi"\n',
             "other.py": "x = 1\n", "tests/test_app.py": "import app\n"}  # fmt: skip
    for path, text in files.items():
        (root / path).write_text(text)
    for args in (["init", "-q"], ["-c", "user.name=p", "-c", "user.email=p@e", "add", "-A"],
                 ["-c", "user.name=p", "-c", "user.email=p@e", "commit", "-qm", "start"]):  # fmt: skip
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    box = S.choose("docker" if DRY else "contree")
    escaped, late = [], None
    try:  # a stop while the sandbox is being made cleans up too
        place = S.Sandbox(root, ["app.py", "tests/test_new.py"], box)
        for name, command in {**FAILS, **MADE, **dict.fromkeys(INS)}.items():
            code, out = place.run(command or name)
            r.note(f"[{'in' if command is None else name}] exit {code}: {out.strip()[-300:]}")
            if name in FAILS and code == 0 or name in MADE and "refused: this command changed" not in out:
                escaped.append(name)
            if command is None and code != 0:
                raise Failed(f"a write inside the scope failed in the sandbox: {name}: {last(out)}")
        try:  # said after the escape test's own verdict, which comes first
            timed = past_its_time(r, place)
        except Failed as no:
            timed, late = "", no
    finally:
        if hasattr(box, "forget"):  # every checkpoint the rung made, the sandbox's first ones too
            box.forget()
    kept = {"other.py": "x = 1\n", "tests/test_app.py": "import app\n"}
    escaped += [p for p, text in kept.items() if (root / p).read_text() != text]
    escaped += [
        p for p in ("moved.py", "tests/conftest.py", "leak") if (root / p).exists() or (root / p).is_symlink()
    ]
    if escaped:
        raise Failed(f"ESCAPED: a way out of the scope held in the sandbox: {', '.join(escaped)}")
    if "hello" not in (root / "app.py").read_text() or not (root / "tests/test_new.py").exists():
        raise Failed("the writes inside the scope did not come back from the sandbox")
    held = f"{len(FAILS) + len(MADE)} ways out failed or were refused, {len(INS)} ways in came back"
    if late:
        raise Failed(f"{held}; but {late}")
    return f"{held}; {timed}; {'docker' if DRY else 'contree'}: {box.ops} operations"


KEPT = ROOT / "tests" / "recordings"  # CI replays every recording here (tests/test_recordings.py)


def keep(rec: Path) -> str:
    """The command that puts ``rec`` where CI replays it, from the repository's root: the directory is not
    in the repository until a recording is, so the command makes it."""
    return f"mkdir -p {rel(KEPT)} && cp {rel(rec)} {rel(KEPT / 'first-light-rung-5.jsonl')}"


def recorded(r: Rung) -> str:
    """Rung 5: the practice leaf, recorded with `graphene demo --record`, the recording counted for what it
    must not hold (the key, the project, a home path, anything shaped like a key), and replayed."""
    rec = STATE / "leaf.jsonl"
    repo, recorder = r.feeds("recorded", recorder=rec)
    try:
        said = one_leaf(r, repo, "nemotron")
    finally:
        os.killpg(recorder.pid, signal.SIGTERM)
        r.note(recorder.communicate(timeout=60)[0] or "")
    from graphene_map import demo

    held = {what: n for what, n in demo.leaks(rec.read_text(encoding="utf-8")).items() if n}
    if held:  # counts only: the recording stays where it is, and is not to be shared
        counted = ", ".join(f"{k} ({n})" for k, n in held.items())
        raise Failed(f"the recording holds what it must not: {counted}; {rel(rec)} is not to be shared")
    code, out = r.sh(["graphene", "demo", str(rec), "--once"], STATE, 120)
    shown = "a scripted stand-in" if DRY else "as it ran, live"
    top = out.strip().splitlines()[0] if out.strip() else ""
    if code or shown not in top or not re.search(r"hello\s+done", out):
        raise Failed(f"the replay does not end with the leaf done, shown as {shown!r}: {top or last(out)}")
    kept = "" if DRY else f"\nCI replays it from {rel(KEPT)}: {keep(rec)}"
    clean = "it holds no key, project, home path or key-shaped word"
    return f"{said}; {clean}; its replay ends with it done: {top}{kept}"


def arms(r: Rung) -> str:
    """Rung 6: arm A as one Graphene leaf (the paragraph to Nano, scope the whole repo, check `true`)
    and B′ (Ultra proposes from the paragraph, the tree accepted as proposed; Nano does the leaves in
    Sandboxes), both through `graphene run`. Neither is the evidence runs' harness: arm_a.py (one
    `converse` session, no plan) and arm_bprime.py (bench.play_rounds, which reads the card's globs), and
    `evidence.py add`, are tested against the fake only and first meet the live service in the evidence
    runs."""
    if DRY:
        if not docker_runs():
            raise Failed(NO_DOCKER)
        paragraph = "A placeholder for the dry run: the sealed paragraph is never read by it."
    elif not PARAGRAPH.is_file():
        raise Failed(f"there is no sealed paragraph at {PARAGRAPH.relative_to(ROOT)} yet")
    else:
        paragraph = PARAGRAPH.read_text(encoding="utf-8").strip()
    r.sealed.append(paragraph)  # `graphene ask <paragraph>` is in the log as [the sealed paragraph]
    before = spent()
    repo_a, _ = r.feeds("arm-a")
    # Graphene needs a leaf to have a check; `true` holds nothing, which is arm A's "no check"
    r.propose(repo_a, [{"id": "arm-a", "title": "arm A: the paragraph, no tree", "goal": paragraph,
                        "scope": ["**"], "check": "true"}])  # fmt: skip
    code, _ = r.graphene(repo_a, "run", "--parallel", "2", "--with", "nemotron", timeout=3600)
    a, a_cost = leaves(repo_a)["arm-a"], spent() - before
    if code or a != P.DONE:  # arm B is not started: nothing more is spent on a rung that has failed
        raise Failed(f"arm A's leaf did not land (it is {a}, exit {code}), ${a_cost:.4f}, in {repo_a.name}; "
                     "arm B was not started; rung-6.log has the run")  # fmt: skip
    repo_b, _ = r.feeds("arm-b")
    r.must(repo_b, "ask", paragraph, "--with", "nemotron", timeout=1800)
    r.must(repo_b, "plan", "accept")
    r.graphene(repo_b, "run", "--parallel", "4", "--with", "nemotron --placement sandbox", timeout=3600)
    b, b_cost = leaves(repo_b), spent() - before - a_cost
    landed = sum(s == P.DONE for s in b.values())
    said = (f"arm A as one leaf (not arm_a.py): it landed, ${a_cost:.4f}; B′ by `graphene run` (not "
            f"arm_bprime.py): {landed} of {len(b)} leaves landed, ${b_cost:.4f}; "
            f"repos {repo_a.name}, {repo_b.name}")  # fmt: skip
    if not landed:
        raise Failed(f"a run ended with nothing landed: {said}")
    return said


def lost_lists(repo: Path) -> int:
    """How many sandbox commands of the run's leaves came back without their list of files: each attempt's
    placement row counts its own (executor._box), and the counts are added up. No store, nothing recorded."""
    if not (repo / ".graphene" / "graphene.db").exists():
        return 0
    with Store.open(repo) as store:
        return sum(int(row["detail"].get("lost") or 0)
                   for n in P.nodes(store) for row in store.node_log(n.id, ("placement",)))  # fmt: skip


def demo_run(r: Rung) -> str:
    """Rung 7: dev/proof/nemotron.sh, the demo run on feeds, recorded, and the recording replayed."""
    rec = STATE / "demo.jsonl"
    # live, `graphene init` puts the leaves in Sandboxes when ConTree is configured and does not refuse the
    # project, and on this machine when it does (the line says where); the dry run's init sees no ConTree
    # SDK, so the Docker sandbox is named, to run the same path
    more = {"EXECUTOR": "nemotron --placement sandbox"} if DRY else {}
    if DRY and not docker_runs():
        raise Failed(NO_DOCKER)
    repo = r.where("demo")
    code, out = r.sh(["bash", str(ROOT / "dev" / "proof" / "nemotron.sh"), str(repo)], ROOT, 3600,
                     RECORD=str(rec), **more)  # fmt: skip
    if code or "bill: $" not in out:
        raise Failed(f"nemotron.sh did not reach the bill (exit {code}): {last(out)}")
    states = leaves(repo)
    landed = sum(s == P.DONE for s in states.values())
    if not landed:
        raise Failed(f"the demo ran to the bill, and nothing landed: {len(states)} leaves, in {repo}")
    lost = lost_lists(repo)
    if lost:  # as rung 3: a leaf whose commands lost their lists did not really run in the sandbox
        raise Failed(f"the demo ran to the bill, but {lost} of its sandbox commands came back without their "
                     "list of files, so nothing they did was brought back")
    where = placed(repo)
    back, shown = r.sh(["graphene", "demo", str(rec), "--once"], STATE, 120)
    if back:
        raise Failed(f"the recording does not replay: {last(shown)}")
    bills = [ln.strip() for ln in out.splitlines() if "bill: $" in ln]
    ran = f"the demo ran to the bill, {landed} of {len(states)} leaves landed, {where}"
    return f"{ran}; {rel(rec)} replays (`graphene demo {rel(rec)}`)\n" + "\n".join(bills)


# The prototypes' practice: two leaves accepted and one left proposed on feeds, so precheck reads a red
# (xmlfeed's check fails with a bare AssertionError, which only Nano can explain), finds one that passes
# already (cents), and forks a sandbox for the proposed one; cover finds a clause no leaf carries; note
# routes two sentences. The words and the checks are fixed: nothing of any task's card is in them.
PROTO_PLAN = [
    {"id": "xmlfeed", "title": "an XML reader for the price feed",
     "goal": "Add ingest/xmlfeed.py, reading samples/prices.xml, and register it in ingest.READERS as 'xml'",
     "scope": ["ingest/xmlfeed.py", "ingest/__init__.py"],
     "check": "python3 -c \"import ingest; assert 'xml' in ingest.READERS\""},
    {"id": "cents", "title": "prices kept in integer cents", "goal": "Keep every price as integer cents",
     "scope": ["normalize/money.py"], "check": "python3 -m unittest -q tests.test_contract"},
]
PROTO_PROPOSED = [{"id": "rejects", "title": "rejected rows written aside",
                   "goal": "Write each row validation rejects to sink/rejects.py's file",
                   "scope": ["sink/rejects.py"], "check": "python3 -c 'import sink.rejects'"}]
PROTO_PARAGRAPH = ("Add an XML reader for the supplier feed and register it. Keep every price in integer "
                   "cents. Email the ops team when a feed is rejected.")
PROTO_NOTES = ["the XML reader must skip a row that has no price",
               "prices in the XML feed are already in cents"]  # fmt: skip


def calls() -> int:
    return len(LEDGER.read_text(encoding="utf-8").splitlines()) if LEDGER.exists() else 0


def prototypes(r: Rung) -> str:
    """Not a rung: the three prototypes, a few Nano calls each, on a fixed plan in a throwaway feeds. One
    PASS or FAIL line each; precheck's sandbox fork is skipped, and said so, with no Sandboxes access."""
    repo, _ = r.feeds("prototypes")
    r.propose(repo, PROTO_PLAN)
    tree, paragraph = repo / ".graphene" / "practice-proposed.json", repo / ".graphene" / "paragraph.txt"
    tree.write_text(json.dumps({"nodes": PROTO_PROPOSED}), encoding="utf-8")
    code, out = r.sh(["graphene", "plan", "propose", str(tree)], repo, 120, GRAPHENE_AS="agent:practice")
    if code:  # an agent's proposal stays proposed: a person's is open at once
        raise Failed(f"`graphene plan propose` failed: {last(out)}")
    paragraph.write_text(PROTO_PARAGRAPH, encoding="utf-8")
    boxed = docker_runs() if DRY else S.configured()
    ids = [] if boxed else [n["id"] for n in PROTO_PLAN]  # a proposed leaf's check runs only in a fork
    leaf = re.compile(rf"^[ !] ({'|'.join(n['id'] for n in PROTO_PLAN + PROTO_PROPOSED)})\s+(.+?)\s{{2,}}")
    steps = [("cover", [["plan", "cover", "--paragraph", str(paragraph)]], "your paragraph, in clauses"),
             ("note", [["plan", "note", n] for n in PROTO_NOTES], "take it:"),
             ("precheck", [["plan", "precheck", *ids]], "each check before any work")]  # fmt: skip
    lines, failed = [], []
    for name, commands, sign in steps:
        began, dollars = calls(), spent()
        done = [r.graphene(repo, *c, timeout=600) for c in commands]
        ok = all(code == 0 and sign in out for code, out in done)
        failed += [] if ok else [name]
        said = [ln.strip() for _, out in done for ln in out.splitlines() if "places it on" in ln
                or ln.startswith(sign) and name == "cover"]  # fmt: skip
        said += [f"{m[1]} {m[2]}" for _, out in done for m in map(leaf.match, out.splitlines()) if m]
        lines.append(f"{name}: {'PASS' if ok else 'FAIL'} · {calls() - began} Nano call(s), "
                     f"${spent() - dollars:.4f} · {'; '.join(said) or last(done[-1][1])}")  # fmt: skip
    if not boxed:
        lines.append(f"precheck: {PROTO_PROPOSED[0]['id']}'s check was not run: it runs only in a sandbox "
                     "fork, and there is no Sandboxes access here")  # fmt: skip
    if failed:
        raise Failed("\n".join([f"{', '.join(failed)} did not do what it says, in {repo}", *lines]))
    return "\n".join(lines)


# number: (name, what it may spend in dollars at list price, how long it takes live, the rung)
RUNGS = {
    1: ("access to Token Factory", 0.25, "1 min", access),
    2: ("one leaf local on Nemotron", 0.50, "2-5 min", local),
    3: ("one leaf in a Sandbox", 0.50, "3-8 min", in_sandbox),
    4: ("the escape test in the Sandbox", 0.05, "2-5 min", escape),
    5: ("a recorded leaf, replayed", 0.50, "2-5 min", recorded),
    6: ("arm A as one leaf, and B′, on feeds", 3.00, "15-40 min", arms),
    7: ("the demo run, recorded", 3.00, "10-30 min", demo_run),
}
STEPS = {"prototypes": ("the prototypes, a few Nano calls each", 0.05, "2-5 min", prototypes)}  # not rungs
MEANS = [  # (what the log or the failure says, what it most likely means, what to try); the first match wins
    (r"ESCAPED",
     "a way out of the leaf's scope worked in the sandbox: containment does not hold there",
     "stop: run no leaf in a Sandbox until it is understood; rung-4.log has each command's exit"),
    (r"the night has \$",
     "the night's cap (the lower of GRAPHENE_AGENT_LIVE_USD and $50), or its 90%, is reached: a rerun does "
     "not reset it",
     f"`{ME} night` shows the bill; nothing more is spent tonight"),
    (r"holds the key or the project",
     "a secret got past the masking into a file the ladder wrote",
     f"share nothing from {rel(STATE)}; find the write that did not go through mask() before any rung again"),
    (r"did not come back as exit 124",
     "ConTree's own time limit ends an operation differently from Docker's (exit 124, the image unchanged)",
     "rung-4.log's [past its time] line has what ConTree said; containment is in the line before it"),
    (r"an agent's mark",
     "a live rung is yours to run: an agent's shell may not spend your key or be recorded as you",
     "type the line above in a terminal where no agent's mark is set, or start the agent's session from a "
     "shell with GRAPHENE_AGENT_LIVE_USD set"),
    (r"yours to type",
     "the access check is yours to run: the session's classifier refuses it to an agent",
     "type the line above, with the '!'"),
    (r"NEBIUS_API_KEY is not set",
     "the shell the ladder runs in has no key",
     "export NEBIUS_API_KEY=… in ~/.zshenv, then open a new shell"),
    (r"answered 401|authenticate|invalid token",
     "Token Factory refused the key (401): wrong, expired, or pasted with a space",
     "make a new key at tokenfactory.nebius.com, put it in ~/.zshenv, open a new shell, rung 1"),
    (r"answered 403",
     "the key may not use this model or this project (403)",
     "check the project's access to Nemotron in the console"),
    (r"answered 404|not in Token Factory's list|lists no Nemotron|model.{0,40}not (found|exist)",
     "a model id is retired or renamed (404), or none is listed for this key",
     "rung 1 lists today's ids; `graphene init --planner nemotron --executor nemotron` writes them"),
    (r"answered 429|limits how fast",
     "Token Factory limited how fast this key may ask (429)",
     "wait a minute, then the rung again; the log says how often it asked"),
    (r"answered 5\d\d|Token Factory's side",
     "Token Factory's side failed (5xx)",
     "try again in a few minutes"),
    (r"spend cap is reached",
     "this rung's spend cap was reached",
     "read the ledger; if the spend was expected, PRACTICE_CAP=<dollars> raises this rung's cap once"),
    (r"Sandboxes refused this project",  # after Token Factory's own: rung 1's log holds both
     "this project may not use Sandboxes yet (ConTree's 403); access is asked for at "
     "tokenfactory.nebius.com/sandboxes/about",
     f"{NEED_SANDBOXES}: meanwhile `{ME} 5`, and rung 1 again once access is granted"),
    (r"No module named 'contree_sdk'|ConTree is not configured \(SDK",
     "the ConTree SDK is not installed",
     "`uv sync --extra nemotron`, then the rung again"),
    (r"ConTree needs (a key|NEBIUS_API_KEY)|ConTree is not configured",  # sandbox.Contree says the first
     "ConTree has no credentials: NEBIUS_PROJECT_ID is not set",
     "export NEBIUS_PROJECT_ID=… (the project's id, from the console) in ~/.zshenv, or `contree auth`"),
    (r"ImagePull|manifest unknown|pull access denied|failed to pull|image .{0,40}not found",
     "the sandbox's image (python:3.12) could not be pulled",
     "check that ConTree can pull python:3.12; the log has the service's words"),
    (r"setpriv|useradd|invalid user",
     "the image lacks setpriv or useradd, or its users differ from Docker's",
     "the sandbox needs bash, git, useradd and setpriv; the log has the command that failed"),
    (r"AttributeError|has no attribute|unexpected keyword|ContreeSync|contree_sdk",
     "the ConTree SDK and the service disagree (sandbox.py speaks contree-sdk 0.3.6)",
     "`uv pip show contree-sdk`; read the traceback in the log against sandbox.Contree"),
    (r"resolve host|name resolution|Network is unreachable|Connection refused|could not be reached",
     "no network on the way: from here to Token Factory, or inside the sandbox",
     "check this machine's network; in a sandbox, a check that installs packages has none"),
    (r"not JSON",
     "something that is not Token Factory answered (a proxy, a sign-in page)",
     "unset GRAPHENE_TOKENFACTORY_URL and any proxy, then the rung again"),
    (r"cut off|finish_reason.{0,5}length|max.tokens|truncat",
     "an answer or an output hit a cap: the model's max tokens, or the sandbox's output cap",
     "EXECUTOR='nemotron --max-tokens 8192' for rung 7; the log says which cap"),
    (r"timed out|ran out of time|no answer in",
     "something ran past its time: a model's answer, a sandbox command, or this rung's limit",
     "run the rung again; the log's last command is the slow one"),
    (r"Docker is not running",
     "the dry run's sandbox stand-in is Docker, and Docker is not up",
     "start Docker Desktop, wait for `docker info` to answer, then the dry run again"),
    (r"no sealed paragraph at",
     "feeds' paragraph has not been sealed yet",
     "the sealer writes it from the card; then rung 6"),
    (r"did not land|nothing landed",
     "the path ran, and the model did not finish the work",
     "`graphene node show <leaf>` in the repo the line names: a finding about the model, not the plumbing"),
]  # fmt: skip


def likely(text: str) -> tuple[str, str]:
    for pattern, means, then in MEANS:
        if re.search(pattern, text, re.IGNORECASE):
            return means, then
    return "not one of the first-contact failures this ladder knows", "read the log's last lines"


def progress() -> dict:
    try:
        return json.loads(PROGRESS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def marked() -> str | None:
    """The first agent's mark this shell carries, if any."""
    return next((m for m in MARKS if os.environ.get(m)), None)


def interrupted(signum, frame) -> None:
    """The first Ctrl-C stops the rung; one more while it cleans up is ignored, so the cleanup ends whole."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    raise KeyboardInterrupt


def climb(n: int) -> str:
    """One rung: PASS, FAIL or STOPPED, what it cost, the bill so far, how long, and the next command."""
    name, cap, _, rung = RUNGS[n] if n in RUNGS else STEPS[n]
    cap = float(os.environ.get("PRACTICE_CAP") or cap)
    r, before, began, refused = Rung(n, cap), spent(), time.monotonic(), False
    called = f"rung {n}" if n in RUNGS else str(n)
    say(f"{called}{'/7' if n in RUNGS else ''} · {name} · cap ${cap:.2f} · log {rel(r.log)}")
    signal.signal(signal.SIGINT, interrupted)
    try:
        # rung 1 has its own way (the person types access.py); the opening is the person's word, given
        # before the session started, that an agent may climb the rest under the night's cap
        mark = None if DRY or n == 1 or night.cap() is not None else marked()
        if mark:
            raise Refused(f"an agent's mark ({mark}) is set in this shell, and a live rung spends on your "
                          f"key and is recorded as you: nothing was run. An agent's shell runs rungs 2-7 "
                          f"only when the person started the session with {night.OPENING} set; or type it "
                          f"yourself, in a terminal where no agent's mark is set:\n    {ME} {n}")  # fmt: skip
        try:
            night.begin(f"rung {n}")
        except night.Refused as no:
            raise Refused(str(no)) from None
        if night.STARTED in os.environ:  # what the rung starts goes on under the cap
            r.env[night.STARTED] = os.environ[night.STARTED]
        said, result = rung(r), "PASS"
    except Failed as no:
        said, result, refused = str(no), "FAIL", isinstance(no, Refused)
    except S.Refused as no:  # a refusal says what it means and what to do, whole
        said, result = str(no), "FAIL"
    except Exception as no:  # an SDK's or a sandbox's own error is a result here
        said, result = f"{type(no).__name__}: {no}", "FAIL"
    except KeyboardInterrupt:
        left = [str(p) for p in r.made if p.exists()]
        said, result = "stopped by you (Ctrl-C): what it had started was ended and cleaned up", "STOPPED"
        if r.killed:
            said = ("stopped by you (Ctrl-C): a command did not end within 120 s and was killed, so what it "
                    "made may be left (a Docker sandbox's are named graphene-*)")  # fmt: skip
        said += (f"\nleft behind: this rung's repos\nto clean: {shlex.join(['rm', '-rf', *left])}" if left
                 else "\nleft behind: nothing")  # fmt: skip
        if not DRY and n in (1, 3, 4, 6, 7, "prototypes"):  # a ConTree operation sent is not cancelled
            said += "\nleft running, maybe: a ConTree operation already sent runs on to its own time limit"
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # the rung's record is written whole
    said, took = r.seal(said), time.monotonic() - began
    leaked = counted(r)
    if leaked and not refused:
        said, result = (f"{said}\na file this rung wrote holds the key or the project (counted: {leaked}): "
                        f"nothing in {rel(STATE)} is to be shared"), "FAIL"  # fmt: skip
    rows = progress() | {str(n): {"result": result, "at": time.strftime("%Y-%m-%d %H:%M"),
                                   "seconds": round(took, 1),
                                   "dollars": round(spent() - before, 6)}}  # fmt: skip
    if not refused:  # a rung that ran nothing leaves the record as it was
        PROGRESS.write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    clean = "" if leaked else " · no file holds the key"
    say(f"{result} · {called} · {took:.1f} s · this {'rung' if n in RUNGS else 'step'} "
        f"${spent() - before:.4f} · bill so far ${spent():.4f}{clean}")  # fmt: skip
    for line in said.splitlines():
        say(f"  {line}")
    if result == "FAIL":
        means, then = likely(said + "\n" + r.log.read_text(encoding="utf-8"))
        say(f"  most likely: {means}")
        say(f"  try: {then}")
        if n != 6:  # rung 6's log holds the planner's tree of the sealed paragraph: it stays in the file
            for line in r.log.read_text(encoding="utf-8").strip().splitlines()[-6:]:
                say(f"  | {line[:160]}")
    if result != "PASS":
        say(f"next: {ME} {n}")
    elif n not in RUNGS:
        say(f"next: `{ME} night` shows the night's bill")
    else:
        say(f"next: {ME} {n + 1}" if n < 7 else "next: the ladder is climbed; `" + ME + " status` shows it")
    if result != "STOPPED":  # stopped, the ladder is on its way out: one more Ctrl-C is ignored there too
        signal.signal(signal.SIGINT, signal.default_int_handler)
    return result


EXIT = {"PASS": 0, "FAIL": 1, "STOPPED": 130}


def status() -> None:
    rows = progress()
    for n, (name, cap, takes, _) in RUNGS.items():
        row = rows.get(str(n))
        seen = f"{row['result']} {row['at']}, {row['seconds']} s, ${row['dollars']:.4f}" if row else "not run"
        say(f"{n}. {name:40} {seen}  (cap ${cap:.2f}, live {takes})")
    say(
        f"bill so far ${spent():.4f} at list price, Token Factory only (Sandboxes: free in the beta, by "
        f"Nebius's page; each sandbox rung counts its operations); "
        f"{rel(LEDGER)}"
    )


def scripted(body: dict) -> dict:
    """The dry run's Token Factory: the access check's tool call, a two-leaf plan from any paragraph, for
    any leaf `practice_<id>.py` written and `done`, and the prototypes' readings of the fixed plan above
    (by the schema each asks for). Nothing about any task's card is in it."""
    from fake_tokenfactory import call

    schema = ((body.get("response_format") or {}).get("json_schema") or {}).get("name")
    if schema:
        clauses = [{"text": t, "leaf": leaf, "nearest": near} for t, leaf, near in (
            ("Add an XML reader for the supplier feed and register it", "xmlfeed", None),
            ("Keep every price in integer cents", "cents", None),
            ("Email the ops team when a feed is rejected", None, "rejects"))]  # fmt: skip
        return {"content": json.dumps({
            "clauses": {"clauses": clauses},
            "note": {"target": "xmlfeed", "scope_add": [], "scope_remove": [], "check": None,
                     "goal_add": True, "why": "it constrains the XML reader"},
            "precheck": {"verdict": "red-right-reason", "why": "the work is not done yet"},
        }[schema])}  # fmt: skip
    if any((t.get("function") or {}).get("name") == "get_current_weather" for t in body.get("tools") or []):
        return call("get_current_weather", city="Dallas", unit="fahrenheit")
    k = sum(1 for m in body["messages"] if m["role"] == "assistant")
    if "Ultra" in body["model"]:
        leaf = ("  ? {0}  [{0}]\n      practice_{0}.py, with VALUE = 42\n      scope: practice_{0}.py\n"
                "      check: python3 -c 'import practice_{0} as m; assert m.VALUE == 42'\n")  # fmt: skip
        plan = (
            "```plan\ngoal: two practice leaves\n- practice  [practice]\n"
            + leaf.format("one")
            + leaf.format("two")
        )
        return [call("list", path="."), {"content": plan + "```"}][min(k, 1)]
    first = body["messages"][1]["content"] if len(body["messages"]) > 1 else ""
    found = re.search(r"^(\S+) \(revision \d+\)", first, re.MULTILINE)
    path = f"practice_{(found.group(1) if found else 'leaf').replace('-', '_')}.py"
    steps = [call("write", path=path, content="VALUE = 42\n"), call("done")]
    return steps[k] if k < len(steps) else {"content": "nothing more"}


def main(argv: list[str]) -> int:
    global FAKE
    args = [a for a in argv if a != "--dry"]
    if not STATE.exists():
        STATE.mkdir(parents=True)
        (STATE / MADE_BY).write_text(MODE)
    if (STATE / MADE_BY).exists():  # an empty one is from before it said: the default paths tell them apart
        made = (STATE / MADE_BY).read_text().strip() or ("dry" if STATE.name == "practice-dry" else "live")
        if made != MODE:  # the live ledger is real spend; a dry row read as live is a stand-in shown as live
            say(f"{STATE} is {'the dry run' if made == 'dry' else 'the live ladder'}'s: nothing was read, "
                "removed or written; point PRACTICE_STATE at another directory")  # fmt: skip
            return 2
    if DRY and night.cap() is not None:  # the dry run's calls are a stand-in's: never on the night's bill
        os.environ[night.LEDGER] = str(STATE / "night.jsonl")
    if args == ["status"]:
        status()
        return 0
    if args == ["night"]:
        for line in night.bill():
            say(line)
        return 0
    step = args[0] if len(args) == 1 and args[0] in STEPS else None
    if args and not step and not (args[0].isdigit() and int(args[0]) in RUNGS):
        for line in __doc__.split("\n\n")[1].splitlines():
            say(line)
        return 2
    whole = DRY and not args  # the dry run climbs the whole ladder, from nothing
    if whole:
        if not (STATE / MADE_BY).exists() and any(STATE.iterdir()):
            say(f"{STATE} holds what the ladder did not make (it has no {MADE_BY}): nothing was removed; "
                "point PRACTICE_STATE at a new directory")  # fmt: skip
            return 2
        shutil.rmtree(STATE)
        STATE.mkdir(parents=True)
        (STATE / MADE_BY).write_text(MODE)
    if DRY:
        from fake_tokenfactory import Fake

        FAKE = Fake([scripted] * 100_000).__enter__()
    try:
        if whole:
            say(
                "the whole ladder, against the stand-ins; the Docker sandbox is "
                + ("up" if docker_runs() else "NOT up")
            )
            result = next((got for got in map(climb, RUNGS) if got != "PASS"), "PASS")  # the first not passed
            status()
            return EXIT[result]
        if step:
            return EXIT[climb(step)]
        rows = progress()
        n = (
            int(args[0])
            if args
            else next((n for n in RUNGS if rows.get(str(n), {}).get("result") != "PASS"), 0)
        )
        if not n:
            status()
            say("every rung has passed")
            return 0
        return EXIT[climb(n)]
    finally:
        if FAKE is not None:
            FAKE.__exit__(None, None, None)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
