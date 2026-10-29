"""`graphene run`: Graphene takes each ready node, hands it to an executor, and decides itself whether
it is done.

The executor is a command the person chooses (`claude -p …`, `codex exec …`, anything that takes a
prompt as its last argument). It is given one node's contract and nothing else. When its process
ends, however it ended, Graphene runs the same boundary as `graphene node done`: git says what
changed, the check says whether it works. Refused, the executor is sent back with the refusal; out
of attempts, the node is handed back with the reason and the run moves on. Nothing here trusts an
exit code or a closing message, and no vendor's ceiling on refused stops applies: the loop is ours.

Each leaf gets its own worktree on its own branch under .graphene/worktrees/, up to `--parallel N` at
once, so executors never see each other's half-written files and never write in the person's
checkout; a leaf that passes its boundary is committed there, by Graphene, and merged into the
checkout the run was started from when the merge is clean. `graphene run --here` is the old way: one
leaf at a time in the checkout itself, and nothing is committed. Leaves whose scopes overlap
are never in flight together, so two leaves cannot have written one file: what is left that can make
a merge unclean is the person's own work in the way, and that leaf waits for them, on its branch.
"""

from __future__ import annotations

import contextlib
import functools
import os
import re
import shlex
import shutil
import signal
import socket
import string
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from . import board as B
from . import extra, pick
from . import meter as M
from . import plan as P
from . import settings as S
from .plan import may_collide
from .record import seconds as _seconds
from .store import Store
from .views import elide, money

# An executor may edit files and run `graphene node …` and `graphene plan …` (its done, its release, a
# look at the plan), and nothing else unless the person says so with --with. Not `graphene run` or
# `graphene ask`: through their own --with, either would be any command at all. None of the person's MCP
# servers (`--strict-mcp-config`, as the planner), and Claude Code stops it at CAP_USD dollars CAP_UNIT.
CAP_USD, CAP_UNIT = 2, "an attempt"  # --max-budget-usd counts one invocation, not the resumed session
DEFAULT_WITH = (
    "claude -p --permission-mode acceptEdits --allowedTools 'Bash(graphene node *)' 'Bash(graphene plan *)' "
    "--output-format stream-json --verbose"  # the stream the meter reads: turns, tokens, tool calls, cost
    f" --max-budget-usd {CAP_USD} --strict-mcp-config"
)
ATTEMPTS = 3
WORST = 3.0  # dollars the night's ledger holds for a Claude Code or Codex attempt with no --max-budget-usd
CODEX = "codex exec --json --sandbox workspace-write"


def unchosen(who: str) -> P.Refused:
    """Nothing chosen and nothing named: refused before anything starts, since what would start runs
    with the person's permissions and spends their usage, and they never chose it."""
    return P.Refused(
        f"no {who} is chosen for this repo, so nothing was started: `graphene init` chooses one, or "
        "`--with claude` (or `--with codex`, `--with nemotron`, a command) names one for this command"
    )


def named(spec: str | None) -> str:
    """What --with names, as the command to start: `nemotron [options]` is Graphene's own executor on
    Token Factory; `claude` and `codex` alone are those agents as Graphene starts them by default, and
    `claude:MODEL` or `codex:MODEL` is the same with that model named in the CLI's own flag; `claude
    --max-budget-usd X` (or `claude:MODEL --max-budget-usd X`) is Claude Code's default with that cap an
    attempt, not CAP_USD; anything else is a command, as it is. Nothing named is refused (`unchosen`)."""
    spec = (spec or "").strip()
    if not spec:
        raise unchosen("executor")
    if spec.split(None, 1)[0] == "nemotron":
        return extra.need("executor").template(spec)
    word, _, rest = spec.partition(" ")
    cap = re.fullmatch(r"--max-budget-usd[ =]\s*(\d+(?:\.\d+)?)", rest.strip())
    if cap and word.partition(":")[0] == "claude":
        return named(word).replace(f"--max-budget-usd {CAP_USD} ", f"--max-budget-usd {cap[1]} ")
    name, _, model = spec.partition(":")
    if model and " " not in spec and name in ("claude", "codex"):
        return {"claude": f"{DEFAULT_WITH} --model", "codex": f"{CODEX} -m"}[name] + f" {shlex.quote(model)}"
    return {"claude": DEFAULT_WITH, "codex": CODEX}.get(spec, spec)


@dataclass(frozen=True)
class Forks:
    """What `graphene run` was told about forks: --forks (0: nothing), --first, and each --with as typed
    (fork k runs the k-th, round robin). A leaf's own number comes first (``forks_of``)."""

    n: int = 0
    first: bool = False
    withs: list[str] = field(default_factory=list)


def forks_of(store, node: P.Node, run: Forks | None) -> int:
    """How many forks a leaf is asked to run as: its own `forks:` line, else the run's --forks, else the
    setting, else one, and never fewer than the run's --with names; one for a run that never forks (``run``
    is None: `--here`, one checkout). A leaf with no check is asked in vain (its check is what keeps one:
    `validate` refuses the line, not the run's number): `run_node` runs it as one agent and says why."""
    if run is None:
        return 1
    return max(node.forks or run.n or S.forks(store), len(run.withs))


INTERPRETER = re.compile(r"(python|node|bash|sh|zsh|ruby|perl|deno|bun)[\d.]*")


def label(template: str, own: str = "graphene_map.nemotron.executor") -> str:
    """Who the run's executor is, in the plan's log: `run:<this>`. The command's name, never where it
    lives: the label is in the log a recording carries. A script run by an interpreter is named by the
    script (`python3 bin/executor.py` is `executor.py`); Graphene's own (``own``) is `nemotron`."""
    argv = shlex.split(template)
    if own in argv:
        return "nemotron"
    ran = INTERPRETER.fullmatch(Path(argv[0]).name)
    script = [a for a in argv[1:] if not a.startswith("-")] if ran else []
    return Path((script or argv)[0]).name
WORKTREES = "worktrees"  # under .graphene/, which git ignores: the run's own, one a leaf
PORT_BASE = 41000  # the first port a run hands out: PORT_BASE + slot * 10 + fork, moved up while taken
POLL = 0.5  # seconds between looks at a running executor: the person may have released its leaf
HEARTBEAT = 30.0  # seconds between the run's lines on what a metered leaf is doing: Alex's number
GRACE = 10  # seconds an executor is given to end after TERM, before KILL


class Ports:
    """A port of its own for every executor a run starts (PORT and GRAPHENE_PORT): PORT_BASE + slot * 10 for
    the leaf in a worker's slot, + k for its fork k, moved up while the port is taken by this run or by
    anything on this machine (bind-tested as it is handed out). Its check gets the same (``plan.port_env``),
    so a leaf that starts a server binds one no other leaf has."""

    def __init__(self) -> None:
        self.taken: set[int] = set()
        self.lock = threading.Lock()

    def take(self, slot: int, n: int = 1) -> list[int]:
        out: list[int] = []
        with self.lock:
            want = PORT_BASE + slot * 10
            while len(out) < n:
                if want not in self.taken and _free(want):
                    self.taken.add(want)
                    out.append(want)
                want += 1
        return out

    def give_back(self, ports: list[int]) -> None:
        with self.lock:
            self.taken.difference_update(ports)


def _free(port: int) -> bool:
    """Whether nothing on this machine holds ``port`` now (a bind, not a promise: the executor binds next)."""
    with socket.socket() as s:
        try:
            s.bind(("", port))
        except OSError:
            return False
    return True


class Stop:
    """What a Ctrl-C reaches (or a closed terminal, or a `kill`): the flag every worker reads, each
    executor this run started, and each check it runs. They run in sessions of their own, so the
    terminal's Ctrl-C reaches Graphene alone, which hands each leaf back before it stops its
    executor."""

    def __init__(self) -> None:
        self.event = threading.Event()
        self._procs: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

    def add(self, session: str, proc: subprocess.Popen) -> None:  # by its session: a fork's, or the hold's
        with self._lock:
            self._procs[session] = proc

    def remove(self, session: str) -> None:
        with self._lock:
            self._procs.pop(session, None)

    def halt(self) -> None:
        self.event.set()
        with self._lock:
            procs = list(self._procs.values())
        for proc in procs:
            _end(proc)
        P.end_checks()


def _end(proc: subprocess.Popen) -> None:
    """Stop an executor this run started, and whatever it started."""
    _end_group(proc.pid, lambda: proc.poll() is not None)


def _end_group(pid: int, gone: Callable[[], bool]) -> None:
    """TERM to a process group, then KILL, each given its time: nothing is handed on while the old
    executor may still write. A group that refuses the signal is waited for all the same: macOS
    refuses one (EPERM) whose last process is ending, and it is not gone until ``gone`` says so (CI
    caught a stop that returned while the executor was still ending, its exit code not yet known)."""
    for sig, grace in ((signal.SIGTERM, GRACE), (signal.SIGKILL, 5)):
        if gone():
            return
        with contextlib.suppress(OSError):
            os.killpg(pid, sig)
        until = time.monotonic() + grace
        while not gone() and time.monotonic() < until:
            time.sleep(0.05)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # someone else's process: alive
    return True


def _started(pid: int) -> str | None:
    """When the process with this pid began, to the second, or None when there is none. A pid is a
    number the system hands out again (a `.graphene` left `running` by a power cut names, after the
    reboot, whoever has that pid now); beside its start time it names one process. `ps` says it on
    macOS and Linux alike, in one spelling whatever the person's locale and zone. On Linux it is read
    from /proc instead: there `ps` works the time out from the boot time, which can move a second
    between two asks, and a live run then looked gone (CI caught it)."""
    try:  # field 22, the start in clock ticks since boot; the name (field 2) may hold spaces and ")"
        return "ticks " + Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        pass
    try:
        said = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                              env={**os.environ, "LC_ALL": "C", "TZ": "UTC"})  # fmt: skip
    except OSError:  # no ps (a bare container): no process can be told apart from another
        return None
    return said.stdout.strip() or None


def _still(pid: int, began: str | None) -> bool:
    """Is the process written down as ``pid``, begun at ``began``, still running? What was written
    with no start time is known by its pid alone."""
    return _started(pid) == began if began else _alive(pid)


