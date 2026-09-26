"""The Nemotron planner: `graphene ask --with nemotron` (and `node split`, `--about`, `:ask`).

A planner writes nothing, so its tools run here, against the repository, and only read: list, read,
grep, glob. It is started the way `graphene ask` starts any planner, with the prompt as its last
argument and GRAPHENE_PLANNER set, and it prints its answer: the fenced ``plan`` block that ``ask.py``
already reads, with any sentence after it, and a line when the model it used is not the one it was given
(``tokenfactory.resolve``). Only stdout is the answer; what it did and what it cost go to stderr, and
the bill into the plan's log.
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

from . import plan as P
from . import tokenfactory as tf
from .store import Store, repo_root

PROMPT_VERSION = 1
SYSTEM = """\
You are the planner for Graphene: a person said what they want, and you propose the tree of work that
coding agents will do, which the person prunes before anything runs. Read the repository with the tools
(list, glob, grep, read) until you know which files each piece of work must change and which command
shows it is done. Then answer with the proposal in the form the request gives, and nothing else but one
or two sentences after it for anything you could not settle. You write no file and run nothing."""


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
    """What the planner may look at: the files git tracks (and untracked ones it does not ignore)."""

    def __init__(self, root: Path):
        self.root = root
        self.files = P.in_tree(root)  # what git shows: never what it ignores (a .env), never .graphene/
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
            try:
                lines = (self.root / f).read_text(encoding="utf-8").splitlines()
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
            return f"{path} is not read: git ignores it, and what is read is sent to the model"
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


def plan(args: argparse.Namespace, prompt: str) -> int:
    here = Path.cwd()
    repo = Repo(here)
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
            "prompt": PROMPT_VERSION}  # fmt: skip
    print(f"nemotron planner · {model}", file=say, flush=True)
    answer, stopped = "", None
    try:
        for step in range(1, args.steps + 1):
            last = step == args.steps
            said = tf.chat(model, messages, None if last else TOOLS, tag="planner", **params)
            bill["calls"] += 1
            bill["prompt_tokens"] += said["usage"].get("prompt_tokens") or 0
            bill["completion_tokens"] += said["usage"].get("completion_tokens") or 0
            bill["dollars"] += said["dollars"]
            message = said["message"]
            calls = message.get("tool_calls") or []
            if not calls and said.get("finish") == "length" and params["max_tokens"] < 32_768:
                params["max_tokens"] = min(params["max_tokens"] * 2, 32_768)  # cut off: ask again, with room
                print(f"{step:>3} cut off at the token limit; again with {params['max_tokens']}", file=say)
                continue
            if not calls:
                answer = message.get("content") or ""
                if said.get("finish") == "length":
                    print("the answer was cut off at the token limit, even with more room", file=say)
                break
            messages.append({"role": "assistant", "content": message.get("content") or "",
                             "tool_calls": calls})
            for c in calls:
                result = repo.call(c["function"]["name"], c["function"].get("arguments"))
                given = str(c["function"].get("arguments", ""))[:120]
                print(f"{step:>3} {c['function']['name']} {given}", file=say)
                messages.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": result})
            if step == args.steps - 1:
                messages.append({"role": "user", "content": "Answer now with the proposal."})
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
    parser.add_argument("--steps", type=int, default=30, help="model calls at most")
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
    return f"{shlex.quote(sys.executable)} -m graphene_map.planner {rest}".strip()


if __name__ == "__main__":
    os.environ.setdefault("GRAPHENE_PLANNER", "1")
    raise SystemExit(main())
