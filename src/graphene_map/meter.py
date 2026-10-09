"""The meter: what an executor did, said and spent, read from its own event stream.

A `Meter` takes the stream one line at a time (Claude Code's `--output-format stream-json`, Codex's
`exec --json`) and returns the rows `graphene run` logs on the leaf: `usage` per turn, `did` per tool
call, `said` per thing the agent says. `attempts`, `going`, `agents`, `width` and `you` read those rows
back for the screens. dev/process/meter/rows.md has the shapes. Standard library only; a line never raises.
"""

import itertools
import json
import os
import shlex
from collections import Counter
from datetime import UTC, datetime
from pathlib import PurePosixPath

from . import plan as P

# ponytail: a table of today's list prices, by hand; a Claude model it lacks is settled by the result's
# total_cost_usd, and its turns say "priced": False until then.
PRICES: dict[str, tuple[float, float, float]] = {  # dollars per million tokens: input, output, cache read
    "claude-fable-5-1": (10, 50, 0.25),
    "claude-opus-5-5": (4, 20, 0.20),
    "claude-opus-5": (5, 25, 0.50),
    "claude-sonnet-5-5": (2, 10, 0.20),
    "claude-sonnet-5": (2, 10, 0.20),
    "claude-haiku-4-5": (1, 5, 0.10),
    "claude-opus-4-8": (5, 25, 0.50),
    "claude-opus-4-7": (5, 25, 0.50),
    "claude-opus-4-6": (5, 25, 0.50),
    "claude-sonnet-4-6": (3, 15, 0.30),
}
FIVE_MINUTES, HOUR = 1.25, 2  # a cache write, as a multiple of the input price
SAID = 400  # characters of one said row
TARGET = 120  # characters of one did row's target
VERBS = {"Read": "reading", "NotebookRead": "reading", "Edit": "editing", "Write": "editing",
         "MultiEdit": "editing", "NotebookEdit": "editing", "Bash": "running", "Grep": "searching",
         "Glob": "searching", "WebSearch": "searching", "WebFetch": "searching"}  # fmt: skip
ENDPOINT = {"claude": "claude code", "codex": "codex"}
PROMPT = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")  # a Claude prompt's
HOLD_ENDS = ("finished", "overruled", "released", "dropped")  # an attempt with no `ended` row ends here


def option(argv: list[str], *names: str) -> str | None:
    """What the command gives the first of ``names`` it has, spaced (`--model x`) or joined (`--model=x`):
    Claude Code and Codex read both. None when it has none."""
    for a, b in zip(argv, [*argv[1:], None], strict=True):
        if a in names:
            return b
        name, joined, value = a.partition("=")
        if joined and name in names:
            return value
    return None


def kind(argv: list[str]) -> str | None:
    """Which stream the command writes: "claude" or "codex" when it writes one the meter reads, else None."""
    name = os.path.basename(argv[0]) if argv else ""
    if name == "claude" and option(argv, "--output-format") == "stream-json":
        return "claude"
    if name == "codex" and "exec" in argv and "--json" in argv:
        return "codex"
    return None


def model_in(argv: list[str]) -> str | None:
    """The model the command names with -m or --model, or None."""
    return option(argv, "-m", "--model")


def doing(verb: str, target: str) -> str:
    """What an executor is doing, in a few words: "editing ingest/xmlfeed.py"."""
    return f"{verb} {target}".strip()


def list_price(model: str | None, usage: dict) -> float | None:
    """What one Claude usage costs at the model's list price, in dollars; None for a model not in PRICES.
    A dated id (claude-haiku-4-5-20251001) or a context suffix (claude-opus-5-5[1m]) is its model's."""
    name = (model or "").split("[")[0]
    price = next((PRICES[k] for k in sorted(PRICES, key=len, reverse=True) if name.startswith(k)), None)
    if price is None:
        return None
    given, out, read = price
    hour = (usage.get("cache_creation") or {}).get("ephemeral_1h_input_tokens") or 0
    five = (usage.get("cache_creation_input_tokens") or 0) - hour
    return (
        (usage.get("input_tokens") or 0) * given
        + five * given * FIVE_MINUTES
        + hour * given * HOUR
        + (usage.get("cache_read_input_tokens") or 0) * read
        + (usage.get("output_tokens") or 0) * out
    ) / 1e6


