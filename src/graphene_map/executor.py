"""The Nemotron executor: Graphene's own loop, run here against Token Factory, with every tool it
calls run in the leaf's placement.

`graphene run --with nemotron …` starts it for one leaf, as it starts any executor: in the leaf's
checkout, with GRAPHENE_NODE set and the leaf's contract as its last argument. It asks a Nemotron model
for one tool call at a time (view, edit, write, run, done, release) and runs it. Three layers hold it:

1. edit and write refuse a path outside the leaf's scope before touching it, in the words the Claude
   Code hooks use (``gate.scope_refused``), logged where a hand-back's offers are read from;
2. in a sandbox, commands run as an unprivileged user who can write only the scope (``sandbox.py``);
   in the local placement there is no second layer, and a shell command is caught at `done`;
3. `done` is Graphene's own (`graphene node done`): git and the check decide, never the model.

The key stays in this process: a command the model runs gets an environment without it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import gate
from . import plan as P
from . import tokenfactory as tf
from .sources.claude_code import repo_root
from .store import Store

PROMPT_VERSION = 1
SYSTEM = """\
You are an executor for Graphene: you do exactly one leaf of a plan a person shaped, in a git repository.
You work only through the tools. Read what you need (view, run); change files with edit or write, only
inside the leaf's scope (a write outside it is refused). Run the leaf's check yourself with run before you
finish. When the check passes, call done: Graphene runs the check again and asks git what changed. If
done refuses, read why, fix it, and call done again. If the leaf cannot be done inside its scope, call
release with the reason and the paths you would need; the person decides. Keep each step small."""

NUDGE = "Use a tool. When the leaf is done call done; if it cannot be done inside its scope, call release."

TOOLS = [
    {"type": "function", "function": {
        "name": "view", "description": "Read a file (with line numbers) or list a directory.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "repo-relative path; '.' is the repo"},
            "start": {"type": "integer", "description": "first line (optional)"},
            "end": {"type": "integer", "description": "last line (optional)"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "edit", "description": "Replace one exact occurrence of old with new in a file.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}},
            "required": ["path", "old", "new"]}}},
    {"type": "function", "function": {
        "name": "write", "description": "Create a file, or replace all of it.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "run", "description": "Run a bash command in the repository; see its exit code and output.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}},
                       "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "done", "description": "Finished: Graphene runs the check and asks git what changed.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "release", "description": "Hand the leaf back unfinished, saying why and naming the paths "
        "outside its scope it would need.",
        "parameters": {"type": "object", "properties": {
            "why": {"type": "string"}, "wants": {"type": "array", "items": {"type": "string"}}},
            "required": ["why"]}}},
]  # fmt: skip

VIEW_LINES = 400
OUTPUT = 8_000  # characters of a command's output the model is shown: its tail, where the result is
KEEP = 150_000  # characters of history before the oldest tool results are cut to a line
RUN_TIMEOUT = 300


class Local:
    """The leaf's own checkout, where commands run as the person's user. Held before the write by the
    tools and at `done` by git; nothing stops a shell command from writing outside the scope until then.
    """

    name = "local"

    def __init__(self, root: Path):
        self.root = root

    def read(self, rel: str) -> bytes:
        return (self.root / rel).read_bytes()

    def write(self, rel: str, data: bytes) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def run(self, command: str, timeout: int = RUN_TIMEOUT) -> tuple[int, str]:
        env = {k: v for k, v in os.environ.items() if k != tf.KEY}  # model-written code never sees the key
        proc = subprocess.Popen(
            ["bash", "-c", command], cwd=self.root, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
        )  # fmt: skip
        try:
            out, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            out, _ = proc.communicate()
            return 124, out.decode("utf-8", "replace") + f"\n(stopped after {timeout} s)"
        return proc.returncode, out.decode("utf-8", "replace")

    def close(self) -> None:
        pass


class Leaf:
    """One leaf's tools, as the model calls them."""

    def __init__(self, store: Store, node: P.Node, place, repo: Path, session: str):
        self.store, self.node, self.place, self.repo, self.session = store, node, place, repo, session
        self.finished = False
        self.refused = 0

    def _rel(self, path: str) -> tuple[str | None, str | None]:
        """The repo-relative path, or why a write there is refused before anything is touched."""
        here = self.place.root
        full = os.path.normpath(os.path.join(here, path))
        rel = os.path.relpath(full, here)
        if rel == "." or rel.startswith(".."):
            return None, f"{path} is not in this repository; no scope covers it"
        if rel.split("/", 1)[0] in (*gate.OURS, ".git"):
            return None, f"{rel} is Graphene's or git's own; no leaf's scope covers it"
        if gate._leaves(full, self.repo, str(here)):
            return None, f"{rel} is a symbolic link that leaves the repo; no scope covers where it points"
        return rel, None

    def _may_write(self, path: str, how: str) -> tuple[str | None, str | None]:
        rel, no = self._rel(path)
        if no is None:
            no = gate.scope_refused(self.store, [self.node], rel, self.session, how)
        if no is not None:
            self.refused += 1
        return rel, no

    def view(self, path: str = ".", start: int | None = None, end: int | None = None) -> str:
        full = (self.place.root / path).resolve()
        if not full.is_relative_to(self.place.root.resolve()):  # what is read is sent to the model
            return f"{path} is not in this repository; only the repository is read"
        if full.is_dir():
            names = sorted(p.name + ("/" if p.is_dir() else "") for p in full.iterdir() if p.name != ".git")
            return "\n".join(names) or "(empty)"
        try:
            data = self.place.read(os.path.relpath(full, self.place.root))
            lines = data.decode("utf-8", "replace").split("\n")
        except OSError as no:
            return f"cannot read {path}: {no.strerror}"
        first = max(1, start or 1)
        last = min(len(lines), end or first + VIEW_LINES - 1)
        shown = [f"{k:>5}  {lines[k - 1]}" for k in range(first, last + 1)]
        more = f"\n(lines {last + 1}-{len(lines)} not shown)" if last < len(lines) else ""
        return "\n".join(shown) + more

    def edit(self, path: str, old: str, new: str) -> str:
        rel, no = self._may_write(path, "edit")
        if no:
            return no
        try:
            text = self.place.read(rel).decode("utf-8")
        except (OSError, UnicodeDecodeError) as no:
            return f"cannot read {rel}: {getattr(no, 'strerror', no)}; write creates a file"
        count = text.count(old) if old else 0
        if count != 1:
            return f"old is in {rel} {count} times; it must be exactly once (view the file, copy the lines)"
        self.place.write(rel, text.replace(old, new, 1).encode())
        return f"edited {rel}"

    def write(self, path: str, content: str) -> str:
        rel, no = self._may_write(path, "write")
        if no:
            return no
        self.place.write(rel, content.encode())
        return f"wrote {rel} ({len(content.splitlines())} lines)"

    def run(self, command: str) -> str:
        code, out = self.place.run(command)
        tail = out[-OUTPUT:]
        cut = f"(first {len(out) - OUTPUT} characters not shown)\n" if len(out) > OUTPUT else ""
        return f"exit {code}\n{cut}{tail}"

    def _graphene(self, *args: str) -> str:
        cli = "import sys; from graphene_map.cli import app; sys.argv[0] = 'graphene'; app()"
        env = {k: v for k, v in os.environ.items() if k != tf.KEY}  # the check runs model-written code
        said = subprocess.run([sys.executable, "-c", cli, *args], cwd=self.place.root, capture_output=True,
                              text=True, env=env)  # fmt: skip
        return (said.stdout + said.stderr).strip()

    def done(self) -> str:
        said = self._graphene("node", "done", self.node.id)
        self.finished = P.get(self.store, self.node.id).state in (P.DONE, P.REVIEW)
        return said

    def release(self, why: str = "", wants: list[str] | None = None) -> str:
        said = self._graphene("node", "release", self.node.id, "--why", why or "(no reason given)",
                              *[a for w in wants or [] for a in ("--wants", w)])  # fmt: skip
        self.finished = P.get(self.store, self.node.id).state != P.RUNNING
        return said

    def call(self, name: str, arguments: str | dict | None) -> str:
        tool = {"view": self.view, "edit": self.edit, "write": self.write, "run": self.run,
                "done": self.done, "release": self.release}.get(name)  # fmt: skip
        if tool is None:
            return f"there is no tool {name!r}; the tools are view, edit, write, run, done, release"
        try:
            args = json.loads(arguments or "{}") if isinstance(arguments, str) else dict(arguments or {})
            return tool(**args)
        except (ValueError, TypeError) as no:
            return f"{name} could not take those arguments ({no}); send them as JSON with the named fields"


