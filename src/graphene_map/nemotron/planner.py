"""The Nemotron planner: `graphene ask --with nemotron` (and `node split`, `--about`, `:ask`).

A planner writes nothing, so its tools run here, against the repository, and only read: list, read,
grep, glob. It is started the way `graphene ask` starts any planner, with the prompt as its last
argument and GRAPHENE_PLANNER set, and it prints its answer: the fenced ``plan`` block that ``ask.py``
already reads, with any sentence after it, and a line when the model it used is not the one it was given
(``tokenfactory.resolve``). Only stdout is the answer; what it did and what it cost go to stderr, and
the bill into the plan's log.

Once the model stops calling tools, it is asked for the proposal in a strict JSON schema (``FORMAT``),
written as the plan's text (``as_text``) and tried, rolled back. A proposal Graphene refuses goes back to
the model once, with Graphene's words. The second answer is the answer.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shlex
import signal
import sys
from pathlib import Path

from .. import board as B
from .. import plan as P
from .. import plan_text as T
from ..ask import _drop_last, _pending, _Rehearsed, proposal_in
from ..store import Store, repo_root
from . import tokenfactory as tf
from .executor import text_calls

PROMPT_VERSION = 5  # 2: the board (questions with a default, assumptions, risks, leave-outs); 3: then:
# lines; 4: at most three items, each a question or a risk that changes the tree; assumptions in goals;
# 5: a check runs only its own files; the proposal is asked for as JSON in a strict schema
SYSTEM = """\
You are the planner for Graphene: a person said what they want, and you propose the tree of work that
coding agents will do, which the person prunes before anything runs. Read the repository with the tools
(list, glob, grep, read) until you know which files each piece of work must change and which command
shows it is done. Ask instead of guessing, and bring only what the repository cannot answer and what
changes the tree: for each thing the request leaves open that the code cannot settle, put a question on
the board with the default you would assume, or a risk with what you would do about it, at most three,
most important first. Never ask what a file answers; plan on the file. An assumption you are confident
of is not an item but a sentence in the goal of the leaf it bears on, and never put up an item whose
answer would change nothing. Write each leaf as the default has it; every option, and every default the
leaves do not already follow, that changes what a leaf does, which files it may touch or how it is
checked carries the then: lines that make that change (goal, scope, check, drop, leaf), so the person's
choice changes the tree. A leaf's check runs only files in its own scope and files already in the
repository. A leaf that needs a test another leaf writes waits on it with needs:. Two leaves never share a
test file: give each leaf its own, or make one tests leaf that waits on all of them. When you have read
enough, stop calling tools. You are then asked for the proposal as JSON, with the fields of the form the
request gives. Put one or two sentences to the person in says. To put lines under a node already in the
plan, name that node as their parent. You write no file and run nothing."""
_S, _N, _L = {"type": "string"}, {"type": ["string", "null"]}, {"type": "array", "items": {"type": "string"}}


def _obj(**p) -> dict:
    """An object of a strict schema: every key required, and no other."""
    return {"type": "object", "additionalProperties": False, "required": list(p), "properties": p}


_ITEM = _obj(kind={"type": "string", "enum": list(B.KINDS)}, id=_S, text=_S, default=_N, then=_L,
             options={"type": "array", "items": _obj(text=_S, then=_L)}, about=_N)  # fmt: skip
_NODE = _obj(id=_S, title=_S, goal=_S, scope=_L, check=_N, needs=_L, parent=_N,
             mark={"type": "string", "enum": ["?", "-"]})  # fmt: skip
# The order Ultra writes in. says first: last, it closed the nodes, could not end the object, and wrote
# spaces to the token limit (12 of the first 41 answers, 8 October). nodes before board: after, its then:
# and about: lines named nodes it had not given ids yet (9 of the first 20 asks)
FORMAT = {"type": "json_schema", "json_schema": {"name": "proposal", "strict": True, "schema": _obj(
    says=_S, goal=_N, nodes={"type": "array", "items": _NODE}, board={"type": "array", "items": _ITEM})}}


def _tool(name: str, description: str, required: tuple[str, ...] = (), **properties: str) -> dict:
    props = {k: {"type": "integer" if v == "int" else "string", "description": v}
             for k, v in properties.items()}  # fmt: skip
    schema = {"type": "object", "properties": props, "required": list(required)}
    return {"type": "function", "function": {"name": name, "description": description, "parameters": schema}}


TOOLS = [
    _tool("list", "List a directory of the repository.", path="repo-relative; '.' is the repository"),
    _tool("glob", "The files matching a glob, e.g. src/**/*.py", ("pattern",), pattern="the glob"),
    _tool("grep", "The lines matching a regular expression.", ("pattern",), pattern="a regular expression",
          glob="which files to search (a glob; all by default)"),
    _tool("read", "A file, with line numbers.", ("path",), path="repo-relative", start="int", end="int"),
]

READ_LINES = 400
HITS = 200


class Repo:
    """What the planner may look at: the files git tracks (and untracked ones it does not ignore), less
    the protected paths the person named in `graphene config` (``hidden``)."""

    def __init__(self, root: Path, hidden: list[str] = ()):
        self.root = root
        files = P.in_tree(root)  # what git shows: never what it ignores (a .env), never .graphene/
        self.files = [f for f in files if not P.covers(list(hidden), f)]
        self.shown = set(self.files)

    def _inside(self, path: str) -> Path | None:
        full = (self.root / (path or ".")).resolve()
        return full if full.is_relative_to(self.root.resolve()) and ".git" not in full.parts else None

    def list(self, path: str = ".") -> str:
        full = self._inside(path)
        if full is None or not full.is_dir():
            return f"{path} is not a directory of this repository"
        prefix = "" if full == self.root.resolve() else str(full.relative_to(self.root.resolve())) + "/"
        rests = [f[len(prefix) :] for f in self.files if f.startswith(prefix)]
        names = sorted({r.split("/")[0] + ("/" if "/" in r else "") for r in rests})
        return "\n".join(names) or "(empty)"

    def glob(self, pattern: str) -> str:
        hits = [f for f in self.files if fnmatch.fnmatch(f, pattern) or P.in_scope(f, [pattern])]
        more = f"\n… {len(hits) - HITS} more" if len(hits) > HITS else ""
        return "\n".join(hits[:HITS]) + more if hits else "(none)"

    def grep(self, pattern: str, glob: str = "**") -> str:
        try:
            find = re.compile(pattern)
        except re.error as no:
            return f"not a regular expression: {no}"
        hits: list[str] = []
        for f in self.files:
            if glob not in ("**", "*", "") and not (fnmatch.fnmatch(f, glob) or P.in_scope(f, [glob])):
                continue
            full = self._inside(f)  # a tracked link is read as what it reaches, as read() does
            if full is None or str(full.relative_to(self.root.resolve())) not in self.shown:
                continue
            try:
                lines = full.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            hits += [f"{f}:{k}: {line.strip()[:200]}" for k, line in enumerate(lines, 1) if find.search(line)]
            if len(hits) >= HITS:
                return "\n".join(hits[:HITS]) + "\n… (more; narrow the pattern or the glob)"
        return "\n".join(hits) or "(no match)"

    def read(self, path: str, start: int | None = None, end: int | None = None) -> str:
        full = self._inside(path)
        if full is None or not full.is_file():
            return f"{path} is not a file of this repository"
        if str(full.relative_to(self.root.resolve())) not in self.shown:
            return f"{path} is not read: git ignores it or it is protected; what is read goes to the model"
        lines = full.read_text(encoding="utf-8", errors="replace").split("\n")
        first = max(1, start or 1)
        last = min(len(lines), end or first + READ_LINES - 1)
        more = f"\n(lines {last + 1}-{len(lines)} not shown)" if last < len(lines) else ""
        return "\n".join(f"{k:>5}  {lines[k - 1]}" for k in range(first, last + 1)) + more

    def call(self, name: str, arguments) -> str:
        tool = {"list": self.list, "glob": self.glob, "grep": self.grep, "read": self.read}.get(name)
        if tool is None:
            return f"there is no tool {name!r}; the tools are list, glob, grep, read; it writes nothing"
        try:
            args = json.loads(arguments or "{}") if isinstance(arguments, str) else dict(arguments or {})
            return tool(**args)
        except (ValueError, TypeError) as no:
            return f"{name} could not take those arguments ({no})"


def _protected(here: Path) -> list[str]:
    """The protected globs the person set (`graphene config`): never read, so never sent to the model."""
    from .. import settings

    try:
        with Store.open(repo_root(here)) as store:
            return settings.protected(store)
    except Exception:  # no store to read: nothing was ever protected in it
        return []


def _flat(v):
    """Every string in it as one line: a line break would end its line in the plan's text."""
    if isinstance(v, dict | list):
        return {k: _flat(x) for k, x in v.items()} if isinstance(v, dict) else [_flat(x) for x in v]
    return B._one(v) if isinstance(v, str) else v