def sweep(store, say: Callable[[str], None], root: Path | None = None) -> None:
    """A leaf still held by a run that is gone (killed, or its terminal closed) is handed back, so the
    next run does not find it `running` for ever: on 22 September a Ctrl-C left one so, and the
    leaves that needed it could not start. A run is known by the pid and start time it wrote beside
    each attempt, and only an attempt of the start that holds the leaf now counts: a live run that
    has just taken the leaf again has not written one yet. The dead run's executor, if it still
    works, is stopped first (TERM, then KILL, and waited for), and only while its pid still names
    the process that was started. The hand-back is not a person's: a live run's executor is not
    stopped for it. A parallel run that died outright (kill -9, Force Quit) left its executors
    working, and a leaf one of them finished is done in the run's worktree and nowhere here: it is
    parked as a stopped run parks it (``park``), committed on its branch and waiting in review. Either
    way the dead run's attempt is closed first (``_close``): nothing else settles its hold. A hold that
    forked had a tree a fork: each fork's work is kept on its ref first (``_keep_fork``: the dead run
    wrote none), then the tree goes, so none stays registered with nothing pointing at it. Last, every
    hold a dead run left in flight in its ledger is closed, whatever its leaf has become since: the
    executor left working may have ended the leaf itself (`done`, or `release`)."""
    for n in P.nodes(store, (P.RUNNING,)):
        if not (n.executor or "").startswith("run:"):
            continue
        mine = {n.session_id, *n.forked}  # the hold's sessions: its own, and each fork's
        rows = [e for e in store.node_log(n.id, ("attempt",)) if e["session_id"] in mine]
        this = rows[-1]["detail"] if rows else {}
        if this.get("run_pid"):
            gone = not _still(this["run_pid"], this.get("run_start"))
        else:  # started, and no attempt written yet: dead only if no parallel run holds the lock
            gone = P.RUN_TREE in (n.checkout or "") and not _locked(root)
        if not gone:
            continue
        for last in {e["session_id"]: e for e in rows}.values():  # each session's last attempt: its executor
            _close(last["detail"])
        for f in n.forked.values():  # the dead run wrote no ref: what each fork tried is kept, its tree goes
            tree = Path(f["tree"])
            with contextlib.suppress(P.Refused, OSError, subprocess.TimeoutExpired):  # a tree git cannot read
                if tree.is_dir():
                    paths = [p for p in P.changed_since(tree, n.base_sha, {}) if P.in_scope(p, n.scope)]
                    _keep_fork(tree, n.id, f["fork"], paths, n.base_sha or "HEAD")
            _git(Path(store.path).parent.parent, "worktree", "remove", "--force", str(tree), ok=True)
        try:
            P.release(store, n.id, P.Caller("graphene run", False, n.session_id),
                      "the run that held it ended without finishing it", stopped=True)  # fmt: skip
        except P.Refused:
            continue  # handed back or finished meanwhile
        say(f"{n.id} was left running by a run that ended; handed back, and it is ready again")
    for n in P.nodes(store, (P.DONE, P.REVIEW)):  # finished in a dead parallel run's worktree, never landed
        tree = Path(n.checkout or "")
        if P.RUN_TREE not in str(tree) + os.sep or not tree.is_dir():
            continue
        log = store.node_log(n.id, ("started", "attempt", "landed", "unlanded"))
        since = log[max((k for k, e in enumerate(log) if e["kind"] == "started"), default=0) :]
        if any(e["kind"] in ("landed", "unlanded") for e in since):
            continue
        run = next((e["detail"] for e in reversed(since) if e["kind"] == "attempt"), {})
        if run.get("run_pid") and not _still(run["run_pid"], run.get("run_start")):
            _close(run)
            park(store, tree, n, say)
    if not (night := extra.load("night")):
        return
    flying = functools.cache(night.flying)  # each ledger read once
    for e in store.node_log(None, ("attempt",)):
        this = e["detail"]
        hold = this.get("hold") or {}
        if not hold.get("id") or hold["id"] not in flying(hold.get("ledger")):
            continue  # no hold, or settled
        if this.get("run_pid") and not _still(this["run_pid"], this.get("run_start")):
            _close(this)


def _close(this: dict) -> None:
    """A dead run's attempt (``this``, its attempt row): its executor stopped if it still works, and only
    while its pid still names the process that was started; then its hold on the night settled, at what
    its log says read again through the meter, as the run would have settled it (``_settle``). A run
    killed outright (kill -9, Force Quit) left the hold in flight, and the night refused every run after.
    A log that cannot be read (the repo moved, its runs cleared) is no stream: the worst case."""
    pid, began = this.get("pid"), this.get("pid_start")
    if pid and began and _started(pid) == began:  # the dead run's executor, still working
        _end_group(pid, lambda p=pid: not _alive(p))
    hold, kind = this.get("hold"), this.get("meter")
    night = extra.load("night") if hold else None
    if not night:
        return
    meter = None
    if kind in M.ENDPOINT and this.get("log") and os.access(this["log"], os.R_OK):
        model = hold["model"].partition(":")[2]  # the ledger's "codex:<model>": the model it is priced at
        price = _listed().get if kind == "codex" else None
        meter = M.Meter(kind, this["attempt"], model, hold["paid"], price)
        Reader(Path(this["log"]), meter, lambda *_: None)(last=True)  # its rows were the dead run's to log
    _settle(night, hold, meter)


def run_holding(root: Path) -> int | None:
    """The pid of the `graphene run` alive in this repository, or None. Its lock names
    the run by pid and start time, so a pid the system has handed to another process since is no
    run: not one to wait for, nor one to interrupt."""
    try:
        first, _, began = (root / ".graphene" / "run.lock").read_text().partition("\n")
        pid = int(first)
    except (OSError, ValueError):
        return None
    return pid if _still(pid, began.strip()) else None


def _locked(root: Path | None) -> bool:
    """Is a `graphene run` other than this one alive in this repository?"""
    return root is not None and run_holding(root) not in (None, os.getpid())


def _waited(
    proc: subprocess.Popen, store, node_id: str, stop: Stop, each: Callable[[], None] | None = None,
    halted: Callable[[], bool] | None = None,
) -> int:
    """The executor's exit code. Meanwhile, a leaf the person released (or dropped) stops its
    executor: handing it back is the person's way to say stop. ``each`` runs every POLL; ``halted``
    says when this one is to stop on its own (a fork, once another is kept under --first)."""
    while True:
        try:
            return proc.wait(timeout=POLL)
        except subprocess.TimeoutExpired:
            pass
        if each:
            each()
        if stop.event.is_set() or (halted is not None and halted()) or _let_go(store, node_id):
            _end(proc)


class Reader:
    """An attempt's log, read as the executor writes it: each complete line goes to the meter, and each
    row the meter gives goes to ``logged``. A log that cannot be read, or a line the meter or the store
    trips on, is counted unread: the meter degrades, the attempt does not."""

    def __init__(self, path: Path, meter: M.Meter, logged: Callable[[str, dict], None]) -> None:
        self.path, self.meter, self.logged, self.offset, self.rest = path, meter, logged, 0, b""

    def __call__(self, last: bool = False) -> None:
        try:
            with open(self.path, "rb") as log:
                log.seek(self.offset)
                got = log.read()
        except OSError:
            self.meter.unread += 1
            return
        self.offset += len(got)
        *lines, self.rest = (self.rest + got).split(b"\n")
        if last:  # the process has ended: a last line with no newline is whole
            lines, self.rest = [*lines, self.rest], b""
        for line in lines:
            try:
                for kind, detail in self.meter.feed(line.decode("utf-8", "replace")):
                    self.logged(kind, detail)
            except Exception:
                self.meter.unread += 1


@functools.cache
def _listed() -> dict[str, tuple[float, float]]:
    """Token Factory's list prices, per prompt and per completion token, by model id: asked once a
    process, and empty when the Nemotron extra is not installed or the list cannot be read."""
    try:
        tf = extra.load("tokenfactory")
        return {m.id: (m.prompt, m.completion) for m in tf.models()} if tf else {}
    except Exception:
        return {}


def _let_go(store, node_id: str) -> bool:
    """Did a person hand this leaf back, or drop it, while its executor worked? Its own `done` or
    `release` is not that: it is left to end by itself, and say its last word."""
    state = P.get(store, node_id).state
    if state in (P.RUNNING, P.DONE, P.REVIEW):
        return False
    last = (store.node_log(node_id, ("released", "dropped")) or [None])[-1]
    return last is not None and (last["kind"] == "dropped" or bool(last["detail"].get("person")))


def graphene_shell(argv: list[str]) -> bool:
    """Is the executor Claude Code with a shell that runs Graphene alone: every `Bash(…)` it is allowed
    names graphene, as the default's two do? Then it is told so (``prompt_for``)."""
    allowed = [a for arg in argv for a in re.findall(r"Bash\(([^)]*)\)", arg)]
    return bool(allowed) and all(a.split()[:1] == ["graphene"] for a in allowed) and M.kind(argv) == "claude"


def prompt_for(
    node: P.Node,
    notes: list[str],
    refusal: str | None,
    why: list[str] | None = None,
    decided: list[str] = (),
    shell: bool = False,
    fork: tuple[str, int] | None = None,
    port: int | None = None,
) -> str:
    """What an executor is told: the person's notes, the contract, how to finish or hand back, and, as
    one of several forks (``fork``: its letter, how many), that it is one, and what decides among them;
    ``port``: the one the run gave it, to bind should it start a server."""
    lines = [
        *notes,
        *([""] if notes else []),
        "You are doing one leaf of a plan that a person and their agents share. `why` is the path from "
        "the plan's goal down to your leaf, in the person's words: it is what your work is for. The "
        "leaf is the whole of what you are asked to do.",
        "",
        P.contract(node, why, decided),
        "",
        "Read anything you need; write only inside the scope. When it is done, run "
        f"`graphene node done {node.id}`; if it refuses, it says what is wrong. If the leaf cannot be done "
        "as written, run the `release` command above and say why, naming with --wants each path outside "
        "the scope it needs. If your check cannot pass because a file another leaf already landed is wrong, "
        "do not work around it in your own files: run the release command with --wants naming that file "
        "and a why that names the fault, so the person can reopen that leaf. Do not start any other node.",
    ]
    if fork:
        b, n = fork
        lines += ["", f"This is fork {b} of {n}: {n} agents work on this leaf at once, each in its own copy; "
                      "when they end, Graphene keeps one by its check."]  # fmt: skip
    if port:
        lines += ["", f"If you start a server, bind $PORT ({port}): it is this leaf's own, no other leaf has "
                      "it, and the check runs with the same PORT."]  # fmt: skip
    if shell:  # ``graphene_shell``: a test runner of its own would be refused; `done` is the one it has
        lines += ["", "Your shell runs only `graphene node …` and `graphene plan …`: `graphene node done "
                  f"{node.id}` runs the check and prints why it failed; call it as often as you need."]
    if refusal:
        lines += ["", REFUSED, refusal]
    return "\n".join(lines)


REFUSED = "Your last attempt was not accepted:"  # the Nemotron executor reads what follows: why it stepped up


def _worst(argv: list[str]) -> float:
    """What one attempt may spend: the command's --max-budget-usd, else WORST. Claude Code stops after the
    turn that passes its cap, so an attempt may spend that turn more (b1.json: $0.0510 under $0.05)."""
    said = M.option(argv, "--max-budget-usd")
    try:
        return float(said) if said else WORST
    except ValueError:
        return WORST


def held(name: str, argv: list[str], paid: float, tag: str) -> tuple:
    """Under the opening, an attempt's worst case held on the night's ledger before it starts: (the
    night, the hold). The hold is None when the night is not open or ``name`` is no agent the meter
    knows. Past the cap it is refused in the ledger's words, and nothing starts."""
    night = extra.load("night") if name in M.ENDPOINT else None
    if not night or night.cap() is None:
        return night, None
    model = f"{name}:{M.model_in(argv) or ('default' if name == 'claude' else 'codex')}"
    # the ledger it is held in goes with it: it settles there, should it end after noon
    hold = {"model": model, "worst": _worst(argv), "paid": paid, "ledger": str(night.where())}
    try:
        hold["id"] = night.reserve(model, hold["worst"], tag, M.ENDPOINT[name], hold["ledger"])
    except night.Refused as no:
        raise P.Refused(str(no)) from None
    return night, hold


def _settle(night, hold: dict, meter: M.Meter | None) -> None:
    """A held attempt, settled on the night's ledger. At what its stream says only when the stream gave
    the whole figure: Claude Code's result was read, or every Codex turn that started completed. A Codex
    model with no list price settles at $0, its tokens alone. Anything else (no stream, a turn stopped or
    failed, a result never read) keeps the worst case held, as a Token Factory call stopped while out
    does (decision 129): it may have been spent. It settles in the ledger that holds it; an older hold
    names none, and settles in the night's now."""
    if meter is None:
        night.settle(hold["id"], hold["model"], hold["worst"], ledger=hold.get("ledger"))
        return
    used = {"prompt_tokens": meter.prompt_tokens, "completion_tokens": meter.completion_tokens}
    night.settle(hold["id"], hold["model"], _spent(meter, hold["worst"]), used, hold.get("ledger"))


def _spent(meter: M.Meter | None, worst: float, unpriced: float = 0.0) -> float:
    """What an attempt held at ``worst`` settles at (``_settle``). ``unpriced``: what a Codex attempt with
    no list price counts as: the night's ledger says its tokens (0), a cap on dollars cannot (``worst``)."""
    if meter is None:
        return worst
    whole = meter.reported is not None if meter.kind == "claude" else meter.begun == meter.turns
    if meter.kind == "codex" and not (meter.price and meter.price(meter.model)):
        return unpriced
    return meter.dollars if whole else worst