def _unwrapped(command: str) -> str:
    """Codex's `/bin/zsh -lc '…'` as the command inside it."""
    try:
        argv = shlex.split(command)
    except ValueError:
        return command
    if len(argv) == 3 and argv[1] in ("-c", "-lc") and os.path.basename(argv[0]) in ("sh", "bash", "zsh"):
        return argv[2]
    return command


class Meter:
    """One attempt's stream, read line by line. ``price`` gives Codex's model its dollars per prompt
    token and per completion token, or None when the model has no list price. ``cwd`` is the checkout
    it works in: a file it names under it is said from there (Claude Code's init says its own)."""

    def __init__(self, kind: str, attempt: int, model: str | None = None, paid_before: float = 0.0,
                 price=None, cwd: str | None = None):  # fmt: skip
        self.kind, self.attempt, self.paid_before, self.price = kind, attempt, paid_before, price
        self.model = model or ("codex" if kind == "codex" else None)
        self.turns = self.prompt_tokens = self.completion_tokens = self.unread = 0
        self.begun = 0  # Codex's turns started: one not completed spent what no row says
        self.dollars, self.priced, self.reported = 0.0, True, None
        self.last: str | None = None
        self.result = ""  # Claude's answer, as `claude -p` prints it with no stream: its result's text
        self.cwd = cwd
        self._seen: set[str] = set()  # Claude's message ids counted, Codex's commands logged

    def feed(self, line: str) -> list[tuple[str, dict]]:
        """The rows one line of the stream gives. A line that is not a JSON event is counted in
        ``unread`` and gives none."""
        line = line.strip()
        if not line:
            return []
        try:
            event = json.loads(line)
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                raise ValueError("not an event")
            return self._claude(event) if self.kind == "claude" else self._codex(event)
        except Exception:  # a stream the meter cannot read degrades the meter, never the run
            self.unread += 1
            return []

    def _usage(self, prompt: int, completion: int, dollars: float | None) -> tuple[str, dict]:
        self.turns += 1
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.dollars += dollars or 0
        row = {"model": self.model, "calls": 1, "prompt_tokens": prompt, "completion_tokens": completion,
               "dollars": dollars or 0, "endpoint": ENDPOINT[self.kind], "attempt": self.attempt,
               "turn": self.turns}  # fmt: skip
        if dollars is None:
            self.priced = row["priced"] = False
        return "usage", row

    def _did(self, tool: str, target: str, verb: str) -> tuple[str, dict]:
        target = target.strip().split("\n")[0][:TARGET]
        self.last = doing(verb, target)
        return "did", {"attempt": self.attempt, "tool": tool, "target": target, "verb": verb}

    def _said(self, text: str) -> list[tuple[str, dict]]:
        text = text.strip()[:SAID]
        if not text:
            return []
        self.last = text
        return [("said", {"attempt": self.attempt, "text": text})]

    def _claude(self, event: dict) -> list[tuple[str, dict]]:
        if event["type"] == "system" and event.get("subtype") == "init":
            self.cwd, self.model = event.get("cwd"), event.get("model") or self.model
            return []
        if event["type"] == "result":
            return self._settled(event)
        if event["type"] != "assistant":
            return []
        message, rows = event["message"], []
        if message.get("id") not in self._seen:  # one message, several events: each repeats its usage
            self._seen.add(message.get("id"))
            usage = message.get("usage") or {}
            self.model = message.get("model") or self.model
            prompt = sum(usage.get(k) or 0 for k in PROMPT)
            rows.append(self._usage(prompt, usage.get("output_tokens") or 0, list_price(self.model, usage)))
        for block in message.get("content") or []:
            if block.get("type") == "tool_use":
                name, given = block.get("name") or "", block.get("input") or {}
                rows.append(self._did(name, self._target(given), VERBS.get(name, name.lower())))
            elif block.get("type") == "text":
                rows += self._said(block.get("text") or "")
        return rows

    def _target(self, given: dict) -> str:
        path = given.get("file_path") or given.get("notebook_path")
        if path:
            if self.cwd and PurePosixPath(path).is_relative_to(self.cwd):
                return str(PurePosixPath(path).relative_to(self.cwd))
            return path
        return given.get("command") or given.get("pattern") or ""

    def _settled(self, event: dict) -> list[tuple[str, dict]]:
        """Claude's result: one row that brings this attempt's turns to what Claude Code reports, its
        dollars and its tokens (the stream counts a message's output tokens before it is written). After
        --resume its total_cost_usd is the session's running total, so what earlier attempts paid comes
        off; its usage is the call's own (dev/test/results-2026-09-23.md)."""
        self.result = str(event.get("result") or event.get("subtype") or "")  # a stop says why it stopped
        reported = event.get("total_cost_usd")
        if not isinstance(reported, (int, float)):
            return []
        self.reported = reported
        rest = reported - self.paid_before - self.dollars
        self.dollars += rest
        used = event.get("usage") or {}
        given = sum(used.get(k) or 0 for k in PROMPT)
        more_in = max(0, given - self.prompt_tokens)
        more_out = max(0, (used.get("output_tokens") or 0) - self.completion_tokens)
        self.prompt_tokens += more_in
        self.completion_tokens += more_out
        return [("usage", {"model": self.model, "calls": 0, "prompt_tokens": more_in,
                           "completion_tokens": more_out, "dollars": rest, "endpoint": ENDPOINT[self.kind],
                           "attempt": self.attempt,
                           "turns": self.turns, "reported": reported})]  # fmt: skip

    def _codex(self, event: dict) -> list[tuple[str, dict]]:
        kind = event["type"]
        if kind == "turn.started":
            self.begun += 1
            return []
        if kind == "turn.completed":
            usage = event.get("usage") or {}
            prompt, completion = int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
            per = self.price(self.model) if self.price else None
            return [self._usage(prompt, completion, prompt * per[0] + completion * per[1] if per else None)]
        if kind == "turn.failed":
            return self._said("error: " + ((event.get("error") or {}).get("message") or ""))
        if kind == "error":
            return self._said("error: " + (event.get("message") or ""))
        if kind not in ("item.started", "item.completed"):
            return []
        item = event.get("item") or {}
        if item.get("type") == "command_execution":
            # counted once, as it starts, so a command still running is what the leaf is doing
            if item.get("id") in self._seen:
                return []
            self._seen.add(item.get("id"))
            return [self._did("command_execution", _unwrapped(item.get("command") or ""), "running")]
        if kind == "item.started":
            return []
        if item.get("type") == "file_change":  # each by its absolute path: said from the checkout, then cut
            paths = [c.get("path") for c in item.get("changes") or []]
            return [self._did("file_change", self._target({"file_path": p}), "editing") for p in paths]
        if item.get("type") == "agent_message":
            return self._said(item.get("text") or "")
        if item.get("type") == "error":
            return self._said("error: " + (item.get("message") or ""))
        return []


