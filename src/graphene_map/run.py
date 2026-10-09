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
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import UTC, datetime
from pathlib import Path

from . import board as B
from . import extra
from . import meter as M
from . import plan as P
from .plan import may_collide
from .record import seconds as _seconds

# An executor may edit files and run `graphene node …` and `graphene plan …` (its done, its release, a
# look at the plan), and nothing else unless the person says so with --with. Not `graphene run` or
# `graphene ask`: through their own --with, either would be any command at all.
DEFAULT_WITH = (
    "claude -p --permission-mode acceptEdits --allowedTools 'Bash(graphene node *)' 'Bash(graphene plan *)' "
    "--output-format stream-json --verbose"  # the stream the meter reads: turns, tokens, tool calls, cost
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
    Token Factory; `claude` and `codex` alone are those agents as Graphene starts them by default;
    anything else is a command, as it is. Nothing named is refused (`unchosen`)."""
    spec = (spec or "").strip()
    if not spec:
        raise unchosen("executor")
    if spec.split(None, 1)[0] == "nemotron":
        return extra.need("executor").template(spec)
    return {"claude": DEFAULT_WITH, "codex": CODEX}.get(spec, spec)


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
POLL = 0.5  # seconds between looks at a running executor: the person may have released its leaf
GRACE = 10  # seconds an executor is given to end after TERM, before KILL


class Stop:
    """What a Ctrl-C reaches (or a closed terminal, or a `kill`): the flag every worker reads, each
    executor this run started, and each check it runs. They run in sessions of their own, so the
    terminal's Ctrl-C reaches Graphene alone, which hands each leaf back before it stops its
    executor."""

    def __init__(self) -> None:
        self.event = threading.Event()
        self._procs: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

    def add(self, node_id: str, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs[node_id] = proc

    def remove(self, node_id: str) -> None:
        with self._lock:
            self._procs.pop(node_id, None)

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
    way the dead run's attempt is closed first (``_close``): nothing else settles its hold. Last, every
    hold a dead run left in flight in its ledger is closed, whatever its leaf has become since: the
    executor left working may have ended the leaf itself (`done`, or `release`)."""
    for n in P.nodes(store, (P.RUNNING,)):
        if not (n.executor or "").startswith("run:"):
            continue
        last = (store.node_log(n.id, ("attempt",)) or [None])[-1]
        this = last["detail"] if last and last["session_id"] == n.session_id else {}
        if this.get("run_pid"):
            gone = not _still(this["run_pid"], this.get("run_start"))
        else:  # started, and no attempt written yet: dead only if no parallel run holds the lock
            gone = P.RUN_TREE in (n.checkout or "") and not _locked(root)
        if not gone:
            continue
        _close(this)
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
    proc: subprocess.Popen, store, node_id: str, stop: Stop, each: Callable[[], None] | None = None
) -> int:
    """The executor's exit code. Meanwhile, a leaf the person released (or dropped) stops its
    executor: handing it back is the person's way to say stop. ``each`` runs every POLL."""
    while True:
        try:
            return proc.wait(timeout=POLL)
        except subprocess.TimeoutExpired:
            pass
        if each:
            each()
        if stop.event.is_set() or _let_go(store, node_id):
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


def prompt_for(
    node: P.Node, notes: list[str], refusal: str | None, why: list[str] | None = None, decided: list[str] = ()
) -> str:
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
    if refusal:
        lines += ["", REFUSED, refusal]
    return "\n".join(lines)


REFUSED = "Your last attempt was not accepted:"  # the Nemotron executor reads what follows: why it stepped up


def _worst(argv: list[str]) -> float:
    """What one attempt may spend: the command's --max-budget-usd, else WORST."""
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
    whole = meter.reported is not None if meter.kind == "claude" else meter.begun == meter.turns
    dollars = meter.dollars if whole else hold["worst"]
    if meter.kind == "codex" and not (meter.price and meter.price(meter.model)):
        dollars = 0.0  # no list price: the bill says its tokens
    used = {"prompt_tokens": meter.prompt_tokens, "completion_tokens": meter.completion_tokens}
    night.settle(hold["id"], hold["model"], dollars, used, hold.get("ledger"))