class Budget:
    """`graphene run --max-usd`: a cap on what the run starts, in this process. An attempt starts only
    while its worst case (``_worst``) and what is held and spent fit under it, and what is going is never
    stopped. Each attempt settles at what it spent (``_spent``), which is usually far under its worst case,
    so a start that does not fit while others hold their worst case waits for them: the run stops starting
    only when one could not fit with nothing held."""

    EPS = 1e-9  # dollars: a running sum of floats ($0.45 three times over) leaves 1e-16, which is no hold

    def __init__(self, cap: float, say: Callable[[str], None]) -> None:
        self.cap, self.say, self.spent, self.held, self.stopped = cap, say, 0.0, 0.0, False
        self.room = threading.Condition()

    def take(self, worst: float, stop: Stop | None = None) -> bool | None:
        """True: ``worst`` is held. False: it can never fit (said once), so nothing new starts. None: not
        now, though it would fit if what is going settled at nothing; ask again as each ends. With ``stop``
        it waits for that here (a worker's second attempt) and raises KeyboardInterrupt when the run stops."""
        with self.room:
            while True:
                if self.stopped:
                    return False
                if self.spent + self.held + worst <= self.cap + self.EPS:
                    self.held += worst
                    return True
                if self.spent + worst > self.cap + self.EPS:  # not even with nothing going
                    self.stopped = True
                    alone = worst > self.cap + self.EPS  # no attempt fits, however little is spent
                    why = f"; one attempt holds {money(worst)} until it ends: --max-usd {worst:g} starts one"
                    why *= alone
                    self.say(f"stopped starting: {money(self.spent)} spent, {money(self.held)} held, "
                             f"cap {money(self.cap)}{why}")  # fmt: skip
                    return False
                if stop is None:
                    return None
                if stop.event.is_set():
                    raise KeyboardInterrupt
                self.room.wait(1.0)

    def settle(self, worst: float, spent: float) -> None:
        with self.room:
            self.held = max(0.0, round(self.held - worst, 9))
            self.spent = round(self.spent + spent, 9)
            self.room.notify_all()


PROMPT, PROMPT_FILE = "{prompt}", "{prompt_file}"  # where a command takes the prompt, when not last


def command_for(template: str, prompt: str, session: str, again: bool, where: Path | None = None) -> list:
    """The executor's argv. Claude Code is told which session this is, so its hooks hold it to the
    node from its first call and a second attempt resumes with what the first one learned; any other
    executor gets the prompt (refusal included) as its last argument, fresh each time, unless the command
    says where it takes it: ``{prompt}`` is replaced by the prompt (`gemini -p {prompt}`), and
    ``{prompt_file}`` by the path of a file holding it (`aider --message-file {prompt_file}`), written in
    ``where`` (the run's own log directory, outside every scope; else the temp directory)."""
    argv = shlex.split(template)
    if argv and Path(argv[0]).name == "claude":  # `--`: a prompt that begins with a note's "-" is no option
        argv += [*(["--resume", session] if again else ["--session-id", session]), "--"]
    if not any(PROMPT in a or PROMPT_FILE in a for a in argv):
        return [*argv, prompt]
    path = ""
    if any(PROMPT_FILE in a for a in argv):
        where = where or Path(tempfile.gettempdir())
        where.mkdir(parents=True, exist_ok=True)
        path = str(where / f"prompt-{session[:8]}-{uuid.uuid4().hex[:6]}.txt")
        Path(path).write_text(prompt, encoding="utf-8")
    return [a.replace(PROMPT, prompt).replace(PROMPT_FILE, path) for a in argv]


def run_node(
    store,
    node_id: str,
    checkout: Path,
    template: str,
    attempts: int,
    say: Callable[[str], None],
    logs: Path | None,
    stop: Stop | None = None,
    budget: Budget | None = None,
    forks: Forks | None = None,
    ports: Ports | None = None,
    slot: int = 0,
) -> P.Node | None:
    """One leaf, start to boundary, in ``checkout``. Returns it when it ended done (or in review);
    None when it could not start, was handed back, or ran out of attempts. Interrupted (Ctrl-C, or
    ``stop``), the leaf is handed back before its executor is stopped, and the interruption goes on.
    ``budget``: the caller has taken its first attempt's worst case there; each attempt after is taken
    here, and each settles there when it ends. ``forks``: what the run was told about forks
    (``forks_of`` says how many this leaf runs as, ``_forked`` runs them); None never forks. ``ports``
    and ``slot``: the run's ports, and the worker's slot this leaf has, which name its executors' PORT."""
    session = str(uuid.uuid4())
    name = label(template)
    who = P.Caller(f"run:{name}", False, session)
    stop = stop or Stop()
    worst = _worst(shlex.split(template))
    owed = worst if budget else 0.0  # held on the budget for the attempt about to start
    try:
        node = P.start(store, node_id, who, checkout)
    except P.Refused as no:
        if owed:
            budget.settle(owed, 0.0)
        lines = (str(no) if "cannot start" in str(no) else f"{node_id} cannot start: {no}").splitlines()
        if "no node made" in lines[0]:  # whoever ran the run reads it, never an agent: the person's way out
            it, stand = ("it", "it stands") if "an uncommitted change" in lines[0] else ("them", "they stand")
            lines[-1] = f"  yours as {stand}? `graphene plan ack`, or commit {it}; else put {it} back"
        say("\n".join(lines))
        return None
    say(f"{node.id} started: {node.title}")
    n = forks_of(store, node, forks)
    if n > 1 and not node.check:  # the check is what keeps one: `validate` refuses the line, not the run's
        say(f"{node.id} runs as one agent: {n} forks need a check to keep one")
        n = 1
    ports = ports or Ports()
    given = ports.take(slot, n)  # a port an executor: the leaf's, or one a fork
    try:
        if n > 1:
            return _forked(store, node, checkout, template, attempts, say, logs, stop, budget, owed, who,
                           forks, n, given)  # fmt: skip
        return _attempts(store, node, checkout, template, attempts, say, logs, stop, budget, owed, session,
                         who, port=given[0]).get("node")  # fmt: skip
    except KeyboardInterrupt:
        with _no_interrupt():  # a second Ctrl-C must not leave the leaf running and its executor alive
            stop.halt()
            if P.get(store, node.id).state == P.RUNNING:
                P.release(store, node.id, who, STOPPED, stopped=True)
                say(f"{node.id} handed back: the run was stopped")
        raise
    finally:
        ports.give_back(given)


