#!/usr/bin/env python3
"""The practice ladder: the first hour with a Token Factory key, one rung at a time. Start it with
docs/test/practice.sh (docs/test/PRACTICE.md says what to type):

    practice.sh            the next rung not yet passed
    practice.sh N          rung N
    practice.sh status     every rung, pass or fail, and the bill so far
    practice.sh --dry      the whole ladder against the stand-ins: the scripted fake Token Factory
                           (tests/fake_tokenfactory.py) and Docker in place of ConTree (PRACTICE_DRY=1 too)

Each rung has its own spend cap (GRAPHENE_SPEND_CAP_USD, set for that rung only, on top of what the
ladder has spent; PRACTICE_CAP=<dollars> replaces it for one run), prints one PASS or FAIL line, the
bill so far from the ledger every Token Factory call is written to (GRAPHENE_LEDGER), how long it took,
and the next command. A failure says what it most likely means and what to try. Progress, the ledger,
each rung's log and the recordings are kept in .graphene/practice/ (git-ignored; .graphene/practice-dry/
for the dry run), and the task repos are built outside this repository, in ~/graphene-practice/
(~/graphene-practice-dry/). PRACTICE_STATE and PRACTICE_WORK move them.

Rung 6 reads feeds' sealed paragraph from docs/test/tasks/feeds/paragraph.md and passes it on; no line
and no log holds it (<the sealed paragraph of feeds> stands in its place), no command's output is shown on
that rung, and it stops at arm A's failure. The dry run never reads it: it passes a placeholder.

Live, only the person climbs: from a shell with an agent's mark, rungs 2-7 run nothing and say so (rung 1
prints the line to type with `!`). Ctrl-C stops a rung, cleans up, and says what is left and how to clean it.
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
from graphene_map import sandbox as S  # noqa: E402
from graphene_map.demo import KEY as KEY_SHAPED  # noqa: E402
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
ME = "docs/test/practice.sh" + (" --dry" if DRY else "")
TAG = "dry run, stand-ins · " if DRY else ""  # every line of the dry run says so
# what an agent's shell carries (plan.caller reads them): the person runs the ladder, so none is passed on
MARKS = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT", "CODEX_SESSION_ID",
         "CODEX_SANDBOX", "AI_AGENT", "GRAPHENE_AS", *P.AGENT_MARKS)  # fmt: skip
SECRETS = ("NEBIUS_API_KEY", "NEBIUS_PROJECT_ID")
NO_DOCKER = "Docker is not running here, and the dry run's sandbox is Docker: nothing was run"
FAKE = None  # the scripted Token Factory, in this process, for the dry run

# The practice leaf: nothing to do with any task's card. A new file, and a check that fails until it is there.
LEAF = {"id": "hello", "title": "a practice leaf: practice_hello.py", "scope": ["practice_hello.py"],
        "goal": "Create practice_hello.py holding exactly one line: VALUE = 42",
        "check": "python3 -c 'import practice_hello as m; assert m.VALUE == 42'"}  # fmt: skip


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def say(line: str = "") -> None:
    print(TAG + mask(line), flush=True)


def mask(text: str) -> str:
    """The key and the project, and anything shaped like a key, never reach a line or a log."""
    for name in SECRETS:
        value = os.environ.get(name) or ""
        if len(value) >= 6:
            text = text.replace(value, f"[{name}]")
    return KEY_SHAPED.sub("[removed: shaped like a key]", text)


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
        keep = ("GRAPHENE_KEYCHAIN",)  # a shell that turned the keychain off keeps it off (every test does)
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
                 f"uv run --frozen --extra sandbox python docs/test/access.py --out {rel(out)}")  # fmt: skip
        fresh = out.exists() and date.fromtimestamp(out.stat().st_mtime) == date.today()
        if not fresh:
            raise Failed(
                f"yours to type: in this Claude Code session, type\n    {typed}\nthen `! {ME} 1` again"
            )
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
    sandboxes = "works" if box.get("ok") else f"not yet ({box.get('said', 'not tried')}); rung 3 needs them"
    models = len(report.get("nvidia", []))
    return f"{models} NVIDIA models, {len(calls)} tool calls as asked; Sandboxes: {sandboxes}"


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
    return f"{said}; in {want}: {p.get('ops')} operations, {p.get('seconds')} s"


# The escape test's ways out of a leaf's scope that go through the sandbox (tests/test_escape.py has the
# rest, the tool's own refusals, which do not depend on where the leaf runs): each must fail in there.
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
    escaped = []
    try:  # a stop while the sandbox is being made cleans up too
        place = S.Sandbox(root, ["app.py", "tests/test_new.py"], box)
        for name, command in {**FAILS, **MADE, **dict.fromkeys(INS)}.items():
            code, out = place.run(command or name)
            r.note(f"[{'in' if command is None else name}] exit {code}: {out.strip()[-300:]}")
            if name in FAILS and code == 0 or name in MADE and "refused: this command changed" not in out:
                escaped.append(name)
            if command is None and code != 0:
                raise Failed(f"a write inside the scope failed in the sandbox: {name}: {last(out)}")
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
    return (f"{len(FAILS) + len(MADE)} ways out failed or were refused, {len(INS)} ways in came back; "
            f"{'docker' if DRY else 'contree'}: {box.ops} operations")  # fmt: skip


def recorded(r: Rung) -> str:
    """Rung 5: the practice leaf, recorded with `graphene demo --record`, and the recording replayed."""
    rec = STATE / "leaf.jsonl"
    repo, recorder = r.feeds("recorded", recorder=rec)
    try:
        said = one_leaf(r, repo, "nemotron")
    finally:
        os.killpg(recorder.pid, signal.SIGTERM)
        r.note(recorder.communicate(timeout=60)[0] or "")
    code, out = r.sh(["graphene", "demo", str(rec), "--once"], STATE, 120)
    shown = "a scripted stand-in" if DRY else "as it ran, live"
    top = out.strip().splitlines()[0] if out.strip() else ""
    if code or shown not in top or not re.search(r"hello\s+done", out):
        raise Failed(f"the replay does not end with the leaf done, shown as {shown!r}: {top or last(out)}")
    return f"{said}; the replay of {rec.name} ends with it done: {top}"


def arms(r: Rung) -> str:
    """Rung 6: one run of arm A (the paragraph to Nano as one leaf over the whole repo, no tree and no
    check) and one of arm B (Ultra proposes from the paragraph, the tree accepted as proposed, which is
    the winning directive's B′; Nano does the leaves in Sandboxes)."""
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
    said = (f"arm A: its leaf landed, ${a_cost:.4f}; arm B: {landed} of {len(b)} leaves landed, "
            f"${b_cost:.4f}; repos {repo_a.name}, {repo_b.name}")  # fmt: skip
    if not landed:
        raise Failed(f"a run ended with nothing landed: {said}")
    return said


def demo_run(r: Rung) -> str:
    """Rung 7: docs/proof/nemotron.sh, the demo run on feeds, recorded, and the recording replayed."""
    rec = STATE / "demo.jsonl"
    # live, `graphene init` puts the leaves in Sandboxes when ConTree is configured (rung 3 showed it is);
    # the dry run's init sees no ConTree SDK, so the Docker sandbox is named, to run the same path
    more = {"EXECUTOR": "nemotron --placement sandbox"} if DRY else {}
    if DRY and not docker_runs():
        raise Failed(NO_DOCKER)
    code, out = r.sh(["bash", str(ROOT / "docs" / "proof" / "nemotron.sh"), str(r.where("demo"))], ROOT, 3600,
                     RECORD=str(rec), **more)  # fmt: skip
    if code or "bill: $" not in out:
        raise Failed(f"nemotron.sh did not reach the bill (exit {code}): {last(out)}")
    back, shown = r.sh(["graphene", "demo", str(rec), "--once"], STATE, 120)
    if back:
        raise Failed(f"the recording does not replay: {last(shown)}")
    bills = [ln.strip() for ln in out.splitlines() if "bill: $" in ln]
    return f"the demo ran to the bill; {rel(rec)} replays (`graphene demo {rel(rec)}`)\n" + "\n".join(bills)


# number: (name, what it may spend in dollars at list price, how long it takes live, the rung)
RUNGS = {
    1: ("access to Token Factory", 0.25, "1 min", access),
    2: ("one leaf local on Nemotron", 0.50, "2-5 min", local),
    3: ("one leaf in a Sandbox", 0.50, "3-8 min", in_sandbox),
    4: ("the escape test in the Sandbox", 0.05, "2-5 min", escape),
    5: ("a recorded leaf, replayed", 0.50, "2-5 min", recorded),
    6: ("one run each of arms A and B on feeds", 3.00, "15-40 min", arms),
    7: ("the demo run, recorded", 3.00, "10-30 min", demo_run),
}
MEANS = [  # (what the log or the failure says, what it most likely means, what to try); the first match wins
    (r"ESCAPED",
     "a way out of the leaf's scope worked in the sandbox: containment does not hold there",
     "stop: run no leaf in a Sandbox until it is understood; rung-4.log has each command's exit"),
    (r"an agent's mark",
     "a live rung is yours to run: an agent's shell may not spend your key or be recorded as you",
     "type the line above in a terminal where no agent's mark is set"),
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
    (r"No module named 'contree_sdk'|ConTree is not configured \(SDK",
     "the ConTree SDK is not installed",
     "`uv sync --extra sandbox`, then the rung again"),
    (r"ConTree needs NEBIUS_API_KEY|ConTree is not configured",
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
    name, cap, _, rung = RUNGS[n]
    cap = float(os.environ.get("PRACTICE_CAP") or cap)
    r, before, began = Rung(n, cap), spent(), time.monotonic()
    say(f"rung {n}/7 · {name} · cap ${cap:.2f} · log {rel(r.log)}")
    signal.signal(signal.SIGINT, interrupted)
    try:
        mark = None if DRY or n == 1 else marked()  # rung 1 has its own way: the person types access.py
        if mark:
            raise Failed(f"an agent's mark ({mark}) is set in this shell, and a live rung spends on your key "
                         f"and is recorded as you: nothing was run. Type it yourself, in a terminal where "
                         f"no agent's mark is set:\n    {ME} {n}")  # fmt: skip
        said, result = rung(r), "PASS"
    except Failed as no:
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
        if not DRY and n in (3, 4, 6, 7):  # sandbox.Sandbox.halt: ConTree's operation is not cancelled
            said += "\nleft running, maybe: a ConTree operation already sent runs on to its own time limit"
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # the rung's record is written whole
    said, took = r.seal(said), time.monotonic() - began
    rows = progress() | {str(n): {"result": result, "at": time.strftime("%Y-%m-%d %H:%M"),
                                   "seconds": round(took, 1),
                                   "dollars": round(spent() - before, 6)}}  # fmt: skip
    PROGRESS.write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    say(
        f"{result} · rung {n} · {took:.1f} s · this rung ${spent() - before:.4f} · bill so far ${spent():.4f}"
    )
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
        f"bill so far ${spent():.4f} at list price, Token Factory only (Sandboxes are billed apart); "
        f"{rel(LEDGER)}"
    )


def scripted(body: dict) -> dict:
    """The dry run's Token Factory: the access check's tool call, a two-leaf plan from any paragraph, and
    for any leaf `practice_<id>.py` written and `done`. Nothing about any task's card is in it."""
    from fake_tokenfactory import call

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
        (STATE / MADE_BY).touch()
    if args == ["status"]:
        status()
        return 0
    if args and not (args[0].isdigit() and int(args[0]) in RUNGS):
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
        (STATE / MADE_BY).touch()
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