def command_for(template: str, prompt: str, session: str, again: bool) -> list[str]:
    """The executor's argv. Claude Code is told which session this is, so its hooks hold it to the
    node from its first call and a second attempt resumes with what the first one learned; any other
    executor gets the prompt (refusal included) as its last argument, fresh each time."""
    argv = shlex.split(template)
    if argv and Path(argv[0]).name == "claude":  # `--`: a prompt that begins with a note's "-" is no option
        argv += [*(["--resume", session] if again else ["--session-id", session]), "--"]
    return [*argv, prompt]


def run_node(
    store,
    node_id: str,
    checkout: Path,
    template: str,
    attempts: int,
    say: Callable[[str], None],
    logs: Path | None,
    stop: Stop | None = None,
) -> P.Node | None:
    """One leaf, start to boundary, in ``checkout``. Returns it when it ended done (or in review);
    None when it could not start, was handed back, or ran out of attempts. Interrupted (Ctrl-C, or
    ``stop``), the leaf is handed back before its executor is stopped, and the interruption goes on."""
    session = str(uuid.uuid4())
    name = label(template)
    who = P.Caller(f"run:{name}", False, session)
    stop = stop or Stop()
    try:
        node = P.start(store, node_id, who, checkout)
    except P.Refused as no:
        say(str(no) if "cannot start" in str(no) else f"{node_id} cannot start: {no}")
        return None
    say(f"{node.id} started: {node.title}")
    refusal: str | None = None
    stamp = (node.started_at or P._now()).replace(":", "").replace("-", "")[:15]
    proc: subprocess.Popen | None = None
    hold: dict | None = None  # the attempt's on the night's ledger
    paid = 0.0  # what this hold's attempts settled: a resumed Claude Code reports the session's total
    try:
        for attempt in range(1, attempts + 1):
            if stop.event.is_set():  # stopped while the last attempt's check ran: nothing starts again
                raise KeyboardInterrupt
            argv = command_for(
                template,
                prompt_for(
                    node, P.notes(store, node.id), refusal, P.trail(store, node), B.decided(store, node)
                ),
                session,
                attempt > 1,
            )
            # GRAPHENE_EXECUTOR: its own `done` is logged under the name the run's acts are (plan.caller)
            # GRAPHENE_TRY: which attempt this is, told rather than read back from the log, whose row
            # for it is written only once the process is running
            env = {**os.environ, "GRAPHENE_NODE": node.id, "GRAPHENE_ATTEMPT": session,
                   "GRAPHENE_TRY": str(attempt)}  # fmt: skip
            env["GRAPHENE_EXECUTOR"] = name
            if name != "nemotron":  # only Graphene's own executor calls Token Factory; the rest never look
                env["GRAPHENE_KEYCHAIN"] = "off"
            env.pop("GRAPHENE_AS", None)  # whoever started the run, the executor speaks for nobody
            log = None
            if logs is not None:  # streamed as it runs, so its tail can be read while it works
                logs.mkdir(parents=True, exist_ok=True)
                log = logs / f"{node.id}-{stamp}-{session[:8]}-{attempt}.txt"
            try:  # under the opening: the attempt's worst case, held first
                night, hold = held(name, argv, paid, f"run: {node.id} attempt {attempt}")
            except P.Refused as no:
                P.release(store, node.id, who, str(no))
                say(f"{node.id} came back: {no}")
                return None
            sink = open(log, "w", encoding="utf-8") if log else subprocess.DEVNULL  # noqa: SIM115
            try:
                proc = subprocess.Popen(
                    argv, cwd=checkout, env=env, stdin=subprocess.DEVNULL, stdout=sink,
                    stderr=subprocess.STDOUT, start_new_session=True,
                )  # fmt: skip
            except OSError as no:  # the executor is not installed, or not executable: nothing ran
                if hold:
                    night.settle(hold["id"], hold["model"], 0.0, ledger=hold["ledger"])
                P.release(store, node.id, who, f"the executor could not be started: {name}: {no.strerror}")
                raise P.Refused(
                    f"cannot run `{argv[0]}`: {no.strerror}. {node.id} was handed back untouched; name "
                    "another executor with --with"
                ) from None
            finally:
                if log:
                    sink.close()
            stop.add(node.id, proc)
            began = time.monotonic()
            kind = M.kind(argv) if log else None
            metered = kind or ("nemotron" if name == "nemotron" else None)  # Nemotron writes its own rows
            # the hold rides on the attempt: should this run die, the next one's sweep settles it (_close)
            store.log_node(node.id, P._now(), "attempt", who.label, session, None,
                           {"attempt": attempt, "pid": proc.pid, "pid_start": _started(proc.pid),
                            "run_pid": os.getpid(), "run_start": _started(os.getpid()),
                            "log": str(log) if log else None, "checkout": str(checkout),
                            "meter": metered, "hold": hold})  # fmt: skip
            meter = read = None
            if kind:  # what it writes is a stream the meter reads: read as it is written
                price = _listed().get if kind == "codex" else None
                meter = M.Meter(kind, attempt, M.model_in(argv), paid, price, str(checkout))
                read = Reader(log, meter, lambda k, d: store.log_node(node.id, P._now(), k, who.label,
                                                                      session, None, d))  # fmt: skip
            try:
                code = _waited(proc, store, node.id, stop, read)
            finally:
                stop.remove(node.id)
                if read:
                    read(last=True)  # Claude Code's result is its last line
                    paid += meter.dollars
                if hold:
                    _settle(night, hold, meter)
            # not an "attempt" row: readers take the last of those as the attempt going now
            store.log_node(node.id, P._now(), "ended", who.label, session, None,
                           {"attempt": attempt, "exit": code, "seconds": round(time.monotonic() - began, 1),
                            "meter": metered, "unread": meter.unread if meter else 0})  # fmt: skip
            if stop.event.is_set():
                raise KeyboardInterrupt
            say(f"{node.id} attempt {attempt}: the executor ended (exit {code})")
            current = P.get(store, node.id)
            if current.state in (P.DONE, P.REVIEW):  # it ran `done` itself, and the boundary agreed
                return current
            if current.state != P.RUNNING:  # it handed the node back and said why, or the person did
                last = (store.node_log(node.id, ("released", "dropped")) or [{"detail": {}, "actor": ""}])[-1]
                person = last["detail"].get("person") or last.get("kind") == "dropped"
                who_said = last["actor"] if person else "the executor"
                say(f"{node.id} handed back by {who_said}: {last['detail'].get('why', current.state)}")
                for _key, what, command in P.offers(store, current):
                    say(f"  {what}: `graphene {shlex.join(command)}`")
                if P.not_offered(store, current):
                    say(f"  {P.not_offered(store, current)}")
                return None
            try:
                return P.finish(store, node.id, who)
            except P.Refused as no:
                if P.get(store, node.id).state != P.RUNNING:  # the person let it go while its check ran
                    say(f"{node.id} handed back while its check ran: {no}")
                    return None
                refusal = str(no)
                first, *rest = refusal.splitlines()
                paths = rest[0].strip() if rest and rest[0].startswith("  ") else ""  # the refusal's line 2
                said = first.rstrip(":") + (f" · {paths}" if paths else "")
                say(f"{node.id} attempt {attempt} refused: {said}")
        tries = f"{attempts} attempt{'s' if attempts != 1 else ''}"
        # the refusal for the person: its `graphene node release` step was the executor's to take
        told = "\n".join(ln for ln in refusal.splitlines() if "graphene node release" not in ln)
        crashed = f"; the executor itself exited {code}" if code else ""
        P.release(store, node.id, who, f"{tries}, the last one refused: {told}{crashed}")
        say(f"{node.id} came back after {tries}")
        return None
    except KeyboardInterrupt:
        with _no_interrupt():  # a second Ctrl-C must not leave the leaf running and its executor alive
            stop.halt()
            if proc is not None:
                _end(proc)  # its own session never saw the terminal's Ctrl-C: it is stopped here
            if hold and hold.get("id"):  # stopped before its attempt's own settle: its worst case, once
                _settle(night, hold, None)
            if P.get(store, node.id).state == P.RUNNING:
                P.release(store, node.id, who, STOPPED, stopped=True)
                say(f"{node.id} handed back: the run was stopped")
        raise