def _attempts(
    store,
    node: P.Node,
    tree: Path,
    template: str,
    attempts: int,
    say: Callable[[str], None],
    logs: Path | None,
    stop: Stop,
    budget: Budget | None,
    owed: float,
    session: str,
    who: P.Caller,
    fork: dict | None = None,
    won: threading.Event | None = None,
    port: int | None = None,
) -> dict:
    """One executor session's attempts at the leaf, in ``tree``: each told the last refusal, each held on
    the night's ledger and the budget (``owed``: what the caller holds for the first), each metered; then
    the boundary, unless the executor ended the leaf itself. The hold's own loop, or one fork's (``fork``:
    its `fork` rows' base: its letter, how many, its --with; ``won``: --first, set once a fork is kept,
    which stops this one). ``port``: the executor's own, in its PORT and its prompt. Returns how
    it ended: "done" with the leaf (done, or in review); "back", handed back by the executor or the person
    (said here for the hold); "refused", out of attempts (the hold is handed back here; a fork's why is
    returned); and for a fork "passed", "gave up", "failed" or "stopped" (under --first, or the leaf let go
    under it: the hold says by whom); with the attempts made and the dollars metered. Raises
    KeyboardInterrupt when the run was stopped, and P.Refused when the executor could not be started."""
    name = label(template)
    worst = _worst(shlex.split(template))
    refusal: str | None = None
    stamp = (node.started_at or P._now()).replace(":", "").replace("-", "")[:15]
    proc: subprocess.Popen | None = None
    hold: dict | None = None  # the attempt's on the night's ledger
    paid = 0.0  # what this hold's attempts settled: a resumed Claude Code reports the session's total
    spent: float | None = None  # ``paid`` once a meter has read a stream; None with no meter (pick: no step)
    shell = graphene_shell(shlex.split(template))
    due = 0.0  # when the terminal next says what the leaf is doing: HEARTBEAT after an attempt begins
    b, of = (fork["fork"], fork["of"]) if fork else (None, 0)
    lane = f"{node.id} fork {b}" if fork else node.id  # the leaf, or one fork of it, in the run's lines
    said = f"{lane}: " if fork else f"{lane} "
    tag = {"fork": b, "of": of} if fork else {}  # on a fork's attempt rows: which, of how many
    mark = {"fork": b} if fork else {}  # on a fork's every other row

    def each() -> None:  # every POLL of the attempt going (its read, meter and began are set below)
        nonlocal due
        if read:
            read()
        if metered and time.monotonic() >= due:  # one line, the id first: two lanes interleave readably
            due = time.monotonic() + HEARTBEAT
            # Nemotron has no stream to meter: it writes its own rows, read as the watch strip reads them
            m = vars(meter) if meter else M.going(store.node_log(node.id)) or {}
            turns, dollars = m.get("turns", 0), m.get("dollars", 0.0)
            used = f"{turns} turn{'s' * (turns != 1)} · " + (
                money(dollars) if m.get("priced", True) else "no list price"
            )
            if not (turns or m.get("prompt_tokens") or dollars):  # Codex: only as a turn ends
                used = "no usage yet"
            tries = f"attempt {attempt} · " if attempt > 1 else ""  # named past the first, as the pane does
            head = f"{lane} · {tries}{round(time.monotonic() - began)} s · "
            if used == "no usage yet" and not m.get("last"):  # a quiet leaf: one fact, not two nothings
                say(head + "still running, nothing read from it yet")
            else:
                head += f"{used} · "
                say(head + elide(m.get("last") or "nothing yet", max(80 - len(head), 20)))  # one row at 80

    try:
        for attempt in range(1, attempts + 1):
            if stop.event.is_set():  # stopped while the last attempt's check ran: nothing starts again
                raise KeyboardInterrupt
            if won is not None and won.is_set():  # --first: another fork is kept, so this one is stopped
                return {"how": "stopped", "why": LOST, "attempts": attempt - 1, "dollars": spent}
            if budget and not owed:
                if not budget.take(worst, stop):
                    why = f"the run's --max-usd stopped it before attempt {attempt}"
                    if fork:
                        return {"how": "refused", "why": why, "attempts": attempt - 1, "dollars": spent}
                    P.release(store, node.id, who, why)
                    say(f"{node.id} came back: {why}")
                    return {"how": "back"}
                owed = worst
                current = P.get(store, node.id)  # the wait can be a whole attempt of another leaf's
                if current.state != P.RUNNING:
                    if fork:  # the hold says by whom
                        return {"how": "stopped", "why": LET_GO, "attempts": attempt - 1, "dollars": spent}
                    say(f"{node.id} handed back while it waited for room under --max-usd")
                    ended = current.state in (P.DONE, P.REVIEW)
                    return {"how": "done", "node": current} if ended else {"how": "back"}
            if fork:  # working (again, after a refusal): the hooks hold it to `done` while its row says so
                store.log_node(node.id, P._now(), "fork", who.label, session, None,
                               {**fork, "state": "running", "why": ""})  # fmt: skip
            told = prompt_for(node, P.notes(store, node.id), refusal, P.trail(store, node),
                              B.decided(store, node), shell, (b, of) if fork else None, port)  # fmt: skip
            argv = command_for(template, told, session, attempt > 1, logs)
            # GRAPHENE_EXECUTOR: its own `done` is logged under the name the run's acts are (plan.caller)
            # GRAPHENE_TRY: which attempt this is, told rather than read back from the log, whose row
            # for it is written only once the process is running
            env = {**os.environ, "GRAPHENE_NODE": node.id, "GRAPHENE_ATTEMPT": session,
                   "GRAPHENE_TRY": str(attempt)}  # fmt: skip
            env["GRAPHENE_EXECUTOR"] = name
            if fork:  # which fork this is, of how many: its own `done` judges its own copy (plan.fork_of)
                env["GRAPHENE_FORK"], env["GRAPHENE_FORKS"] = b, str(of)
            if port:  # its own port, should it start a server: no other executor of this run has it
                env["PORT"] = env["GRAPHENE_PORT"] = str(port)
            if name != "nemotron":  # only Graphene's own executor calls Token Factory; the rest never look
                env["GRAPHENE_KEYCHAIN"] = "off"
            env.pop("GRAPHENE_AS", None)  # whoever started the run, the executor speaks for nobody
            log = None
            if logs is not None:  # streamed as it runs, so its tail can be read while it works
                logs.mkdir(parents=True, exist_ok=True)
                whose = f"{node.id}.{b}" if fork else node.id
                log = logs / f"{whose}-{stamp}-{session[:8]}-{attempt}.txt"
            try:  # under the opening: the attempt's worst case, held first
                night, hold = held(name, argv, paid, f"run: {lane} attempt {attempt}")
            except P.Refused as no:
                if fork:
                    return {"how": "failed", "why": str(no), "attempts": attempt - 1, "dollars": spent}
                P.release(store, node.id, who, str(no))
                say(f"{node.id} came back: {no}")
                return {"how": "back"}
            sink = open(log, "w", encoding="utf-8") if log else subprocess.DEVNULL  # noqa: SIM115
            try:
                proc = subprocess.Popen(
                    argv, cwd=tree, env=env, stdin=subprocess.DEVNULL, stdout=sink,
                    stderr=subprocess.STDOUT, start_new_session=True,
                )  # fmt: skip
            except OSError as no:  # the executor is not installed, or not executable: nothing ran
                if hold:
                    night.settle(hold["id"], hold["model"], 0.0, ledger=hold["ledger"])
                if fork:  # this fork failed; the leaf comes back once every fork has ended
                    raise P.Refused(f"the executor could not be started: {name}: {no.strerror}") from None
                P.release(store, node.id, who, f"the executor could not be started: {name}: {no.strerror}")
                raise P.Refused(
                    f"cannot run `{argv[0]}`: {no.strerror}. {node.id} was handed back untouched; name "
                    "another executor with --with"
                ) from None
            finally:
                if log:
                    sink.close()
            stop.add(session, proc)
            began = time.monotonic()
            due = began + HEARTBEAT
            kind = M.kind(argv) if log else None
            metered = kind or ("nemotron" if name == "nemotron" else None)  # Nemotron writes its own rows
            # the hold rides on the attempt: should this run die, the next one's sweep settles it (_close)
            store.log_node(node.id, P._now(), "attempt", who.label, session, None,
                           {"attempt": attempt, "pid": proc.pid, "pid_start": _started(proc.pid),
                            "run_pid": os.getpid(), "run_start": _started(os.getpid()),
                            "log": str(log) if log else None, "checkout": str(tree),
                            "meter": metered, "hold": hold, "port": port, **tag})  # fmt: skip
            meter = read = None
            if kind:  # what it writes is a stream the meter reads: read as it is written
                price = _listed().get if kind == "codex" else None
                meter = M.Meter(kind, attempt, M.model_in(argv), paid, price, str(tree))
                read = Reader(log, meter, lambda k, d: store.log_node(node.id, P._now(), k, who.label,
                                                                      session, None, d | mark))  # fmt: skip
            try:
                code = _waited(proc, store, node.id, stop, each, won.is_set if won is not None else None)
            finally:
                stop.remove(session)
                if read:
                    read(last=True)  # Claude Code's result is its last line
                    paid += meter.dollars
                    spent = paid
                if hold:
                    _settle(night, hold, meter)
                if owed:
                    budget.settle(owed, _spent(meter, owed, owed))
                    owed = 0.0
            # not an "attempt" row: readers take the last of those as the attempt going now
            store.log_node(node.id, P._now(), "ended", who.label, session, None,
                           {"attempt": attempt, "exit": code, "seconds": round(time.monotonic() - began, 1),
                            "meter": metered, "unread": meter.unread if meter else 0,
                            **({"fork": b} if fork else {})})  # fmt: skip
            if stop.event.is_set():
                raise KeyboardInterrupt
            if won is not None and won.is_set():  # --first: another fork is kept; this one was stopped for it
                return {"how": "stopped", "why": LOST, "attempts": attempt, "dollars": spent}
            capped = meter is not None and meter.result == "error_max_budget_usd"  # its result's subtype
            say(f"{said}attempt {attempt}: the executor "
                + ("stopped at its --max-budget-usd" if capped else f"ended (exit {code})"))  # fmt: skip
            current = P.get(store, node.id)
            if fork:
                if current.state != P.RUNNING:  # the leaf was let go under its forks: the hold says by whom
                    return {"how": "stopped", "why": LET_GO, "attempts": attempt, "dollars": spent}
                last = P.fork_row(store, current, b) or {}
                if last.get("state") == "gave up":
                    return {"how": "gave up", "why": last.get("why", ""), "attempts": attempt,
                            "wants": last.get("wants") or [], "dollars": spent}  # fmt: skip
                try:  # its own `done` may have passed, and it may have written since: judged as it stands
                    P.judge_fork(store, node.id, who, (session, {"fork": b, "tree": str(tree)}))
                    return {"how": "passed", "attempts": attempt, "dollars": spent}
                except P.Refused as no:
                    refusal = str(no)
            else:
                if current.state in (P.DONE, P.REVIEW):  # it ran `done` itself, and the boundary agreed
                    return {"how": "done", "node": current}
                if current.state != P.RUNNING:  # it handed the node back and said why, or the person did
                    _handed_back(store, current, say)
                    return {"how": "back"}
                try:
                    return {"how": "done", "node": P.finish(store, node.id, who)}
                except P.Refused as no:
                    if P.get(store, node.id).state != P.RUNNING:  # the person let it go while its check ran
                        say(f"{node.id} handed back while its check ran: {no}")
                        return {"how": "back"}
                    refusal = str(no)
            first, *rest = refusal.splitlines()
            paths = rest[0].strip() if rest and rest[0].startswith("  ") else ""  # the refusal's line 2
            told = first.rstrip(":") + (f" · {paths}" if paths else "")
            say(f"{said}attempt {attempt} refused: {told}")
        tries = f"{attempts} attempt{'s' if attempts != 1 else ''}"
        # the refusal for the person: its `graphene node release` step was the executor's to take
        told = "\n".join(ln for ln in refusal.splitlines() if "graphene node release" not in ln)
        crashed = f"; the executor itself exited {code}" if code else ""
        if capped:  # no crash: its result said the budget ran out
            crashed = ("; its last attempt stopped at its --max-budget-usd (a larger cap in --with, or a "
                       "smaller leaf)")
        why = f"{tries}, the last one refused: {told}{crashed}"
        if fork:
            say(f"{said}{tries}, the last one refused")
            return {"how": "refused", "why": why, "attempts": attempts, "dollars": spent}
        P.release(store, node.id, who, why)
        say(f"{node.id} came back after {tries}: `graphene node show {node.id}` says why")
        return {"how": "refused"}
    except KeyboardInterrupt:
        with _no_interrupt():  # a second Ctrl-C must not leave the executor alive
            if proc is not None:
                _end(proc)  # its own session never saw the terminal's Ctrl-C: it is stopped here
            if hold and hold.get("id"):  # stopped before its attempt's own settle: its worst case, once
                _settle(night, hold, None)
        raise
    finally:
        if owed:  # held, and no attempt ran on it (refused by the night, or not startable)
            budget.settle(owed, 0.0)


def _handed_back(store, node: P.Node, say: Callable[[str], None]) -> None:
    """The leaf was handed back under its executor, by the executor or by the person: said, with the
    offers a leaf that came back makes."""
    last = (store.node_log(node.id, ("released", "dropped")) or [{"detail": {}, "actor": ""}])[-1]
    person = last["detail"].get("person") or last.get("kind") == "dropped"
    who_said = last["actor"] if person else "the executor"
    say(f"{node.id} handed back by {who_said}: {last['detail'].get('why', node.state)}")
    for _key, what, command in P.offers(store, node):
        say(f"  {what}: `graphene {shlex.join(command)}`")
    if P.not_offered(store, node):
        say(f"  {P.not_offered(store, node)}")


LOST = "another fork's check passed first"  # a fork stopped under --first: Nemotron's words for it
STOPPED_FORK = "the run was stopped before this fork ended"  # a fork's last row under Ctrl-C or `:stop`
LET_GO = "the leaf was handed back while this fork worked"  # a fork's last row under the person's release