def _seconds(start: str, end: str | datetime) -> int:
    end = end if isinstance(end, datetime) else datetime.fromisoformat(end)
    return max(0, round((end - datetime.fromisoformat(start)).total_seconds()))


def attempts(rows: list[dict], scope: list[str] | None = None, now: datetime | None = None) -> list[dict]:
    """One leaf's attempts, oldest first, from its node_log rows: what each spent, did and said. A row
    without an attempt number (a usage row from before the meter, a denied path) is the attempt's that
    was going when it was written. An attempt with no `ended` row (one from before the meter, or a run
    that died) ends where its hold did."""
    now = now or datetime.now(UTC)
    tries: list[dict] = []
    numbered: dict = {}
    for e in rows:
        d = e["detail"] or {}
        if e["kind"] == "attempt":
            tries.append({"row": e, "rows": [], "ended": None, "held": None})
            numbered[d.get("attempt")] = tries[-1]
            continue
        if "attempt" in d:
            a = numbered.get(d["attempt"])
        else:
            a = tries[-1] if tries and not tries[-1]["ended"] else None
        if a is None:
            continue
        if e["kind"] == "ended":
            a["ended"] = e
        else:
            a["rows"].append(e)
            a["held"] = a["held"] or (e if e["kind"] in HOLD_ENDS else None)
    return [_attempt(a, nxt, scope, now) for a, nxt in itertools.pairwise([*tries, None])]