STOPPED = "the run was stopped before this leaf was finished"  # by Ctrl-C, `:stop` or a closed terminal


def summary(store, since: int, stopped: bool = False) -> str:
    """What a run did, in one line for the person, read from what the plan logged after entry
    ``since``: what it finished, what came back to them, what waits in review, and the two clocks (the
    agents' minutes and dollars, the person's acts and minutes). `graphene watch` shows this line when
    the run ends, so it is the run's last."""
    log = store.node_log()[since:]
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
    cost = clocks(log)
    if stopped:
        return "run stopped: " + (", ".join(said) or "nothing was finished") + cost
    if not ran:
        return "run: nothing started (graphene plan says what each leaf waits on)"
    return "run: " + (", ".join(said) or "nothing finished") + cost


def clocks(log: list[dict]) -> str:
    """The run's two clocks and its width, from its own rows: " · agents 41 min, $2.8700 at list price ·
    width 2 of 3 · you 4 acts, 2 min". With no usage row, the dollars are "no meter": nothing is invented."""
    agents, you, ran = M.agents(log, datetime.now(UTC)), M.you(log, P.person_name()), M.width(log)
    took = f"{round(agents['seconds'] / 60)} min" if agents["seconds"] >= 60 else "<1 min"
    spent, n = "no meter", agents["unpriced"]
    if any(e["kind"] == "usage" for e in log):
        spent = f"${agents['dollars']:.4f} at list price"
    if n:
        spent += f" + {f'{round(n / 1000)}k' if n >= 1000 else n} tokens with no list price"
    acts = f"{you['acts']} act{'s' * (you['acts'] != 1)}"
    wide = f" · width {ran['most']} of {ran['lanes']}" if ran else ""
    return f" · agents {took}, {spent}{wide} · you {acts}, {you['minutes']} min"


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
        "last": metered.get("last") or (said_by(last[-1]) if last else _spoke(log)),
        "idle": int(now - max(stamps)) if stamps else None,
    }