def _forked(store, node: P.Node, tree: Path, template: str, attempts: int, say: Callable[[str], None],
            logs: Path | None, stop: Stop, budget: Budget | None, owed: float, who: P.Caller, forks: Forks,
            n: int, ports: list[int] | None = None) -> P.Node | None:  # fmt: skip
    """The leaf run as ``n`` forks (the hold is taken: ``tree`` is its own worktree, ``who`` its session):
    a worktree a fork, cut from the hold's base beside the hold's tree; each fork the attempt loop
    (``_attempts``) in a thread of its own, with its own store connection, session, log, holds and meter,
    told which fork it is. The leaf's state stays the hold's. When every fork has ended (with --first, as
    soon as one has passed, the rest stopped), each fork's changes inside the scope are committed on
    refs/graphene/forks/<id>/<letter> (``_keep_fork``: kept after the leaf ends, for the record and `node
    diff --fork`), and the rule that keeps one (``pick.choose``: among the forks whose check passed, the
    one that passes the most of the others' tests, then the one that left its check's own files alone,
    the smaller, the cheaper, the sooner) names the fork to keep; its changes inside the scope are copied
    into the hold's tree, deletions too, and the leaf is finished there, once, under the run's own
    session, so it lands as any leaf does. None passed, it comes back with each fork's reason and the
    union of what they asked for. The fork worktrees go."""
    root = Path(store.path).parent.parent  # the repo: the fork trees go beside the hold's
    letters = string.ascii_lowercase[:n]
    withs = forks.withs or [None]  # fork k runs the k-th --with, round robin; none: the run's own
    specs = {b: withs[k % len(withs)] or label(template) for k, b in enumerate(letters)}
    templates = {b: named(w) if (w := withs[k % len(withs)]) else template for k, b in enumerate(letters)}
    sessions = {b: str(uuid.uuid4()) for b in letters}
    port = dict(zip(letters, ports or [], strict=False))  # a port a fork, when the run hands them out
    trees: dict[str, Path] = {}
    ends: dict[str, dict] = {}  # each fork's last row, as it ended
    entries: dict[str, pick.Entry] = {}  # each fork as the rule that keeps one reads it
    finished: list[str] = []  # the forks in the order they ended
    won = threading.Event() if forks.first else None
    order = threading.Lock()
    base = node.base_sha or "HEAD"  # the hold's: every fork is cut from it, and kept against it
    try:
        for b in letters:
            trees[b] = worktree_for(store, root, tree, node.id, fork=b, at=base)
        P.set_forked(store, node.id, {sessions[b]: {"fork": b, "tree": str(trees[b])} for b in letters})
        store.log_node(node.id, P._now(), "forked", who.label, who.session_id, None,
                       {"forks": list(letters), "of": n, "first": forks.first, "with": specs,
                        "sessions": sessions})  # fmt: skip
        say(f"{node.id} forked {n} ways: " + ", ".join(f"{b} {specs[b]}" for b in letters))
        # the budget: the caller holds the leaf's first attempt (``owed``), which is fork a's; each other
        # fork holds its own, and one that cannot fit does not start
        holds = {"a": owed}
        for b in letters[1:]:
            worst = _worst(shlex.split(templates[b]))
            if budget is None:
                holds[b] = 0.0
            elif budget.take(worst):
                holds[b] = worst
        if len(holds) < n:
            say(f"{len(holds)} of {n} forks started: --max-usd has room for {len(holds)}")
            for b in [b for b in letters if b not in holds]:  # on record, as the forks that ran are
                ends[b] = {"fork": b, "of": n, "with": specs[b], "state": "failed", "attempts": 0,
                           "why": "the run's --max-usd had no room for it"}  # fmt: skip
                entries[b] = pick.Entry(b, False, state="failed", why=ends[b]["why"])
                store.log_node(node.id, P._now(), "fork", who.label, sessions[b], None, ends[b])

        def one(b: str) -> None:
            with Store.open(root) as mine:  # a thread, a connection
                mine_who = P.Caller(f"run:{label(templates[b])}", False, sessions[b])
                row = {"fork": b, "of": n, "with": specs[b]}  # its `fork` rows' base: running, each attempt
                began = time.monotonic()
                try:
                    end = _attempts(mine, node, trees[b], templates[b], attempts, say, logs, stop, budget,
                                    holds[b], sessions[b], mine_who, row, won, port.get(b))  # fmt: skip
                except KeyboardInterrupt:  # the run was stopped: its row says so; the hold hands it back
                    end = {"how": "stopped", "why": STOPPED_FORK}
                except P.Refused as no:  # its executor would not start
                    end = {"how": "failed", "why": str(no)}
                how, why = end["how"], end.get("why", "")
                if how == "passed" and won is not None:
                    won.set()  # --first: the rest stop
                with order:
                    k = len(finished)
                    finished.append(b)
                verdict = P.fork_row(mine, node, b) or {}  # its check's own files it changed, when it passed
                paths, sha, lines, test_lines, tests = [], None, 0, 0, []
                try:  # git that fails here is this fork's failure, on its row: never the thread's end
                    paths = [p for p in P.changed_since(trees[b], base, {}) if P.in_scope(p, node.scope)]
                    if sha := _keep_fork(trees[b], node.id, b, paths, base):
                        lines, test_lines = pick.size(root, base, sha)
                        tests = _tests_of(root, node, sha, paths)
                except (P.Refused, RuntimeError) as no:  # pick's git raises RuntimeError
                    how, why = "failed", f"its work could not be kept: {no}"
                e = pick.Entry(b, how == "passed", sha, paths, lines, test_lines, tests,
                               verdict.get("check_touched") or [], end.get("dollars"),
                               round(time.monotonic() - began, 1), k, how, why)  # fmt: skip
                entries[b] = e
                detail = {**row, "state": how, "why": why, "paths": paths[: P.KEPT_PATHS], "lines": lines,
                          "test_lines": test_lines, "ref": fork_ref(node.id, b) if sha else None,
                          "dollars": e.dollars, "seconds": e.seconds, "attempts": end.get("attempts", 0),
                          **({"wants": end["wants"]} if end.get("wants") else {}),
                          **({"check_touched": e.touched_check} if e.touched_check else {})}  # fmt: skip
                mine.log_node(node.id, P._now(), "fork", mine_who.label, sessions[b], None, detail)
                ends[b] = detail
                told = {"passed": f"the check passed · {lines} lines", "gave up": f"gave up: {why}",
                        "stopped": f"stopped: {why}", "failed": f"failed: {why}"}.get(how)  # fmt: skip
                if told:  # a refused fork said each attempt as it went
                    say(f"{node.id} fork {b}: {told}")

        threads = [threading.Thread(target=one, args=(b,), daemon=True) for b in holds]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if stop.event.is_set():
            raise KeyboardInterrupt
        current = P.get(store, node.id)
        if current.state in (P.DONE, P.REVIEW):  # a person's own say-so meanwhile: as it stands
            return current
        if current.state != P.RUNNING:  # the person let it go under its forks
            _handed_back(store, current, say)
            return None
        if not any(e.passed for e in entries.values()):  # Nemotron's words: each fork's reason, as one
            why = f"no fork's check passed ({n} forks): " + "; ".join(
                f"fork {b}: {'handed it back: ' * (ends[b]['state'] == 'gave up')}{ends[b]['why']}"
                for b in letters if b in ends
            )
            wants = sorted({w for e in ends.values() for w in e.get("wants") or []})
            P.release(store, node.id, who, why, wants=wants or None)
            say(f"{node.id} came back: {why}")
            return None

        def agrees(i: str, j: str) -> bool:  # i's tests laid over j's tree, under the leaf's own check
            try:
                crossed = pick.overlay(root, entries[j].commit, entries[i].commit, entries[i].tests)
            except RuntimeError:  # the crossed tree could not be made: it passes nothing
                return False
            return P.run_check(node.check, tree, at=crossed)[0]

        choice = pick.choose(list(entries.values()), agrees)
        kept = choice.fork
        _copied(trees[kept], tree, entries[kept].paths)
        store.log_node(node.id, P._now(), "picked", who.label, who.session_id, None,
                       {"fork": kept, "of": n, "by": "graphene", "reason": choice.reason,
                        "table": choice.table})  # fmt: skip
        others = [str(entries[b].lines) for b in sorted(entries) if b != kept and entries[b].passed]
        sizes = "" if re.fullmatch(r"\d+ lines? against \d+", choice.reason) else (  # the reason said it
            f" · {entries[kept].lines} lines" + (f" against {', '.join(others)}" if others else ""))
        say(f"{node.id} kept {kept} of {n}: {choice.reason}{sizes}")
        try:  # the boundary, once, in the hold's tree: the check, `finished`, review or done, then it lands
            return P.finish(store, node.id, who)
        except P.Refused as no:
            if P.get(store, node.id).state != P.RUNNING:  # the person let it go while its check ran
                say(f"{node.id} handed back while its check ran: {no}")
                return None
            why = f"fork {kept}'s work was refused in the leaf's own tree: {no}"
            P.release(store, node.id, who, why)
            say(f"{node.id} came back: {why.splitlines()[0]}")
            return None
    finally:
        for t in trees.values():
            _git(tree, "worktree", "remove", "--force", str(t), ok=True)


def _copied(source: Path, into: Path, paths: list[str]) -> None:
    """A fork's changes inside the scope, put into the hold's tree as `fork_and_pick` puts a winner's:
    each path as the fork left it, and a path it deleted deleted."""
    for rel in paths:
        src, dst = source / rel, into / rel
        if dst.is_symlink() or dst.exists():
            dst.unlink()
        if src.is_symlink() or src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst, follow_symlinks=False)


def _tests_of(repo: Path, node: P.Node, commit: str, paths: list[str]) -> list[str]:
    """What a fork referees the other forks with (pick's agreement): of what it changed inside the scope
    (``paths``, committed as ``commit``), the files that look like tests and that its check runs in its
    tree. A file it deleted runs nowhere."""
    listed = _git(repo, "ls-tree", "-r", "-z", "--name-only", commit, ok=True).stdout.split("\0")[:-1]
    ran = {f for _, under in P.check_paths(node.check, listed, [node]) for f in under}
    return [p for p in paths if pick.is_test(p) and p in ran]


def fork_ref(node_id: str, letter: str) -> str:
    """Where a fork's work is kept once the leaf has ended: a hidden ref under the leaf's id."""
    return f"refs/graphene/forks/{node_id}/{letter}"


def _keep_fork(tree: Path, node_id: str, letter: str, paths: list[str], base: str) -> str | None:
    """A fork's changes inside the scope (``paths``), as a commit on the hold's ``base``, kept on the hidden
    ref ``fork_ref`` names after the leaf ends, so the record and `node diff --fork` can show what each
    fork tried. Read from its copy as it stands: an agent may `git commit` there itself, and its HEAD is
    then not the base. The commit; None when nothing inside the scope differs from the base."""
    if not paths:
        return None
    sparse = ("-c", "core.sparseCheckout=false")  # a leaf may write outside a sparse checkout's cone
    _git(tree, *sparse, "read-tree", base)  # its index is the base again: what differs is what it changed
    # update-index, not add: a path it committed and then deleted is in neither, and add refuses the pathspec
    _git(tree, *sparse, "update-index", "--add", "--remove", "--", *paths)
    if _git(tree, "diff", "--cached", "--quiet", base, ok=True).returncode == 0:
        return None
    made = _git(tree, "write-tree").stdout.strip()
    sha = _git(tree, *_ident(tree), "commit-tree", made, "-p", base, "-m",
               f"fork {letter} of {node_id}\n\nGraphene-Node: {node_id}\n").stdout.strip()  # fmt: skip
    _git(tree, "update-ref", fork_ref(node_id, letter), sha)
    return sha


STOPPED = "the run was stopped before this leaf was finished"  # by Ctrl-C, `:stop` or a closed terminal


NOTHING = "run: nothing started (graphene plan says what each leaf waits on)"  # a last line kept as no row


def summary(store, since: int, stopped: bool = False, yours: bool = True) -> str:
    """What a run did, in one line for the person, read from what the plan logged after entry
    ``since``: what it finished, what came back to them, what waits in review, and the two clocks (the
    agents' minutes and dollars, the person's acts and minutes). `graphene watch` shows this line when
    the run ends, so it is the run's last. The person's clock counts what led to the run too: their acts
    since the last run ended (its kept line) or the plan was archived, else since the plan began. Without
    ``yours`` (`graphene auto`'s runs) it is left out: what auto wrote as the person is no move of theirs."""
    whole = store.node_log()
    log = whole[since:]
    begun = max((k + 1 for k, e in enumerate(whole[:since])
                 if e["node_id"] == "*" and e["kind"] in ("run", "archived")), default=0)  # fmt: skip
    started = {e["node_id"] for e in log if e["kind"] == "started" and e["actor"].startswith("run:")}
    let_go = {e["node_id"]: e["detail"] for e in log if e["kind"] == "released"}
    ran = [n for n in P.order(P.nodes(store)) if n.id in started]  # in the plan's order, not the race's
    done = [n.id for n in ran if n.state == P.DONE]
    review = [n.id for n in ran if n.state == P.REVIEW]
    back = [n.id for n in ran if n.state == P.OPEN and n.id in let_go and not let_go[n.id].get("person")]
    handed = [i for i in back if let_go[i].get("why") == STOPPED]
    back = [i for i in back if i not in handed]
    freed = [n.id for n in ran if n.state == P.OPEN and let_go.get(n.id, {}).get("person")]

    said = [f"{len(done)} done"] if done else []
    said += [f"{len(back)} came back ({P._few(back)})"] if back else []
    said += [f"{len(review)} in review ({P._few(review)})"] if review else []
    said += [f"{P._few(handed)} handed back, ready again"] if handed else []
    said += [f"{P._few(freed)} released by you, ready again"] if freed else []
    cost = clocks(log, M.you(whole[begun:], P.person_name()))
    cost = cost if yours else cost.split(" · you: ")[0]
    if stopped:
        return "run stopped: " + (", ".join(said) or "nothing was finished") + cost
    if not ran:
        return NOTHING
    return "run: " + (", ".join(said) or "nothing finished") + cost


def clocks(log: list[dict], you: dict | None = None) -> str:
    """The run's two clocks and its width, from its own rows: " · agents 41m, $2.8700 at list price ·
    2 of 3 at once · you: 4 moves, 2m". With no usage row, the dollars are "no meter": nothing is invented.
    ``you``: the person's clock over more rows than the run's own (``summary``)."""
    agents, ran = M.agents(log, datetime.now(UTC)), M.width(log)
    you = you or M.you(log, P.person_name())
    took = f"{round(agents['seconds'] / 60)}m" if agents["seconds"] >= 60 else "<1m"
    spent, n = "no meter", agents["unpriced"]
    if any(e["kind"] == "usage" for e in log):
        spent = f"${agents['dollars']:.4f} at list price"
    if n:
        spent += f" + {f'{round(n / 1000)}k' if n >= 1000 else n} tokens with no list price"
    acts = f"{you['acts']} move{'s' * (you['acts'] != 1)}"
    wide = f" · {ran['most']} of {ran['lanes']} at once" if ran else ""
    return f" · agents {took}, {spent}{wide} · you: {acts}, {you['minutes']}m"