def as_text(p: dict) -> str:
    """A proposal in ``FORMAT`` as the plan's text, which `graphene ask` reads from every planner. A
    node's place is its parent: line. A node's goal keeps its lines, as the plan keeps them."""
    goals = [T._norm_goal(n["goal"] or "") for n in p["nodes"]]
    p = _flat({**p, "nodes": [{**n, "check": T._norm_check(n["check"])} for n in p["nodes"]]})
    out, taken = [f"goal: {p['goal']}"] if p["goal"] else [], {n["id"] for n in p["nodes"]}
    for it in p["board"]:  # an item's id is a handle nothing in the answer names: made one when it is not
        it = it if T._VALID_ID.fullmatch(it["id"]) else {**it, "id": T.slug(it["id"], taken, "item")}
        taken.add(it["id"])
        out += B.lines({**it, "state": "open"})
    for n, goal in zip(p["nodes"], goals, strict=True):
        out.append(f"{'-' if n['mark'] == '-' else '?'} {n['title']}  [{n['id']}]")
        own = {"scope": T._globs(n["scope"]), "check": n["check"], "needs": ", ".join(n["needs"]),
               "parent": n["parent"]}  # fmt: skip
        out += [f"    goal: {line}" for line in goal]
        out += [f"    {key}: {value}" for key, value in own.items() if value]
    return "\n".join(out) + "\n"