_TEXT_CALL = re.compile(r"```tool\s*\n(.*?)\n```", re.DOTALL)
TEXT_PROTOCOL = """
Call a tool by writing a fenced block, one per message, and nothing after it:
```tool
{"name": "view", "arguments": {"path": "src/app.py"}}
```
The tools: view(path, start?, end?), edit(path, old, new), write(path, content), run(command), done(),
release(why, wants?)."""


def text_calls(content: str | None) -> list[dict]:
    """Tool calls written as fenced text, for a model whose native calls misfire."""
    out = []
    for k, block in enumerate(_TEXT_CALL.findall(content or "")):
        try:
            said = json.loads(block)
            given = json.dumps(said.get("arguments") or {})
            out.append({"id": f"text_{k}", "function": {"name": said["name"], "arguments": given}})
        except (ValueError, KeyError, TypeError):
            continue
    return out


def _compact(messages: list[dict]) -> None:
    """Keep the history under KEEP characters by cutting the oldest tool results to one line.
    TODO: a plain cut; a summary of what was learned would keep more for a long leaf."""
    size = sum(len(json.dumps(m)) for m in messages)
    for m in messages[2:]:
        if size <= KEEP:
            return
        if m.get("role") == "tool" and len(m.get("content") or "") > 200:
            size -= len(m["content"]) - 60
            m["content"] = m["content"][:60] + " …(cut to save room)"