@contextlib.contextmanager
def _no_interrupt():
    """Ctrl-C (and Ctrl-\\, a hangup or a `kill`) held off while a stop is being cleaned up (main thread
    only; elsewhere it cannot land)."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    held = (signal.SIGINT, signal.SIGHUP, signal.SIGTERM, signal.SIGQUIT)
    was = {sig: signal.signal(sig, signal.SIG_IGN) for sig in held}
    try:
        yield
    finally:
        for sig, handler in was.items():
            signal.signal(sig, handler)


def _splits(template: str) -> None:
    try:
        if not shlex.split(template):
            raise ValueError("it is empty")
    except ValueError as no:
        raise P.Refused(f"--with {template!r} cannot be read as a command: {no}") from None


def _begins(template: str) -> None:
    """A run of Graphene's own executor, Claude Code or Codex is one new live thing under the night's cap
    (``night.begin``): its leaves go on under the cap once it has started, and it does not start past 90%
    of the cap. Asked after the sweep, so what a dead run held is settled first: asked before it, the
    dead run's holds refused the run, and its leaves stayed `running` with their executors at work."""
    if label(template) in ("nemotron", *M.ENDPOINT) and (night := extra.load("night")):
        try:
            night.begin("the run")
        except night.Refused as no:
            raise P.Refused(str(no)) from None


def leaves_of(store, ids: list[str] | None) -> list[str] | None:
    """A sub-goal named to `run --node` means the leaves under it."""
    if not ids:
        return ids
    everything = P.nodes(store)
    under = P.kids(everything)
    out = []
    for i in ids:
        out += [i] if not under.get(i) else [c.id for c in P.below(i, everything) if not under.get(c.id)]
    return out


def tail(path: str | Path | None, lines: int = 40) -> list[str]:
    """The last lines an executor wrote, read from its log while it grows."""
    if not path:
        return []
    try:
        with open(path, "rb") as log:
            log.seek(0, os.SEEK_END)
            log.seek(max(0, log.tell() - 64_000))
            text = log.read().decode("utf-8", "replace")
    except OSError:
        return []
    return text.splitlines()[-lines:]


def said_by(event: dict) -> str:
    """One tool call in a line: the tool and what it was pointed at."""
    given = event.get("input") or {}
    what = (
        event.get("file_path")
        or given.get("command")
        or given.get("pattern")
        or given.get("description")
        or ""
    )
    return f"{event['tool']} {' '.join(str(what).split())}"[:160].rstrip()


def live(store, node: P.Node, now: float | None = None) -> dict:
    """A running leaf as the person watches it: which executor, where, what it did last and how
    long ago. What it did is the meter's newest row for the attempt (`editing api.py`, or what it
    said), else the hooks' last tool call for its session, else its log's last line that is not the
    stream's JSON; the log's age, too, says when it last spoke. The attempt is its hold's
    (`meter.going`): a session that took the leaf after a run has none."""
    metered = M.going(store.node_log(node.id)) or {}
    log = metered.get("log")
    last = store.last_events(node.session_id) if node.session_id else []
    now = time.time() if now is None else now
    stamps = []
    if metered.get("last_at"):
        stamps.append(_seconds(metered["last_at"]))
    if last:
        stamps.append(_seconds(last[-1]["timestamp"]))
    if log and os.path.exists(log) and os.path.getmtime(log) <= now:  # a replay's log is written as it plays
        stamps.append(os.path.getmtime(log))
    if metered:
        stamps.append(_seconds(metered["started"]))
    return {
        "executor": node.executor,
        "checkout": node.checkout,
        "attempt": metered.get("attempt"),
        "log": log,
        # Nemotron writes the model's words as rows itself, and its log is its own narration ("sandbox made"):
        # never what the agent says
        "last": metered.get("last") or (said_by(last[-1]) if last else
                                        "" if str(node.executor or "").endswith("nemotron") else _spoke(log)),
        "idle": int(now - max(stamps)) if stamps else None,
    }


# the first line of what Graphene's own commands print into an executor's log (`node release`, `node done`,
# a refused `done` with its check's output, the next step): from there on the words are Graphene's, which a
# cockpit row would quote as what the agent says
OURS_SAID = re.compile(
    r"^(?:next: |\S+ handed back: |\S+ is (?:done|finished and waits for a sign-off|not done)\b)"
)


def _spoke(log: str | None) -> str:
    """The agent's last line in its log: from before the first line one of Graphene's own commands printed
    there (``OURS_SAID``: what follows is that command's, a failed check's output and the line naming whose
    plan it changed included), and not one of the stream's JSON events (stderr shares the file)."""
    lines = tail(log, 40)
    first = next((k for k, line in enumerate(lines) if OURS_SAID.match(line.strip())), len(lines))
    return next((line for line in reversed(lines[:first])
                 if not line.lstrip().startswith(("{", "(the plan of "))), "")  # fmt: skip


QUEUED = "queued"  # a leaf a `graphene run` asked for while another run held the repo: that run takes it


def hand_on(store, only: list[str] | None) -> list[str]:
    """`graphene run` while another run holds the repo: what this one would start is that one's to take,
    each leaf logged as asked for (``QUEUED``), however that run was started. Named (``only``), each open
    leaf of an agent's, one that came back too; else each ready leaf that did not come back. Their ids."""
    everything, who, named = P.nodes(store), P.caller(), leaves_of(store, only)
    if named:
        ids = [n.id for n in everything if n.id in named and n.state == P.OPEN and n.owner == P.AGENT]
    else:
        ids = [n.id for n in P.ready(everything, P.Caller("agent", False)) if not P.came_back(store, n)]
    now = P._now()  # one ask, one moment: the person's clock counts a move a moment (`meter.acts`)
    for node_id in ids:
        store.log_node(node_id, now, QUEUED, who.label, who.session_id, None, None)
    return ids


def _answered(store, node_id: str, after: int) -> str | None:
    """The person's last word on a leaf, when it is theirs and came after log row ``after``: they changed
    it (a widen is an edit), reopened it, or asked a run for it (``QUEUED``). A start or a hand-back since
    is the last word instead, and an act undone reads as never made, as ``P.let_go`` reads them."""
    log = [e for e in store.node_log(node_id, ("started", "released", "reopened", "edited", "undone", QUEUED))
           if e["actor"] != P.GRAPHENE]  # fmt: skip
    while log and log[-1]["kind"] == "undone":
        since = log.pop()["detail"].get("since")
        log = log if since is None else [e for e in log if e["id"] <= since]
    last = log[-1] if log else {"kind": None, "id": 0}
    return last["kind"] if last["kind"] in ("edited", "reopened", QUEUED) and last["id"] > after else None


def _newest(store, node_id: str | None = None) -> int:
    """The id of the newest row of a leaf's log, or of the whole log: what is done after it is new."""
    return (store.node_log(node_id) or [{"id": 0}])[-1]["id"]


def _came_back(store, only: list[str] | None, say: Callable[[str], None]) -> set[str]:
    """The leaves that came back: they wait on the person, so a run not told which leaves to run
    (``only``, `--node`, `r` on one) leaves them alone, and says how to run one again."""
    if only:
        return set()
    back = [n.id for n in P.order(P.nodes(store, (P.OPEN,))) if P.came_back(store, n)]
    if back:
        one = len(back) == 1
        say(f"{', '.join(back)} came back and wait{'s' if one else ''} on you: "
            f"`graphene run --node {back[0]}` runs {'it' if one else 'one'} again")  # fmt: skip
    return set(back)


def _red_first(store, target: Path, only: list[str] | None, say: Callable[[str], None],
               committed: bool) -> list:
    """Red first (precheck.py), once the run's own refusals have passed: the check of each leaf it can
    start now, ready for an agent with what it needs here (``only``: of those, what --node named, a
    sub-goal's leaves, a leaf that came back; else each that did not come back): one that waits on
    another would be judged before what it needs has landed. Run at the commit its leaves start from
    (``committed``: HEAD alone, which a leaf's worktree is cut from). A warning here, not a gate: if it
    breaks, the run goes on. Returns its rows, (leaf, verdict detail) each: `graphene auto` gates on them."""
    from . import precheck as pre

    ready = [n for n in P.ready(P.nodes(store), P.Caller("agent", False))
             if not P.not_here(store, n, target, committed)]  # fmt: skip
    ids = [n.id for n in ready if (n.id in only if only else not P.came_back(store, n))]
    if not ids:
        return []
    try:
        rows = pre.run(store, target, ids, committed=committed)
    except Exception as no:
        say(f"red first: not run: {' '.join(str(no).split())[:200]}")
        return []
    for line in pre.said(rows):
        say(line)
    return list(rows)


def _said_done(store, node: P.Node, say: Callable[[str], None]) -> None:
    from .node_record import _touched

    say(f"{node.id} is {'done' if node.state == P.DONE else 'finished; it waits for a sign-off'}")
    for line in _touched(store.node_log(node.id, ("finished",)), node.id):  # flagged, as node done says
        say(line)


@P.ctrl_c_on_hangup()
def run_plan(
    store,
    checkout: Path,
    template: str = DEFAULT_WITH,
    attempts: int = ATTEMPTS,
    only: list[str] | None = None,
    say: Callable[[str], None] = print,
    logs: Path | None = None,
    precheck: bool = False,
    max_usd: float | None = None,
) -> list[P.Node]:
    """Run every leaf an agent can reach, in order. Returns the ones that ended done (or in review).
    ``precheck``: red first, before the first leaf starts. ``max_usd``: a cap on what starts (``Budget``)."""
    _splits(template)
    sweep(store, say, store.path.parent.parent)  # the repo's root, where a parallel run's lock is
    _begins(template)
    only = leaves_of(store, only)
    if precheck:
        _red_first(store, checkout, only, say, committed=False)  # the leaves run in the checkout as it is
    finished: list[P.Node] = []
    tried: set[str] = _came_back(store, only, say)  # never tried: the person's to run again
    # The nodes that exist when the run starts are the run: a plan that grows while it is going (a
    # proposal accepted, or an executor adding nodes) does not make an unattended run unbounded.
    planned = {n.id for n in P.nodes(store) if n.state not in P.GONE}
    budget = Budget(max_usd, say) if max_usd is not None else None
    ports = Ports()
    while True:
        ready = [
            n
            for n in P.ready(P.nodes(store), P.Caller("agent", False))
            if n.id in planned and n.id not in tried and (not only or n.id in only)
        ]
        if not ready or (budget and not budget.take(_worst(shlex.split(template)))):
            return finished
        tried.add(ready[0].id)
        node = run_node(store, ready[0].id, checkout, template, attempts, say, logs, Stop(), budget, None,
                        ports)  # fmt: skip
        if node is not None:
            finished.append(node)
            _said_done(store, node, say)


# -- in parallel, a worktree a leaf ---------------------------------------------------------------------


def _git(where: Path, *args: str, ok: bool = False) -> subprocess.CompletedProcess:
    with P.worktree_lock(where) if args[:1] == ("worktree",) else contextlib.nullcontext():  # one at a time
        out = subprocess.run(["git", "-C", str(where), *args], capture_output=True, text=True)
    if out.returncode != 0 and not ok:
        raise P.Refused(
            f"git {' '.join(args[:3])} failed in {where}: {(out.stderr or out.stdout).strip()[:300]}"
        )
    return out


def worktree_for(
    store, root: Path, target: Path, node_id: str, fork: str | None = None, at: str = "HEAD"
) -> Path:
    """A fresh worktree for one leaf, on branch graphene/<id>, cut from where the target stands now
    (so it has everything that has landed). What an earlier run left under the same name goes. ``fork``:
    one fork's copy of the leaf, `<id>.<letter>`, detached at ``at`` (the hold's base): it lands nothing
    itself, so it is on no branch to delete."""
    path = root / ".graphene" / WORKTREES / (f"{node_id}.{fork}" if fork else node_id)
    _git(target, "worktree", "remove", "--force", str(path), ok=True)
    _git(target, "worktree", "prune", ok=True)
    shutil.rmtree(path, ignore_errors=True)  # a directory git has lost track of (a killed run) goes too
    on = ("--detach",) if fork else ("-B", f"graphene/{node_id}")
    _git(target, "worktree", "add", "--quiet", *on, str(path), at)
    # The person's hook settings are usually untracked (`graphene init` keeps them out of git through
    # .git/info/exclude, which every worktree shares), so a fresh worktree has none and the hooks
    # would not run there. Copied, they do; ignored by git, the copy is nobody's change.
    hooks = Path(".claude") / "settings.local.json"
    if (target / hooks).is_file() and _git(target, "check-ignore", "-q", str(hooks), ok=True).returncode == 0:
        (path / hooks).parent.mkdir(exist_ok=True)
        (path / hooks).write_bytes((target / hooks).read_bytes())
    P.mark_boundary(store, path)  # a path used before starts clean: nothing here was "changed between nodes"
    return path