def _answer(raw: str) -> tuple[str, str]:
    """The proposal's text, and what to print: the fenced block with says after it, or an answer that is
    not that JSON (a stand-in's) as it is."""
    try:
        p = json.loads(raw)
        text = as_text(p)
        return text, f"```plan\n{text}```\n{B._one(p['says'])}"
    except (ValueError, TypeError, KeyError, AttributeError):
        return proposal_in(raw), raw


def _refused(root: Path, text: str, files: list[str]) -> str | None:
    """Graphene's refusal of the proposal, applied as `graphene ask` applies it and rolled back, or None.
    A re-ask drops the tree it replaces first (GRAPHENE_REPLACES), and what a merge or a re-ask replaces
    may share the new leaves' paths (GRAPHENE_BESIDE), as `graphene ask` has it."""
    replaces = os.environ.get("GRAPHENE_REPLACES") or None
    try:
        with Store.open(repo_root(root)) as store, store.claim():
            _drop_last(store, replaces, P.Caller(P.person_name(), True))  # as `graphene ask`: the person
            left = {n.id for n in _pending(store, replaces)}  # what of the last tree stays
            beside = {*os.environ.get("GRAPHENE_BESIDE", "").split(), *left}
            T.apply(store, text, P.Caller("planner:nemotron", False), None, files=files, beside=beside)
            raise _Rehearsed
    except _Rehearsed:
        return None
    except P.Refused as no:
        return str(no)
    except Exception as no:  # noqa: BLE001  (the answer is paid for: `graphene ask` reads it either way)
        print(f"(the proposal was not tried: {no})", file=sys.stderr)
        return None