def _spoke(log: str | None) -> str:
    """The log's last line that is not one of the stream's JSON events (stderr shares the file)."""
    return next((line for line in reversed(tail(log, 40)) if not line.lstrip().startswith("{")), "")


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


def _said_done(node: P.Node, say: Callable[[str], None]) -> None:
    say(f"{node.id} is {'done' if node.state == P.DONE else 'finished; it waits for a sign-off'}")


@P.ctrl_c_on_hangup()
def run_plan(
    store,
    checkout: Path,
    template: str = DEFAULT_WITH,
    attempts: int = ATTEMPTS,
    only: list[str] | None = None,
    say: Callable[[str], None] = print,
    logs: Path | None = None,
) -> list[P.Node]:
    """Run every leaf an agent can reach, in order. Returns the ones that ended done (or in review)."""
    _splits(template)
    sweep(store, say, store.path.parent.parent)  # the repo's root, where a parallel run's lock is
    _begins(template)
    only = leaves_of(store, only)
    finished: list[P.Node] = []
    tried: set[str] = _came_back(store, only, say)  # never tried: the person's to run again
    # The nodes that exist when the run starts are the run: a plan that grows while it is going (a
    # proposal accepted, or an executor adding nodes) does not make an unattended run unbounded.
    planned = {n.id for n in P.nodes(store) if n.state not in P.GONE}
    while True:
        ready = [
            n
            for n in P.ready(P.nodes(store), P.Caller("agent", False))
            if n.id in planned and n.id not in tried and (not only or n.id in only)
        ]
        if not ready:
            return finished
        tried.add(ready[0].id)
        node = run_node(store, ready[0].id, checkout, template, attempts, say, logs, Stop())
        if node is not None:
            finished.append(node)
            _said_done(node, say)