def _ident(tree: Path) -> list[str]:
    return [] if _git(tree, "config", "user.email", ok=True).stdout.strip() else [
        "-c", "user.name=graphene", "-c", "user.email=graphene@localhost"]  # fmt: skip


def _commit(store, tree: Path, node: P.Node) -> list[str]:
    """The leaf's work, committed on its branch in its worktree, with its why in the message.
    Returns the paths its boundary said had changed. After the person's `node pick` the branch is that
    fork's commit already (``pick_fork``): nothing to commit, and what lands is what that fork changed."""
    last = (store.node_log(node.id, ("finished", "overruled", "picked")) or [{"kind": "", "detail": {}}])[-1]
    if last["kind"] == "picked":  # after the finish, so the person's: the rule's own comes before it
        return (P.fork_row(store, node, last["detail"]["fork"]) or {}).get("paths") or []
    entry = last["detail"]
    paths = entry.get("changed") or []
    why, notes = " > ".join(P.trail(store, node)), P.notes(store, node.id)
    message = f"{node.title}\n\n{node.goal or node.title}\n\n" + (f"Why: {why}\n" if why else "")
    message += f"Reopened: {notes[-1]}\n" if notes else ""
    sparse = ("-c", "core.sparseCheckout=false")  # a leaf may write outside a sparse checkout's cone
    _git(tree, *sparse, "add", "-A", "--", *(paths if paths and not entry.get("more_changed") else ["."]))
    if _git(tree, "diff", "--cached", "--quiet", ok=True).returncode != 0:  # else it committed itself
        _git(tree, *_ident(tree), "commit", "-q", "--no-verify", "-m", f"{message}Graphene-Node: {node.id}\n")
    return paths


def _merged(store, node: P.Node) -> str:
    """The merge's message: the leaf, then the check that proved it (and that it passed at the base too,
    where it proved nothing), who did it in how many attempts for how much, and, landed again after a
    reopen, the person's last note."""
    from .node_record import _hold  # the rows of its last hold: this run's attempts

    held = _hold(store.node_log(node.id))
    notes, tries, lines = P.notes(store, node.id), M.attempts(held), []
    picked = [e["detail"] for e in held if e["kind"] == "picked"]  # forked, and one fork kept
    if node.check:
        red = [e["detail"] for e in store.node_log(node.id, ("precheck",))]  # red first, at the base
        red = [d for d in red if d.get("check") == node.check]
        at_base = red and red[-1].get("verdict") in ("passes", "landed")  # landed: reopened, done on it again
        too = ", and it passed at the base too" if at_base else ""
        lines.append(f"Check: `{node.check}` passed{too}")
    if tries:
        kept = picked[-1]["fork"] if picked else None  # the kept fork's executor is the one that did it
        a = ([t for t in tries if t.get("fork") == kept] or tries)[-1]
        who = " ".join(filter(None, (a["executor"], a["model"] and a["model"].rsplit("/", 1)[-1])))
        spent = f"${sum(t['dollars'] for t in tries):.4f} at list price"
        if not all(t["meter"] and t["priced"] for t in tries):  # no dollars where nothing counted them
            spent = "no meter" if not all(t["meter"] for t in tries) else "no list price"
        forked = f"{picked[-1]['of']} forks, kept {kept} · " if picked else ""
        lines.append(f"Executor: {who} · {forked}{len(tries)} attempt{'s' * (len(tries) != 1)} · {spent}")
    lines += [f"Reopened: {notes[-1]}"] if notes else []
    subject = f"{node.title} ({node.id}{', reopened' if notes else ''})"
    return "\n".join([subject, "", *lines, f"Graphene-Node: {node.id}"])


def land(
    store,
    target: Path,
    tree: Path,
    node: P.Node,
    say: Callable[[str], None],
    not_here: set[str] = frozenset(),
    ran: list[tuple[str, str, str]] | None = None,
) -> bool:
    """Commit the leaf's work on its branch and merge it into the checkout the run was started from.
    True when it landed. When the merge is not clean nothing in the target is touched: the leaf waits
    for the person in review, on its branch, and what needs it waits with it. ``ran``: the checks of
    what this run has landed (command, whose, the commit it landed at); when the target has moved since
    the leaf's base, its own and those of what landed since then run on the merge first, and one that
    fails parks it as an unclean merge does."""
    branch = f"graphene/{node.id}"
    who = P.Caller("graphene run", False)
    ident = _ident(tree)
    # a merge of the person's own, half done: theirs to finish, and never ours to abort
    theirs = _git(target, "rev-parse", "-q", "--verify", "MERGE_HEAD", ok=True).returncode == 0
    paths: list[str] = []
    on_merge: list[str] = []

    def landed() -> None:
        store.log_node(node.id, P._now(), "landed", who.label, None, None,
                       {"commit": P.head(target), "branch": branch, "into": str(target.resolve()),
                        "paths": paths[: P.KEPT_PATHS],
                        **({"on_merge": on_merge} if on_merge else {})})  # fmt: skip
        _git(target, "worktree", "remove", "--force", str(tree), ok=True)
        _git(target, "branch", "-D", branch, ok=True)
        P.mark_boundary(store, target)

    try:
        if theirs:
            raise P.Refused(f"a merge of your own is in progress in {target}; finish it or abort it first")
        paths = _commit(store, tree, node)
        before = P.head(target)
        if ran is not None and _in_sandbox(store, node):
            say(f"{node.id}: not checked on the merge: it ran in a sandbox, and its check runs there")
        elif ran is not None:
            for _ in range(3):  # the checkout moves while a check runs (a commit of yours, a sign-off)
                own = P.port_env(store, node)  # its check ran with its PORT: on the merge too
                checked = _red_on_merge(target, branch, before, node, ran, ident, say, own)
                now = P.head(target)
                if now == before:
                    on_merge += checked
                    break
                before = now  # checked on a merge that is not the one that would land: again
            else:
                raise P.Refused("the branch moved three times while its check ran, so no merge of it was "
                                "checked that could land")  # fmt: skip
        clean = _git(target, "diff", "--cached", "--quiet", ok=True).returncode == 0
        try:
            _git(target, *ident, "merge", "--no-ff", "--no-edit", "-m", _merged(store, node), branch)
        except KeyboardInterrupt:  # stopped while git merged: a hook of the person's was running
            with _no_interrupt():
                made = P.head(target) != before  # the merge commit (a post-merge hook was cut short)
                _unmerge(target, branch, clean and not made)  # what git left half done
                if made:
                    landed()  # else the caller parks the leaf
            raise
    except P.Refused as no:
        if not theirs:
            _unmerge(target, branch)
        said = [" ".join(str(no).split())]
        with store.claim():
            fresh = P.get(store, node.id)
            fresh.state = P.REVIEW
            P._save(store, fresh, "unlanded", who, P._now(), branch=branch, worktree=str(tree), why=said[:6])
        say(
            f"{node.id} passed and did not land: {said[0]}. Your checkout is as it was\n"
            f"  its work: {branch}, in {tree}\n"
            f"  `git merge {branch}`, then `graphene node signoff {node.id}`; or `graphene node reopen "
            f"{node.id}` to have it done again on top of what is here now"
        )
        return False
    landed()
    for up in P.roll_up(store, who, target, not_here=not_here):
        say(f"{up.id} is {'done' if up.state == P.DONE else 'finished; it waits for a sign-off'}: "
            "everything under it is" + (f", and `{up.check}` passes" if up.check else ""))  # fmt: skip
    return True


def _in_sandbox(store, node: P.Node) -> bool:
    """Did this leaf work in a sandbox? Its check then runs there (``P.finish``), not on this machine."""
    return bool(P.sandboxed(store, node))


def _red_on_merge(target: Path, branch: str, before: str | None, node: P.Node,
                  ran: list[tuple], ident: list[str],
                  say: Callable[[str], None], env: dict[str, str] | None = None) -> list[str]:  # fmt: skip
    """When the target has moved since ``branch`` was cut, the leaf's check and the checks of what this
    run landed since (``ran``: each check, whose, where it landed, and its leaf's own environment, its PORT)
    run on the merge made as a commit of its own, nowhere in the checkout: the leaf and what landed
    meanwhile have never been checked together, and one can turn the other's red. What landed before the
    leaf was cut is under its own check already. ``env``: this leaf's own, as its check ran with. Returns
    the commands run; one that fails is refused, naming whose and on top of what."""
    base = _git(target, "merge-base", "HEAD", branch, ok=True).stdout.strip()
    if not before or base == before:
        return []  # not moved: what it passed on is what it lands on
    made = _git(target, "merge-tree", "--write-tree", "HEAD", branch, ok=True)
    if made.returncode == 1:
        return []  # a conflict: the merge itself refuses it
    if made.returncode:  # git before 2.38 has no --write-tree
        why = ((made.stderr or made.stdout).strip().splitlines() or ["no output"])[0]
        say(f"{node.id}: not checked on the merge: `git merge-tree --write-tree` (git 2.38) failed: {why}")
        return []
    merge = _git(target, *ident, "commit-tree", made.stdout.split()[0], "-p", "HEAD", "-p", branch,
                 "-m", "check").stdout.strip()  # fmt: skip
    checks = {node.check: (node.id, env)} if node.check else {}
    for command, whose, at, *own in ran:  # landed since the leaf was cut: its commit is not under the base
        under = _git(target, "merge-base", "--is-ancestor", at, base, ok=True).returncode == 0
        if command not in checks and not under:
            checks[command] = (whose, own[0] if own else None)
    passed: list[str] = []
    for command, (whose, own) in checks.items():
        extra = {"env": own} if own else {}  # named only when there is one: a test's stand-in takes none
        ok, tail, _ = P.run_check(command, target, at=merge, **extra)
        if not ok and whose != node.id and not P.run_check(command, target, at=before, **extra)[0]:
            say(f"{node.id}: {whose}'s check `{command}` already fails on {before[:8]}, so it is not held "
                f"against {node.id}")  # fmt: skip
            continue  # red without this leaf: whatever turned it red is the leaf that landed before
        if not ok:
            last = next((ln.strip() for ln in reversed(tail.splitlines()) if ln.strip()), "")
            raise P.Refused(f"it passes on its base, and {whose}'s check `{command}` fails on top of "
                            f"{before[:8]}, which has moved since" + (f": {last[:160]}" if last else ""))
        passed.append(command)
    return passed


def _unmerge(target: Path, branch: str, staged_ours: bool = False) -> None:
    """Undo this run's merge of ``branch`` that did not finish, and nothing of the person's. A merge
    git paused (a conflict, a hook that refused, a post-merge hook cut short after the commit, which
    `--abort` leaves as it is) has MERGE_HEAD at the branch, and is aborted; a MERGE_HEAD at
    anything else is the person's own merge. One stopped while a hook ran, before git
    wrote MERGE_HEAD, left the leaf's files staged on a HEAD that did not move: `reset --merge` puts
    them back and keeps what is not staged, and only when nothing was staged before the merge began
    (``staged_ours``: git merges onto a clean index only, so all that is staged is the run's)."""
    merging = _git(target, "rev-parse", "-q", "--verify", "MERGE_HEAD", ok=True).stdout.strip()
    if merging:
        if merging == _git(target, "rev-parse", "-q", "--verify", branch, ok=True).stdout.strip():
            _git(target, "merge", "--abort", ok=True)
    elif staged_ours:
        _git(target, "reset", "-q", "--merge", ok=True)


def _only_run(root: Path):
    """One parallel run a repo: a second one would clear the first one's worktrees from under it."""
    lock = root / ".graphene" / "run.lock"
    lock.parent.mkdir(exist_ok=True)
    other = run_holding(root)  # None: no lock, or the run that left it is gone
    if other is not None:
        raise P.Refused(
            f"another `graphene run` is going here (pid {other}); `graphene watch` shows it"
        )
    lock.write_text(f"{os.getpid()}\n{_started(os.getpid()) or ''}\n")  # the pid, and when it began
    return lock