def going(rows: list[dict], scope: list[str] | None = None, now: datetime | None = None) -> dict | None:
    """The last attempt of the leaf's current hold (its rows after its last `started`): the one going now
    while it runs. None when the hold has made none: a person or a Claude Code session took the leaf
    after a run, or the run has not written its attempt yet. An earlier hold's attempt is not this one."""
    hold = rows[max((k for k, e in enumerate(rows) if e["kind"] == "started"), default=-1) + 1 :]
    return (attempts(hold, scope, now) or [None])[-1]


def _attempt(a: dict, nxt: dict | None, scope: list[str] | None, now: datetime) -> dict:
    rows, ended, start = a["rows"], a["ended"], a["row"]["timestamp"]
    usage = [e["detail"] for e in rows if e["kind"] == "usage"]
    did = [e["detail"] for e in rows if e["kind"] == "did"]
    talk = [e for e in rows if e["kind"] in ("did", "said")]
    said = [e["detail"].get("text") for e in rows if e["kind"] == "said"]
    executor = (a["row"]["actor"] or "").removeprefix("run:")
    checkout = a["row"]["detail"].get("checkout")

    def target(d: dict) -> str:  # Codex names a file it changed by its absolute path: said as the scope is
        path = PurePosixPath(d.get("target") or "")
        if d.get("verb") == "editing" and checkout and path.is_relative_to(checkout):
            return str(path.relative_to(checkout))
        return d.get("target") or ""

    def targets(verb: str) -> list[str]:
        return list(dict.fromkeys(target(d) for d in did if d.get("verb") == verb and d.get("target")))

    edited = targets("editing")
    told = [doing(e["detail"].get("verb") or "", target(e["detail"])) if e["kind"] == "did"
            else e["detail"].get("text") for e in talk]  # fmt: skip
    last = talk[-1] if talk else None
    until = ended or a["held"]
    end = datetime.fromisoformat((until or nxt["row"])["timestamp"]) if until or nxt else now
    return {
        "attempt": a["row"]["detail"].get("attempt"),
        "executor": executor,
        "meter": (ended["detail"].get("meter") if ended else None)
        or a["row"]["detail"].get("meter")  # known from the start: before its first turn it has no usage yet
        or (executor if usage or talk else None),
        "model": next((u["model"] for u in reversed(usage) if u.get("model")), None),
        "started": start,
        "log": a["row"]["detail"].get("log"),
        "seconds": _seconds(start, end),
        "until": end,  # its end, or now while it runs: a datetime
        "running": until is None and nxt is None,
        "exit": ended["detail"].get("exit") if ended else None,
        "turns": sum(u.get("calls") or 0 for u in usage),
        "prompt_tokens": sum(u.get("prompt_tokens") or 0 for u in usage),
        "completion_tokens": sum(u.get("completion_tokens") or 0 for u in usage),
        "dollars": sum(u.get("dollars") or 0 for u in usage),
        "priced": not unpriced(rows),
        "endpoints": sorted({u.get("endpoint") or "" for u in usage}),  # who answered; "" when a row says not
        "read": targets("reading"),
        "edited": edited,
        "ran": targets("running"),
        "runs": Counter(d["target"] for d in did if d.get("verb") == "running" and d.get("target")),
        "searched": targets("searching"),
        "said": said[-1] if said else None,
        "last": told[-1] if told else None,
        "told": told,
        "last_at": last["timestamp"] if last else None,
        "files_in": [f for f in edited if scope is None or P.in_scope(f, scope)],
        "files_out": [f for f in edited if scope is not None and not P.in_scope(f, scope)],
        "refused": list(dict.fromkeys(e["detail"]["path"] for e in rows
                                      if e["kind"] == "denied" and e["detail"].get("path"))),  # fmt: skip
    }