def attempt_number(store: Store, node: P.Node) -> int:
    """Which attempt of this hold this is (1, 2, …): the escalation ladder climbs by it."""
    log = store.node_log(node.id)
    began = max((k for k, e in enumerate(log) if e["kind"] == "started"), default=-1)
    return max(1, sum(1 for e in log[began + 1 :] if e["kind"] == "attempt"))


def in_scope_files(root: Path, scope: list[str], budget: int) -> str:
    """The tracked files in the scope, inlined up to ``budget`` characters, for a small model."""
    out, left = [], budget
    for rel in P.tracked(root):
        if not P.in_scope(rel, scope):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if len(text) > left:
            out.append(f"--- {rel} (not inlined: {len(text)} characters; view it)")
            continue
        left -= len(text)
        out.append(f"--- {rel}\n{text}")
    return "\n".join(out)


def work(args: argparse.Namespace, prompt: str) -> int:
    node_id = os.environ.get("GRAPHENE_NODE")
    if not node_id:
        print("the Nemotron executor is started by `graphene run`, which names the leaf (GRAPHENE_NODE)")
        return 2
    here = Path.cwd()
    repo = repo_root(here)
    session = os.environ.get("GRAPHENE_ATTEMPT", "")
    with Store.open(repo) as store:
        node = P.get(store, node_id)
        if not args.model:  # the smallest Nemotron the live list has
            try:
                listed = tf.roles()
            except tf.Unreachable as no:
                print(f"stopped: {no}", flush=True)
                return 3
            args.model = [listed[k] for k in ("nano", "super", "ultra") if k in listed][:1]
        if not args.model:
            print("stopped: Token Factory lists no Nemotron model for this key", flush=True)
            return 3
        ladder = args.model
        model = ladder[min(attempt_number(store, node), len(ladder)) - 1]
        try:
            place = Local(here) if args.placement == "local" else _sandbox(here, node, store, session)
        except (RuntimeError, ImportError, OSError) as no:
            print(f"stopped: the sandbox could not be made: {no}", flush=True)
            return 3
        leaf = Leaf(store, node, place, repo, session)
        first = [prompt]
        if args.map:
            files = P.tracked(here)
            more = "\n…" if len(files) > 400 else ""
            first.append("The repository's files:\n" + "\n".join(files[:400]) + more)
        if args.inline:
            inlined = in_scope_files(here, node.scope, args.inline)
            first.append("The files in your scope, as they are now:\n" + inlined)
        system = SYSTEM + (TEXT_PROTOCOL if args.protocol == "text" else "")
        messages = [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(first)}]
        params = {"temperature": args.temperature, "max_tokens": args.max_tokens,
                  **{k: json.loads(v) for k, v in (p.split("=", 1) for p in args.param)}}  # fmt: skip
        bill = {"model": model, "calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "dollars": 0.0,
                "seconds": 0.0, "prompt": PROMPT_VERSION}  # fmt: skip
        print(f"nemotron executor · {model} · {place.name} placement · leaf {node.id}", flush=True)
        nudged = 0
        try:
            for step in range(1, args.steps + 1):
                _compact(messages)
                said = tf.chat(model, messages, TOOLS if args.protocol == "native" else None, tag=node.id,
                               **params)  # fmt: skip
                bill["calls"] += 1
                bill["prompt_tokens"] += said["usage"].get("prompt_tokens") or 0
                bill["completion_tokens"] += said["usage"].get("completion_tokens") or 0
                bill["dollars"] += said["dollars"]
                bill["seconds"] += said["seconds"]
                message = said["message"]
                native = message.get("tool_calls") or []
                calls = native or (text_calls(message.get("content")) if args.protocol == "text" else [])
                print(f"{step:>3} {model.rsplit('/', 1)[-1]} answered in {said['seconds']:.2f} s", flush=True)
                if message.get("content"):
                    print(f"{step:>3} says: {' '.join(str(message['content']).split())[:200]}", flush=True)
                kept = {"role": "assistant", "content": message.get("content") or ""}
                if native:
                    kept["tool_calls"] = native
                messages.append(kept)
                if not calls:
                    nudged += 1
                    if nudged > 2:
                        print(f"{step:>3} stopped: no tool call three times", flush=True)
                        break
                    messages.append({"role": "user", "content": NUDGE})
                    continue
                for c in calls:
                    name = c["function"]["name"]
                    began = time.monotonic()
                    result = leaf.call(name, c["function"].get("arguments"))
                    took = time.monotonic() - began
                    first_line = result.split("\n", 1)[0][:160]
                    brief = _brief(c["function"].get("arguments"))
                    print(f"{step:>3} {name} {brief} → {first_line} ({took:.2f} s)", flush=True)
                    if native:
                        messages.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": result})
                    else:
                        messages.append({"role": "user", "content": f"Result of {name}:\n{result}"})
                    if leaf.finished:
                        return 0
            return 0
        except tf.Unreachable as no:
            print(f"stopped: {no}", flush=True)
            return 3
        finally:
            place.close()
            bill["refused"] = leaf.refused
            bill["dollars"] = round(bill["dollars"], 6)
            store.log_node(node.id, P._now(), "usage", f"run:{NAME}", session or None, None, bill)
            print(f"bill: {bill['calls']} calls, {bill['prompt_tokens']} in, "
                  f"{bill['completion_tokens']} out, ${bill['dollars']:.4f} at list price, "
                  f"{leaf.refused} writes refused", flush=True)  # fmt: skip