@P.ctrl_c_on_hangup()
def run_parallel(
    open_store: Callable[[], object],
    root: Path,
    target: Path,
    workers: int,
    template: str = DEFAULT_WITH,
    attempts: int = ATTEMPTS,
    only: list[str] | None = None,
    say: Callable[[str], None] = print,
    logs: Path | None = None,
    precheck: bool = False,
    max_usd: float | None = None,
    forks: Forks | None = None,
) -> list[P.Node]:
    """Every leaf an agent can reach, up to ``workers`` at once, each in its own worktree; landed one
    at a time, here, as they finish. A leaf never starts while something it needs has not landed, or
    while a leaf whose scope overlaps its own is in flight. ``precheck``: red first, before any starts.
    ``max_usd``: a cap on what starts (``Budget``). ``forks``: what the run was told about forks, for
    each leaf to read (``forks_of``)."""
    _splits(template)
    if _git(target, "rev-parse", "-q", "--verify", "HEAD", ok=True).returncode != 0:  # as init says it
        raise P.Refused(
            "this repo has no commit yet: a run cuts each leaf's worktree from HEAD, so commit once first"
        )
    if _git(target, "symbolic-ref", "-q", "HEAD", ok=True).returncode != 0:
        raise P.Refused(
            f"{target} is on no branch (a detached HEAD): leaves merged here would belong to no branch "
            "and be lost at the next checkout. `git switch <branch>` first, or run with --here"
        )
    lock = _only_run(root)
    try:
        return _run_parallel(open_store, root, target, workers, template, attempts, only, say, logs, precheck,
                             max_usd, forks)  # fmt: skip
    finally:
        lock.unlink(missing_ok=True)


def _run_parallel(open_store, root, target, workers, template, attempts, only, say, logs,
                  precheck, max_usd, forks=None) -> list[P.Node]:  # fmt: skip
    store = open_store()
    began = _newest(store)  # it holds the repo from here: what is asked of it from now on (red first can
    # take minutes) is asked of it, and nothing before
    sweep(store, say, root)  # a leaf a dead run still holds would never be ready again
    _begins(template)
    only = leaves_of(store, only)
    if precheck:
        _red_first(store, target, only, say, committed=True)
    planned = {n.id for n in P.nodes(store) if n.state not in P.GONE}
    files = P.tracked(target)
    # what this run took, or found came back, each with its log's newest row then: the person's act
    # after it (``_answered``) is theirs to have it taken again, as a run they started now would; a leaf
    # asked for before this run began was asked of another run
    tried = dict.fromkeys(_came_back(store, only, say), began)
    flying: dict[Future, tuple[P.Node, Path]] = {}
    slots: dict[Future, int] = {}  # each flying leaf's worker slot: its executors' PORT is named by it
    unlanded: set[str] = set()
    finished: list[P.Node] = []
    waiting: dict[str, str] = {}  # a leaf whose needs are done elsewhere and not here yet: said once
    ran: list[tuple] = []  # what this run landed: its check, whose, where it landed, its leaf's own env
    stop = Stop()
    budget = Budget(max_usd, say) if max_usd is not None else None
    ports = Ports()

    def work(node_id: str, tree: Path, slot: int) -> P.Node | None:
        with open_store() as mine:  # a thread, a connection
            return run_node(mine, node_id, tree, template, attempts, say, logs, stop, budget, forks, ports,
                            slot)  # fmt: skip

    def again(node_id: str) -> bool:
        """Taken again, or one this run was not started with: the person widened or changed it, or reopened
        it, since this run took it, or a `graphene run` asked for it while this one held the repo."""
        said = _answered(store, node_id, tried.get(node_id, began))
        return said == QUEUED or (said is not None and node_id in tried)

    def launch(pool: ThreadPoolExecutor) -> None:
        # one the person signed off since it parked has landed: still held here, its parent never closed
        unlanded.difference_update([i for i in unlanded if P.unlanded(store, i) is None])
        everything = P.nodes(store)
        by_id = {n.id: n for n in everything}
        busy = {n.id for n, _ in flying.values()} | unlanded
        for n in P.ready(everything, P.Caller("agent", False)):
            if len(flying) >= workers:
                return
            if (n.id not in planned or n.id in tried or (only and n.id not in only)) and not again(n.id):
                continue
            if busy & set(P.all_needs(n, by_id)):
                continue  # done in its worktree is not yet here
            away = "; ".join(P.not_here(store, n, target, committed=True))
            if away:  # done by another run, or in place and not committed: a worktree would miss it
                if waiting.get(n.id) != away:
                    waiting[n.id] = away
                    say(f"{n.id} waits on {away}")
                continue
            if any(
                may_collide(n.scope, o.scope) or P.overlap(n.scope, o.scope, files)
                for o, _ in flying.values()
            ):
                continue  # one writer a path: it starts when that one has landed, on top of it
            if budget and not budget.take(_worst(shlex.split(template))):
                return  # None: what is going holds the room, asked again at the next look; False: past
                # the cap, and what is not started stays open
            tried[n.id] = _newest(store, n.id)
            tree = worktree_for(store, root, target, n.id)
            slot = min(set(range(workers)) - set(slots.values()), default=len(flying))  # the free slot
            future = pool.submit(work, n.id, tree, slot)
            flying[future], slots[future] = (n, tree), slot

    def collect(future: Future) -> None:
        nonlocal files
        unlanded.difference_update([i for i in unlanded if P.unlanded(store, i) is None])
        was, tree = flying.pop(future)
        slots.pop(future, None)
        try:
            node = future.result()
        except P.Refused as no:  # one leaf's trouble (its executor would not start) is not the run's
            say(str(no))
            node = None
        if node is None:  # handed back: its worktree stays, with whatever it tried, for the person
            log = store.node_log(was.id, ("started", "forked"))
            if log and log[-1]["kind"] == "forked":  # its forks tried, each kept on its own ref
                say(f"{was.id}: what each fork tried is kept under refs/graphene/forks/{was.id}/")
            else:
                say(f"{was.id}: what it tried is kept in {tree} until a run takes {was.id} again")
            return
        if node.state == P.REVIEW:  # a sign-off holds the merge: its work waits on its branch for the yes
            park(store, tree, node, say, "it waits for your sign-off before it lands")
            unlanded.add(node.id)
            return
        try:
            landed = land(store, target, tree, node, say, {n.id for n, _ in flying.values()} | unlanded, ran)
        except KeyboardInterrupt:
            with _no_interrupt():  # after it landed (a sub-goal's check ran) it stays done and landed
                if (store.node_log(node.id, ("started", "landed")) or [{}])[-1].get("kind") != "landed":
                    park(store, tree, P.get(store, node.id), say)
            raise
        if landed:
            if node.check and not _in_sandbox(store, node):  # its check runs where it ran, not here
                ran.append((node.check, node.id, P.head(target) or "", P.port_env(store, node)))
            finished.append(P.get(store, node.id))
            _said_done(store, finished[-1], say)
            files = P.tracked(target)
        else:
            unlanded.add(node.id)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        try:
            while True:
                launch(pool)
                if not flying:
                    return finished
                # every POLL too: what the person did meanwhile (a sign-off, a widen, a leaf asked for) is
                # taken up while the run goes on, not once one of its own leaves ends
                for future in wait(flying, timeout=POLL, return_when=FIRST_COMPLETED).done:
                    collect(future)
        except KeyboardInterrupt:
            stop.halt()  # every executor stopped, every worker told: each hands its leaf back
            pool.shutdown(wait=True, cancel_futures=True)
            for future, (was, tree) in flying.items():
                node = P.get(store, was.id)
                if future.done() and not future.cancelled() and node.state in (P.DONE, P.REVIEW):
                    park(store, tree, node, say)  # stopped after it passed, before it landed: in review
            raise


def park(store, tree: Path, node: P.Node, say: Callable[[str], None],
         why: str = "the run was stopped before it landed") -> None:  # fmt: skip
    """A leaf that passed its boundary in its worktree and is not to land now (the run was stopped
    before it could, or it waits for a sign-off): its work is committed on its branch, and it waits
    for the person in review, as a leaf whose merge was not clean does. The store never says done
    for work that is nowhere here."""
    branch = f"graphene/{node.id}"
    try:
        _commit(store, tree, node)
    except P.Refused as no:
        why = f"{why}, and its work could not be committed: {no}"
    with store.claim():
        fresh = P.get(store, node.id)
        fresh.state = P.REVIEW
        P._save(store, fresh, "unlanded", P.Caller("graphene run", False), P._now(), branch=branch,
                worktree=str(tree), why=[why])  # fmt: skip
    say(f"{node.id} passed; {why}\n  its work: {branch}. `graphene node diff {node.id}` shows it; "
        f"`graphene node signoff {node.id}` merges it")


def fork_work(store, target: Path, node_id: str, letter: str) -> tuple[str, str, list[dict]]:
    """One fork's work as its ref keeps it (``_keep_fork``): the ref, its commit, and the rows of the hold
    that forked (its `forked` row on). Refused when the leaf's last hold did not fork, had no such fork,
    or the fork changed nothing inside its scope, so nothing of it was kept."""
    from .node_record import _hold  # the rows of its last hold

    held = _hold(store.node_log(node_id, ("started", "forked", "fork", "picked")))
    forked = next((e["detail"] for e in held if e["kind"] == "forked"), None)
    if forked is None:
        raise P.Refused(f"{node_id}'s last hold did not fork, so it has no fork {letter}")
    if letter not in forked["forks"]:
        raise P.Refused(f"{node_id} forked {forked['of']} ways ({', '.join(forked['forks'])}): it has no "
                        f"fork {letter}")  # fmt: skip
    ref = fork_ref(node_id, letter)
    sha = _git(target, "rev-parse", "-q", "--verify", f"{ref}^{{commit}}", ok=True).stdout.strip()
    if not sha:
        raise P.Refused(f"fork {letter} of {node_id} changed nothing inside its scope, so nothing of it was "
                        "kept")  # fmt: skip
    return ref, sha, held


def pick_fork(store, target: Path, node_id: str, letter: str, who: P.Caller) -> str:
    """`graphene node pick`: the person's own choice among the forks of a leaf that waits in review with its
    work parked on its branch (``park``). The branch, and its worktree, become that fork's work as its ref
    keeps it, whatever the rule kept, and a `picked` row says so, by the person; the sign-off then lands it
    as it lands any leaf (``_signoff`` → ``land``). The fork's state is on its row, so a fork whose check
    was refused is the person's to land, as an override is: returns that state, for the person to hear.
    Refused on a leaf that is not in review, or whose work is not parked on a branch."""
    P._person_only(who, "picking a fork")
    node = P.get(store, node_id)
    if node.state != P.REVIEW:
        raise P.Refused(f"{node.id} is {node.state}: a fork is picked on a leaf in review, before its "
                        "sign-off")  # fmt: skip
    left = P.unlanded(store, node.id)
    if not left:
        raise P.Refused(f"{node.id}'s work is not parked on a branch, so no fork of it can take its place")
    _ref, sha, held = fork_work(store, target, node_id, letter)
    tree = Path(left.get("worktree") or "")
    if tree.is_dir():  # the branch is checked out there: it moves with the tree
        _git(tree, "reset", "-q", "--hard", sha)
    else:  # cleared by hand: the branch alone, which the sign-off has the person merge, as it says
        _git(target, "update-ref", f"refs/heads/{left.get('branch', f'graphene/{node_id}')}", sha)
    was = [e["detail"] for e in held if e["kind"] == "picked"]
    row = {"fork": letter, "of": next(e["detail"]["of"] for e in held if e["kind"] == "forked"),
           "by": "person", "reason": f"picked by {who.name}", "table": was[-1]["table"] if was else []}
    store.log_node(node.id, P._now(), "picked", who.label, None, None, row)
    return next((e["detail"]["state"] for e in reversed(held)
                 if e["kind"] == "fork" and str(e["detail"].get("fork")) == letter), "on no record")