# -- in parallel, a worktree a leaf ---------------------------------------------------------------------


def _git(where: Path, *args: str, ok: bool = False) -> subprocess.CompletedProcess:
    out = subprocess.run(["git", "-C", str(where), *args], capture_output=True, text=True)
    if out.returncode != 0 and not ok:
        raise P.Refused(
            f"git {' '.join(args[:3])} failed in {where}: {(out.stderr or out.stdout).strip()[:300]}"
        )
    return out


def worktree_for(store, root: Path, target: Path, node_id: str) -> Path:
    """A fresh worktree for one leaf, on branch graphene/<id>, cut from where the target stands now
    (so it has everything that has landed). What an earlier run left under the same name goes."""
    path = root / ".graphene" / WORKTREES / node_id
    _git(target, "worktree", "remove", "--force", str(path), ok=True)
    _git(target, "worktree", "prune", ok=True)
    shutil.rmtree(path, ignore_errors=True)  # a directory git has lost track of (a killed run) goes too
    _git(target, "worktree", "add", "--quiet", "-B", f"graphene/{node_id}", str(path), "HEAD")
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
    Returns the paths its boundary said had changed."""
    entry = (store.node_log(node.id, ("finished", "overruled")) or [{"detail": {}}])[-1]["detail"]
    paths = entry.get("changed") or []
    why = " > ".join(P.trail(store, node))
    message = f"{node.title}\n\n{node.goal or node.title}\n\n" + (f"Why: {why}\n" if why else "")
    _git(tree, "add", "-A", "--", *(paths if paths and not entry.get("more_changed") else ["."]))
    if _git(tree, "diff", "--cached", "--quiet", ok=True).returncode != 0:  # else it committed itself
        _git(tree, *_ident(tree), "commit", "-q", "--no-verify", "-m", f"{message}Graphene-Node: {node.id}\n")
    return paths


def land(
    store,
    target: Path,
    tree: Path,
    node: P.Node,
    say: Callable[[str], None],
    not_here: set[str] = frozenset(),
) -> bool:
    """Commit the leaf's work on its branch and merge it into the checkout the run was started from.
    True when it landed. When the merge is not clean nothing in the target is touched: the leaf waits
    for the person in review, on its branch, and what needs it waits with it."""
    branch = f"graphene/{node.id}"
    who = P.Caller("graphene run", False)
    ident = _ident(tree)
    # a merge of the person's own, half done: theirs to finish, and never ours to abort
    theirs = _git(target, "rev-parse", "-q", "--verify", "MERGE_HEAD", ok=True).returncode == 0
    paths: list[str] = []

    def landed() -> None:
        store.log_node(node.id, P._now(), "landed", who.label, None, None,
                       {"commit": P.head(target), "branch": branch, "into": str(target.resolve()),
                        "paths": paths[: P.KEPT_PATHS]})  # fmt: skip
        _git(target, "worktree", "remove", "--force", str(tree), ok=True)
        _git(target, "branch", "-D", branch, ok=True)
        P.mark_boundary(store, target)

    try:
        if theirs:
            raise P.Refused(f"a merge of your own is in progress in {target}; finish it or abort it first")
        paths = _commit(store, tree, node)
        before = P.head(target)
        clean = _git(target, "diff", "--cached", "--quiet", ok=True).returncode == 0
        try:
            _git(target, *ident, "merge", "--no-ff", "--no-edit", "-m", f"{node.title} ({node.id})", branch)
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
) -> list[P.Node]:
    """Every leaf an agent can reach, up to ``workers`` at once, each in its own worktree; landed one
    at a time, here, as they finish. A leaf never starts while something it needs has not landed, or
    while a leaf whose scope overlaps its own is in flight."""
    _splits(template)
    if _git(target, "symbolic-ref", "-q", "HEAD", ok=True).returncode != 0:
        raise P.Refused(
            f"{target} is on no branch (a detached HEAD): leaves merged here would belong to no branch "
            "and be lost at the next checkout. `git switch <branch>` first, or run with --here"
        )
    lock = _only_run(root)
    try:
        return _run_parallel(open_store, root, target, workers, template, attempts, only, say, logs)
    finally:
        lock.unlink(missing_ok=True)


def _run_parallel(open_store, root, target, workers, template, attempts, only, say, logs) -> list[P.Node]:
    store = open_store()
    sweep(store, say, root)  # a leaf a dead run still holds would never be ready again
    _begins(template)
    only = leaves_of(store, only)
    planned = {n.id for n in P.nodes(store) if n.state not in P.GONE}
    files = P.tracked(target)
    tried: set[str] = _came_back(store, only, say)  # never tried: the person's to run again
    flying: dict[Future, tuple[P.Node, Path]] = {}
    unlanded: set[str] = set()
    finished: list[P.Node] = []
    waiting: dict[str, str] = {}  # a leaf whose needs are done elsewhere and not here yet: said once
    stop = Stop()

    def work(node_id: str, tree: Path) -> P.Node | None:
        with open_store() as mine:  # a thread, a connection
            return run_node(mine, node_id, tree, template, attempts, say, logs, stop)

    def launch(pool: ThreadPoolExecutor) -> None:
        everything = P.nodes(store)
        by_id = {n.id: n for n in everything}
        busy = {n.id for n, _ in flying.values()} | unlanded
        for n in P.ready(everything, P.Caller("agent", False)):
            if len(flying) >= workers:
                return
            if n.id not in planned or n.id in tried or (only and n.id not in only):
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
            tried.add(n.id)
            tree = worktree_for(store, root, target, n.id)
            flying[pool.submit(work, n.id, tree)] = (n, tree)

    def collect(future: Future) -> None:
        nonlocal files
        was, tree = flying.pop(future)
        try:
            node = future.result()
        except P.Refused as no:  # one leaf's trouble (its executor would not start) is not the run's
            say(str(no))
            node = None
        if node is None:  # handed back: its worktree stays, with whatever it tried, for the person
            say(f"{was.id}: what it tried is kept in {tree} until the next run takes {was.id} again")
            return
        try:
            landed = land(store, target, tree, node, say, {n.id for n, _ in flying.values()} | unlanded)
        except KeyboardInterrupt:
            with _no_interrupt():  # after it landed (a sub-goal's check ran) it stays done and landed
                if (store.node_log(node.id, ("started", "landed")) or [{}])[-1].get("kind") != "landed":
                    park(store, tree, P.get(store, node.id), say)
            raise
        if landed:
            finished.append(P.get(store, node.id))
            _said_done(finished[-1], say)
            files = P.tracked(target)
        else:
            unlanded.add(node.id)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        try:
            while True:
                launch(pool)
                if not flying:
                    return finished
                for future in wait(flying, return_when=FIRST_COMPLETED).done:
                    collect(future)
        except KeyboardInterrupt:
            stop.halt()  # every executor stopped, every worker told: each hands its leaf back
            pool.shutdown(wait=True, cancel_futures=True)
            for future, (was, tree) in flying.items():
                node = P.get(store, was.id)
                if future.done() and not future.cancelled() and node.state in (P.DONE, P.REVIEW):
                    park(store, tree, node, say)  # stopped after it passed, before it landed: in review
            raise


def park(store, tree: Path, node: P.Node, say: Callable[[str], None]) -> None:
    """A leaf that passed its boundary in its worktree when the run was stopped, before it could
    land: its work is committed on its branch, and it waits for the person in review, as a leaf
    whose merge was not clean does. The store never says done for work that is nowhere here."""
    branch = f"graphene/{node.id}"
    try:
        _commit(store, tree, node)
        why = "the run was stopped before it landed"
    except P.Refused as no:
        why = f"the run was stopped before it landed, and its work could not be committed: {no}"
    with store.claim():
        fresh = P.get(store, node.id)
        fresh.state = P.REVIEW
        P._save(store, fresh, "unlanded", P.Caller("graphene run", False), P._now(), branch=branch,
                worktree=str(tree), why=[why])  # fmt: skip
    say(f"{node.id} passed; {why}\n  `git merge {branch}`, then `graphene node signoff {node.id}`")