def unpriced(rows: list[dict]) -> int:
    """The tokens no list price covers: those of each turn that says "priced": False, unless the result
    that closed its attempt settled the attempt (Claude Code reports what it cost, whatever the model).
    Codex's turns are never settled."""
    usage = [e for e in rows if e["kind"] == "usage"]

    def whose(e: dict) -> tuple:  # one attempt: its leaf, its hold's session, its number
        return e.get("node_id"), e.get("session_id"), e["detail"].get("attempt")

    settled = {whose(e) for e in usage if "reported" in e["detail"]}
    return sum((e["detail"].get("prompt_tokens") or 0) + (e["detail"].get("completion_tokens") or 0)
               for e in usage if e["detail"].get("priced") is False and whose(e) not in settled)  # fmt: skip


def by_node(rows) -> dict[str, list[dict]]:
    """A log's rows by node id ("*" is the plan's own), oldest first."""
    out: dict[str, list[dict]] = {}
    for e in rows:
        out.setdefault(e["node_id"], []).append(e)
    return out


def agents(rows: list[dict], now: datetime) -> dict:
    """The agents' clock over a whole log: attempts running, their seconds summed, the dollars of every
    usage row, and the tokens no list price covers."""
    tries = [a for log in by_node(rows).values() for a in attempts(log, now=now)]
    usage = [e["detail"] for e in rows if e["kind"] == "usage"]
    return {
        "running": sum(a["running"] for a in tries),
        "seconds": sum(a["seconds"] for a in tries),
        "dollars": sum(u.get("dollars") or 0 for u in usage),
        "unpriced": unpriced(rows),
    }


def width(rows: list[dict], now: datetime | None = None) -> dict | None:
    """How wide a whole log ran: the most leaves with an attempt running at one moment (``most``), how
    many made one (``lanes``), and the share of agent seconds with one running alone (``alone``). None
    when none ran. An attempt runs over [start, end), to the millisecond: one that ends as another starts
    does not overlap it, in the same second or not. One that ends later does, however briefly."""
    tries = [a for log in by_node(rows).values() for a in attempts(log, now=now)]
    spans = [(datetime.fromisoformat(a["started"]).timestamp(), a["until"].timestamp()) for a in tries]
    points = sorted({x for span in spans for x in span})
    # ponytail: each stretch between two moments counts every attempt, O(n²) in attempts; fine for a night
    stretches = [(q - p, sum(s <= p < e for s, e in spans)) for p, q in itertools.pairwise(points)]
    held = sum(d * n for d, n in stretches)
    alone = sum(d for d, n in stretches if n == 1) / held if held else 1.0
    lanes = len({e["node_id"] for e in rows if e["kind"] == "attempt"})
    return {"most": max([1, *(n for _, n in stretches)]), "lanes": lanes, "alone": alone} if tries else None


def acts(rows: list[dict], person: str | None) -> list[str]:
    """The person's acts: the timestamps of their own rows, once each, oldest first."""
    # talk.mine's rule, mirrored: talk imports typer, and this module is the core's
    return sorted({e["timestamp"] for e in rows if (e["actor"] or "").split(" (")[0] == person})


def you(rows: list[dict], person: str) -> dict:
    """The person's clock, by their keys: acts are their own rows, once per timestamp (`acts`); minutes
    are the distinct minutes holding at least one act."""
    stamps = acts(rows, person)
    return {"acts": len(stamps), "minutes": len({s[:16] for s in stamps})}