def plan(args: argparse.Namespace, prompt: str) -> int:
    here = Path.cwd()
    repo = Repo(here, _protected(here))
    say = sys.stderr
    try:  # the id the live list has: the largest Nemotron by default, a retired one's nearest
        chosen, instead = tf.resolve([args.model] if args.model else [], "planner")
    except tf.Unreachable as no:
        print(f"stopped: {no}", file=say)
        return 3
    if not chosen:
        print("stopped: Token Factory lists no Nemotron model for this key", file=say)
        return 3
    model = chosen[0]
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
    params = {"temperature": args.temperature, "max_tokens": args.max_tokens,
              **{k: json.loads(v) for k, v in (p.split("=", 1) for p in args.param)}}  # fmt: skip
    bill = {"model": model, "calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "dollars": 0.0,
            "prompt": PROMPT_VERSION, "endpoint": tf.endpoint()}  # fmt: skip
    print(f"nemotron planner · {model}", file=say, flush=True)

    def asked(tools: list | None = None, **strict) -> tuple[dict, list]:
        """One call, on the bill, and its tool calls. Cut off with no call, it is asked again with room."""
        while True:
            said = tf.chat(model, messages, tools, tag="planner", **params, **strict)
            bill["calls"] += 1
            bill["prompt_tokens"] += said["usage"].get("prompt_tokens") or 0
            bill["completion_tokens"] += said["usage"].get("completion_tokens") or 0
            bill["dollars"] += said["dollars"]
            message = said["message"]
            calls = message.get("tool_calls") or (text_calls(message.get("content")) if tools else [])
            if calls or said.get("finish") != "length":
                return message, calls
            if params["max_tokens"] >= 32_768:
                print("the answer was cut off at the token limit, even with more room", file=say)
                return message, calls
            params["max_tokens"] = min(params["max_tokens"] * 2, 32_768)
            print(f"cut off at the token limit; again with {params['max_tokens']}", file=say)

    answer, stopped = "", None
    try:
        for step in range(1, args.steps):
            message, calls = asked(TOOLS)
            native = message.get("tool_calls") or []
            messages.append({"role": "assistant", "content": message.get("content") or "",
                             **({"tool_calls": native} if native else {})})
            if not calls:
                break  # its draft: the proposal is asked for next, as JSON
            for c in calls:
                result = repo.call(c["function"]["name"], c["function"].get("arguments"))
                given = str(c["function"].get("arguments", ""))[:120]
                print(f"{step:>3} {c['function']['name']} {given}", file=say)
                if native:
                    messages.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": result})
                else:  # as the executor answers a call written as text
                    said_back = f"Result of {c['function']['name']}:\n{result}"
                    messages.append({"role": "user", "content": said_back})
        messages.append({"role": "user", "content": "Answer now with the proposal. Write it as JSON."})
        raw = asked(response_format=FORMAT)[0].get("content") or ""
        text, answer = _answer(raw)
        no = _refused(here, text, P.tracked(here))  # git first, never under the plan's lock
        if no:  # once, with Graphene's words; the second answer is the answer
            bill["sent_back"] = no
            lines = "\n".join(f"{k:>5}  {line}" for k, line in enumerate(text.splitlines(), 1))
            messages += [{"role": "assistant", "content": raw}, {"role": "user", "content": (
                f"Graphene could not read the proposal: {no}\nIt read your JSON as:\n{lines}\n"
                "Answer again with the whole proposal.")}]  # fmt: skip
            text, answer = _answer(asked(response_format=FORMAT)[0].get("content") or "")
    except tf.Unreachable as no:
        stopped = no
    finally:
        bill["dollars"] = round(bill["dollars"], 6)
        print(f"bill: {bill['calls']} calls, {bill['prompt_tokens']} in, {bill['completion_tokens']} out, "
              f"${bill['dollars']:.4f} at list price", file=say, flush=True)  # fmt: skip
        try:
            with Store.open(repo_root(here)) as store:
                store.log_node("*", P._now(), "usage", "planner:nemotron", None, None, bill)
        except Exception as no:  # the answer matters more than its bill
            print(f"(the bill was not recorded: {no})", file=say)
    if stopped is not None:  # its last line, after the bill: `graphene ask` says the last line it printed
        print(f"stopped: {stopped}", file=say)
        return 3
    print(answer)
    if answer.strip():  # after the proposal, where `graphene ask` shows what the planner says
        for line in instead:
            print(line)
    return 0 if answer.strip() else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="graphene-nemotron-planner", description=__doc__.split("\n")[0])
    parser.add_argument("--model", help="a model id in Token Factory's list (default: the largest Nemotron)")
    parser.add_argument("--steps", type=int, default=30, help="tool steps at most, then the answer")
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--param", action="append", default=[], help="KEY=JSON, sent in the request as is")
    parser.add_argument("prompt")
    args = parser.parse_args(argv)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    return plan(args, args.prompt)


def template(spec: str) -> str:
    """`nemotron [options]` as the command `graphene ask` starts."""
    rest = spec.split(None, 1)[1] if len(spec.split(None, 1)) > 1 else ""
    return f"{shlex.quote(sys.executable)} -m graphene_map.nemotron.planner {rest}".strip()


if __name__ == "__main__":
    os.environ.setdefault("GRAPHENE_PLANNER", "1")
    raise SystemExit(main())