def _brief(arguments) -> str:
    try:
        said = json.loads(arguments) if isinstance(arguments, str) else dict(arguments or {})
    except ValueError:
        return "(arguments not JSON)"
    return " ".join(str(said.get(k))[:80] for k in ("path", "command", "why") if said.get(k))


def _sandbox(here: Path, node: P.Node, store: Store, session: str):
    """The leaf's sandbox, and a note in its record of where it is, so that its check (whoever runs
    `done`) runs in a fork of the same sandbox."""
    from . import sandbox

    name = os.environ.get("GRAPHENE_SANDBOX") or "contree"
    place = sandbox.Sandbox(here, node.scope, sandbox.choose(name), store, node.id)
    store.log_node(node.id, P._now(), "placement", f"run:{NAME}", session or None, None,
                   {"placement": "sandbox", "box": name, "image": place.base,
                    "seconds": round(place.timings[0], 3)})  # fmt: skip
    print(f"sandbox ready ({name}, {place.timings[0]:.1f} s): image {place.base[:12]}", flush=True)
    return place


NAME = "nemotron"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="graphene-nemotron", description=__doc__.split("\n")[0])
    parser.add_argument("--model", action="append", default=[], help="a model id; again for the next attempt")
    parser.add_argument("--placement", choices=("local", "sandbox"), default="local")
    parser.add_argument("--steps", type=int, default=40, help="model calls at most")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--param", action="append", default=[], help="KEY=JSON, sent in the request as is")
    parser.add_argument("--map", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--inline", type=int, default=0, help="inline the scope's files, up to N characters")
    parser.add_argument("--protocol", choices=("native", "text"), default="native")
    parser.add_argument("prompt")
    args = parser.parse_args(argv)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))  # a stopped run: the bill is still written
    return work(args, args.prompt)


def template(spec: str) -> str:
    """`nemotron [options]` as the command `graphene run` starts."""
    rest = spec.split(None, 1)[1] if len(spec.split(None, 1)) > 1 else ""
    return f"{shlex.quote(sys.executable)} -m graphene_map.executor {rest}".strip()


if __name__ == "__main__":
    raise SystemExit(main())
