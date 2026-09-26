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

What a screen shows of it is written on the leaf's log as it happens: each attempt's model as the attempt
begins (`model`; on a step up the ladder, with the model before and why), each fork's state when it
starts and when it ends (`fork`), and in a sandbox its checkpoint, operations and seconds (`placement`,
and on each fork's row).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from . import gate
from . import plan as P
from . import tokenfactory as tf
from .run import GRACE, REFUSED
from .store import Store, repo_root

PROMPT_VERSION = 1
SYSTEM = """\
You are an executor for Graphene: you do exactly one leaf of a plan a person shaped, in a git repository.
You work only through the tools. Read what you need (view, run); change files with edit or write, only
inside the leaf's scope (a write outside it is refused). Run the leaf's check yourself with run before you
finish. When the check passes, call done: Graphene runs the check again and asks git what changed. If
done refuses, read why, fix it, and call done again. If the leaf cannot be done inside its scope, call
release with the reason and the paths you would need; the person decides. Keep each step small."""

NUDGE = "Use a tool. When the leaf is done call done; if it cannot be done inside its scope, call release."
CUT = "Your answer was cut off at the token limit. Think less, and call one tool."
LARGER = "or name a larger model with another --model"  # what a person can do when the model gives up

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

# The names a small model was trained to call its tools by, and their arguments: a call spelled so is
# the tool it means, not a wasted turn. TODO: which of these Nemotron uses is not measured yet.
ALIASES = {"read_file": "view", "read": "view", "cat": "view", "open": "view", "str_replace": "edit",
           "str_replace_editor": "edit", "replace": "edit", "write_file": "write", "create_file": "write",
           "bash": "run", "shell": "run", "execute": "run", "finish": "done", "submit": "done"}  # fmt: skip
ARGS = {"file_path": "path", "filePath": "path", "filename": "path", "file": "path", "old_str": "old",
        "old_string": "old", "oldString": "old", "new_str": "new", "new_string": "new", "newString": "new",
        "text": "content", "file_text": "content", "cmd": "command", "reason": "why"}  # fmt: skip

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
        self.proc: subprocess.Popen | None = None  # the command running now

    def read(self, rel: str) -> bytes:
        return (self.root / rel).read_bytes()

    def write(self, rel: str, data: bytes) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def run(self, command: str, timeout: int = RUN_TIMEOUT) -> tuple[int, str]:
        env = {k: v for k, v in os.environ.items() if k != tf.KEY}  # model-written code never sees the key
        proc = self.proc = subprocess.Popen(
            ["bash", "-c", command], cwd=self.root, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
        )  # fmt: skip
        try:
            out, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            out, _ = proc.communicate()
            return 124, out.decode("utf-8", "replace") + f"\n(stopped after {timeout} s)"
        except BaseException:  # a stopped run: nothing the model started outlives it
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            raise
        return proc.returncode, out.decode("utf-8", "replace")

    def halt(self) -> None:
        """The run was stopped while a fork's thread waits on its command: end it, and all it started."""
        if self.proc is not None and self.proc.returncode is None:
            with contextlib.suppress(OSError):  # it ended just now
                os.killpg(self.proc.pid, signal.SIGKILL)

    def close(self) -> None:
        pass


class Leaf:
    """One leaf's tools, as the model calls them."""

    def __init__(self, store: Store, node: P.Node, place, repo: Path, session: str):
        self.store, self.node, self.place, self.repo, self.session = store, node, place, repo, session
        self.source = place.root  # the git checkout its files come from (a fork's copy has no .git)
        self.finished = False
        self.ended = ""  # how its conversation ended (converse says)
        self.refused = 0
        self.wrote: dict[str, str] = {}  # path -> how: its own edit or write, or a command in a sandbox

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
        here = self.place.root.resolve()
        if not full.is_relative_to(here):  # what is read is sent to the model
            return f"{path} is not in this repository; only the repository is read"
        shown = _shown(self.place.root, self.source)  # never what git ignores (a .env), never .graphene/
        rel = str(full.relative_to(here))
        if full.is_dir():
            prefix = "" if rel == "." else rel + "/"
            rests = [f[len(prefix) :] for f in shown if f.startswith(prefix)]
            names = sorted({r.split("/")[0] + ("/" if "/" in r else "") for r in rests})
            return "\n".join(names) or "(empty)"
        if rel not in shown:
            return f"{path} is not read: git ignores it or it is not there (what is read goes to the model)"
        try:
            data = self.place.read(rel)  # not relative to the root as given: a fork's copy is behind a link
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
        self.wrote[rel] = "edit"
        return f"edited {rel}"

    def write(self, path: str, content: str) -> str:
        rel, no = self._may_write(path, "write")
        if no:
            return no
        self.place.write(rel, content.encode())
        self.wrote[rel] = "edit"
        return f"wrote {rel} ({len(content.splitlines())} lines)"

    def run(self, command: str) -> str:
        code, out = self.place.run(command)
        for rel in getattr(self.place, "brought", ()):  # what a command changed in the sandbox, brought here
            self.wrote.setdefault(rel, "shell")
        tail = out[-OUTPUT:]
        cut = f"(first {len(out) - OUTPUT} characters not shown)\n" if len(out) > OUTPUT else ""
        return f"exit {code}\n{cut}{tail}"

    def _graphene(self, *args: str) -> str:
        """`graphene …` for this leaf. It is Graphene's own process and keeps the key: a sandbox leaf's
        check is forked in ConTree from there. The check itself never gets it (plan.run_check drops it
        here; in a sandbox nothing of the environment goes in)."""
        cli = "import sys; from graphene_map.cli import app; sys.argv[0] = 'graphene'; app()"
        said = subprocess.run([sys.executable, "-c", cli, *args], cwd=self.place.root, capture_output=True,
                              text=True, env=dict(os.environ))  # fmt: skip
        return (said.stdout + said.stderr).strip()

    def done(self) -> str:
        said = self._graphene("node", "done", self.node.id)
        self.finished = P.get(self.store, self.node.id).state in (P.DONE, P.REVIEW)
        return said

    def release(self, why: str = "", wants: list[str] | str | None = None) -> str:
        wants = [wants] if isinstance(wants, str) else wants  # one path, not its letters
        said = self._graphene("node", "release", self.node.id, "--why", why or "(no reason given)",
                              *[a for w in wants or [] for a in ("--wants", w)])  # fmt: skip
        self.finished = P.get(self.store, self.node.id).state != P.RUNNING
        return said

    def call(self, name: str, arguments: str | dict | None) -> str:
        name = ALIASES.get(name, name)
        tool = {"view": self.view, "edit": self.edit, "write": self.write, "run": self.run,
                "done": self.done, "release": self.release}.get(name)  # fmt: skip
        if tool is None:
            return f"there is no tool {name!r}; the tools are view, edit, write, run, done, release"
        try:
            args = json.loads(arguments or "{}") if isinstance(arguments, str) else dict(arguments or {})
            if isinstance(args, str):  # encoded twice
                args = json.loads(args or "{}")
            if not isinstance(args, dict):
                return f"{name} takes a JSON object of named fields"
            args = {ARGS.get(k, k): v for k, v in args.items() if v is not None}  # null: not given
            return tool(**args)
        except (ValueError, TypeError, AttributeError) as no:  # a field of the wrong type, too
            return f"{name} could not take those arguments ({no}); send them as JSON with the named fields"


_TEXT_CALL = re.compile(r"```tool\s*\n(.*?)\n```", re.DOTALL)
TEXT_PROTOCOL = """
Call a tool by writing a fenced block, one per message, and nothing after it:
```tool
{"name": "view", "arguments": {"path": "src/app.py"}}
```
The tools: view(path, start?, end?), edit(path, old, new), write(path, content), run(command), done(),
release(why, wants?)."""


_NATIVE_CALL = re.compile(r"<TOOLCALL>\s*(.*?)\s*</TOOLCALL>", re.DOTALL)


def text_calls(content: str | None) -> list[dict]:
    """Tool calls written as text: a fenced ```tool block (``--protocol text``), or Nemotron's own
    `<TOOLCALL>[{"name": …, "arguments": {…}}]</TOOLCALL>` when a server hands it back as text."""
    found: list[dict] = []
    for block in _TEXT_CALL.findall(content or ""):
        try:
            found.append(json.loads(block))
        except ValueError:
            continue
    for block in _NATIVE_CALL.findall(content or ""):
        try:
            said = json.loads(block)
        except ValueError:
            continue
        found += said if isinstance(said, list) else [said]
    out = []
    for k, said in enumerate(found):
        if isinstance(said, dict) and isinstance(said.get("name"), str):
            given = json.dumps(said.get("arguments") or {})
            out.append({"id": f"text_{k}", "function": {"name": said["name"], "arguments": given}})
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
    for rel in P.in_tree(root):
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


class Fork(Leaf):
    """One of N conversations on one leaf, in a copy of its checkout: its `done` runs the check in the
    copy and does not finish the leaf; the first fork whose check passes is the one that lands."""

    def __init__(self, *args, check: str | None, won: threading.Event, halted: threading.Event, source: Path):
        super().__init__(*args)
        self.check, self.won, self.passed, self.source = check, won, False, source
        self.halted = halted  # the run was stopped (won is set with it, so the fork stops at its next step)
        self.over = False  # its last row is written, by itself or for it
        self.released: tuple[str, list[str]] | None = None
        self.why: str | None = None  # why it gave up, when it did
        self.failed: Exception | None = None  # what stopped it: Token Factory, or the sandbox
        self.check_failed: int | None = None  # the exit code of its last check, when that one failed

    def done(self) -> str:
        if self.check:
            code, out = self.place.run(self.check)
            if code != 0:
                self.check_failed = code
                return f"the check failed in this fork (exit {code}):\n{out[-OUTPUT:]}"
        with _SHARED:  # one fork is the first to pass, and only that one lands
            self.passed = not self.won.is_set()
            self.won.set()
        self.finished = True
        if not self.check:
            return "this fork is finished (the leaf has no check)"
        return "the check passed in this fork" + ("" if self.passed else ", and another fork's passed first")

    def release(self, why: str = "", wants: list[str] | str | None = None) -> str:
        wants = [wants] if isinstance(wants, str) else wants  # one path, not its letters
        self.released, self.finished = (why or "(no reason given)", list(wants or [])), True
        return "this fork gives up; the leaf is handed back only if every fork does"

    def outcome(self) -> tuple[str, str]:
        """How this fork ended, as its row on the leaf says it, and why: passed, lost (another fork
        passed first), gave up (its reason), check failed (then how its conversation ended), or how its
        conversation ended when no check ran: no tool call, out of steps."""
        if self.passed:
            return "passed", "its check passed first" if self.check else "it finished first (it has no check)"
        if self.released:
            return "gave up", self.released[0]
        if self.ended == "stopped" or self.finished:
            return "lost", "another fork's check passed first"
        said = {"no tool call": "it stopped calling tools", "out of steps": "it ran out of steps"}[self.ended]
        if self.check_failed is not None:
            return "check failed", f"its check failed (exit {self.check_failed}), then {said}"
        return self.ended, said


def converse(leaf: Leaf, model: str, messages: list[dict], args, params: dict, bill: dict, tag: str,
             stop: threading.Event | None = None) -> str | None:  # fmt: skip
    """The loop: ask the model, run the tools it calls, until the leaf is finished, the model stops
    calling tools three times, the steps run out, or ``stop`` is set (another fork won, or the run was
    stopped: a fork's ``halted``). Returns why the model gave up, in words and with what a person can do
    about it, or None when it did not; how the loop ended is left in ``leaf.ended``: finished, no tool
    call, out of steps, stopped."""
    nudged, told = 0, ""

    def stopped() -> bool:  # read at each step, and before each tool: nothing starts after a stop
        if stop is None or not stop.is_set() or leaf.finished:
            return False
        why = "the run was stopped" if leaf.halted.is_set() else "another fork's check passed"
        print(f"{tag}{step:>3} stopped: {why}", flush=True)
        leaf.ended = "stopped"
        return True

    for step in range(1, args.steps + 1):
        if stopped():
            return None
        _compact(messages)
        said = tf.chat(model, messages, TOOLS if args.protocol == "native" else None, tag=leaf.node.id,
                       **params)  # fmt: skip
        with _SHARED:
            bill["calls"] += 1
            bill["prompt_tokens"] += said["usage"].get("prompt_tokens") or 0
            bill["completion_tokens"] += said["usage"].get("completion_tokens") or 0
            bill["dollars"] += said["dollars"]
            bill["seconds"] += said["seconds"]
        message = said["message"]
        native = message.get("tool_calls") or []
        calls = native or text_calls(message.get("content"))  # a native call handed back as text, too
        print(f"{tag}{step:>3} {model.rsplit('/', 1)[-1]} answered in {said['seconds']:.2f} s", flush=True)
        if message.get("content"):
            print(f"{tag}{step:>3} says: {' '.join(str(message['content']).split())[:200]}", flush=True)
        kept = {"role": "assistant", "content": message.get("content") or ""}
        if native:
            kept["tool_calls"] = native
        messages.append(kept)
        if not calls:
            nudged += 1
            cut = said.get("finish") == "length"  # a reasoning model that ran out of room is not done
            if nudged > 2:
                print(f"{tag}{step:>3} stopped: no tool call three times", flush=True)
                leaf.ended = "no tool call"
                if cut:
                    return (f"the model answered three times without calling a tool, the last cut off at the "
                            f"token limit ({params.get('max_tokens')} tokens): raise --max-tokens, {LARGER}")
                return f"the model answered three times without calling a tool: {LARGER}"
            if cut and params.get("max_tokens"):
                params["max_tokens"] = min(params["max_tokens"] * 2, 32_768)
                print(f"{tag}{step:>3} cut off at the token limit; now {params['max_tokens']}", flush=True)
            messages.append({"role": "user", "content": CUT if cut else NUDGE})
            continue
        for c in calls:
            if stopped():
                return None
            name = c["function"]["name"]
            began = time.monotonic()
            result = leaf.call(name, c["function"].get("arguments"))
            took = time.monotonic() - began
            first_line = result.split("\n", 1)[0][:160]
            brief = _brief(c["function"].get("arguments"))
            print(f"{tag}{step:>3} {name} {brief} → {first_line} ({took:.2f} s)", flush=True)
            if native:
                messages.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": result})
            else:
                messages.append({"role": "user", "content": f"Result of {name}:\n{result}"})
            told = first_line
            if leaf.finished:
                leaf.ended = "finished"
                return None
    leaf.ended = "out of steps"
    last = f" (the last it was told: {told})" if told else ""
    return f"the model used all {args.steps} steps without finishing{last}: raise --steps, {LARGER}"


_SHARED = threading.Lock()  # what the forks share: the bill, and which of them passed first
STOPPED_FORK = "the run was stopped before this fork ended"


def _shown(root: Path, source: Path) -> list[str]:
    """What git in ``source``, the leaf's checkout, shows of the files under ``root`` (69): there, what
    it tracks or does not ignore; under a fork's copy, which has no .git of its own, the files there (what
    git showed, and what the fork wrote) that git in the checkout does not ignore."""
    if root == source:
        return P.in_tree(root)
    found = []
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in (".git", *gate.OURS)]
        found += [os.path.relpath(os.path.join(base, name), root) for name in names]
    ignored = gate._ignored(source, found)
    return sorted(set(found) - ignored)


def _in_scope_state(root: Path, scope: list[str], source: Path) -> dict[str, bytes]:
    """The files under ``root`` that the scope covers and git in ``source`` shows, links and caches left
    out: what git ignores (a .env, a .venv, data/) is never copied from a fork, nor deleted for one."""
    out = {}
    for rel in _shown(root, source):
        path = root / rel
        skip = {".git", *gate.OURS, "__pycache__"} & set(Path(rel).parts)
        if P.in_scope(rel, scope) and not skip and path.is_file() and not path.is_symlink():
            out[rel] = path.read_bytes()
    return out


def fork_and_pick(n: int, here: Path, node: P.Node, store: Store, repo: Path, session: str, model: str,
                  messages: list[dict], args, params: dict, bill: dict) -> Leaf | str:  # fmt: skip
    """N conversations from one checkpoint of the leaf, each in a copy of its checkout; the first
    whose check passes is copied into the checkout (what its scope covers, and nothing else). Returns
    a leaf to finish here or, when no fork passed, why each did not (when every fork handed the leaf
    back, it is handed back). When a fault stopped every fork (Token Factory, the sandbox), the first
    fork's is raised, as it is without forks."""
    won, halted = threading.Event(), threading.Event()
    before = _in_scope_state(here, node.scope, here)
    copies, forks = [], []

    def told(k: int) -> list[dict]:
        said = [dict(m) for m in messages]
        said[0]["content"] += (f"\nThis is fork {k} of {n}: {n} attempts at this leaf run at once from the "
                               "same checkout, and the first whose check passes lands.")  # fmt: skip
        return said

    def note(to: Store, k: int, f: Fork, state: str, why: str = "") -> None:  # its row, as it happens
        said = {"fork": k + 1, "of": n, "model": model, "state": state, "why": why, **_box(f.place)}
        to.log_node(node.id, P._now(), "fork", f"run:{NAME}", session or None, None, said)

    def ended(to: Store, k: int, f: Fork, state: str, why: str) -> None:
        """A fork's last row, written once: how it ended, or "stopped" once the run was stopped."""
        with _SHARED:
            if f.over:
                return
            f.over = True
        note(to, k, f, *(("stopped", STOPPED_FORK) if halted.is_set() else (state, why)))

    def one(k: int, f: Fork) -> None:
        with Store.open(repo) as mine:  # a thread, a connection
            f.store = mine
            if hasattr(f.place, "store"):
                f.place.store = mine  # a sandbox logs its breaches
            note(mine, k, f, "running")
            try:
                f.why = converse(f, model, told(k + 1), args, params, bill, f"[fork {k + 1}] ", won)
            except Exception as no:  # in a thread of its own: its reason and its row, never a traceback
                said = _relative(str(no), f.place.root)
                f.why = said if isinstance(no, tf.Unreachable) else f"{type(no).__name__}: {said}"
                f.failed = no if isinstance(no, tf.Unreachable) else RuntimeError(
                    f.why.removeprefix("RuntimeError: "))  # raised as the leaf's, which names its type once
                print(f"[fork {k + 1}] stopped: {f.why}", flush=True)
                ended(mine, k, f, "stopped", f.why)
                return
            ended(mine, k, f, *f.outcome())

    try:  # opened before the first copy: a sandbox that cannot be made leaves no copy behind
        for k in range(n):
            copy = Path(tempfile.mkdtemp(prefix=f"graphene-{node.id}-fork{k + 1}-"))
            copies.append(copy)
            for rel in P.in_tree(here):
                src = here / rel
                if src.is_file() and not src.is_symlink():
                    (copy / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, copy / rel)
            if args.placement == "local":
                place = Local(copy)
            elif k == 0:  # the leaf's sandbox, made once; its check forks from it
                place = _sandbox(copy, node, store, session, args, checkout=here)
            else:  # every other fork, from the same checkpoint: nothing uploaded or set up again
                place = forks[0].place.fork(copy)
            forks.append(Fork(store, node, place, repo, session, check=node.check, won=won, halted=halted,
                              source=here))  # fmt: skip
        threads = [threading.Thread(target=one, args=(k, f), daemon=True) for k, f in enumerate(forks)]
        try:
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        except BaseException:  # the run was stopped (TERM, Ctrl-C): only this thread heard it
            halted.set()
            won.set()  # each fork reads it at its next step, and before its next tool
            for f in forks:
                f.place.halt()  # what it runs now: a command, a container
            until = time.monotonic() + GRACE / 2  # inside the time the run gives this process to end
            for t in threads:
                if t.is_alive():
                    t.join(max(0.0, until - time.monotonic()))
            for k, f in enumerate(forks):  # a fork still in a call to Token Factory is left, and said so
                ended(store, k, f, "stopped", STOPPED_FORK)
            raise
        finally:  # what they spent is in the bill already, shared; and what they were refused
            bill["refused_in_forks"] = sum(f.refused for f in forks)
        bill["wrote_in_forks"] = {}
        winner = next((k for k, f in enumerate(forks) if f.passed), None)
        bill["forks"], bill["winner"] = n, None if winner is None else winner + 1
        if winner is None:
            gave_up = [f.released for f in forks if f.released]
            if gave_up and len(gave_up) == n:
                wants = sorted({w for _, ws in gave_up for w in ws})
                real = Leaf(store, node, Local(here), repo, session)
                print(real.release(gave_up[0][0], wants), flush=True)
            if all(f.failed for f in forks):
                raise forks[0].failed
            print(f"no fork's check passed ({n} forks)", flush=True)
            why = [f"fork {k + 1}: {f.why or 'handed it back: ' + f.released[0]}"
                   for k, f in enumerate(forks) if f.why or f.released]  # fmt: skip
            return f"no fork's check passed ({n} forks): " + "; ".join(why)
        bill["wrote_in_forks"] = forks[winner].wrote  # the winner's writes are the leaf's
        after = _in_scope_state(copies[winner], node.scope, here)
        for rel in before.keys() - after.keys():
            (here / rel).unlink(missing_ok=True)
        for rel, data in after.items():
            if before.get(rel) != data:
                (here / rel).parent.mkdir(parents=True, exist_ok=True)
                (here / rel).write_bytes(data)
        print(f"fork {winner + 1} of {n} passed its check; its work is in the leaf's checkout", flush=True)
        return Leaf(store, node, Local(here), repo, session)
    finally:
        for f in forks:
            f.place.close()
        for copy in copies:
            shutil.rmtree(copy, ignore_errors=True)


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
        try:  # the ids the live list has: the smallest Nemotron by default, a retired one's nearest
            args.model, said = tf.resolve(args.model, "executor")
        except tf.Unreachable as no:
            return stop(store, node, str(no))
        for line in said:
            print(line, flush=True)
        if not args.model:
            return stop(store, node, "Token Factory lists no Nemotron model for this key")
        ladder = args.model
        tried = int(os.environ.get("GRAPHENE_TRY") or 0) or attempt_number(store, node)  # run says which
        model = ladder[min(tried, len(ladder)) - 1]
        step = {"attempt": tried, "model": model}
        before = ladder[min(tried - 1, len(ladder)) - 1] if tried > 1 else model
        if before != model:  # a step up the ladder: from which model, and why (the refusal run handed over)
            refusal = prompt.partition(REFUSED)[2].strip().split("\n", 1)[0].rstrip(":")
            why = f"attempt {tried - 1} refused" + (f": {refusal}" if refusal else "")
            step |= {"from": before, "why": why}
        store.log_node(node.id, P._now(), "model", f"run:{NAME}", session or None, None, step)
        first = [prompt]
        if args.map:
            files = P.in_tree(here)
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
                "seconds": 0.0, "prompt": PROMPT_VERSION, "endpoint": tf.endpoint()}  # fmt: skip
        where = args.placement + (f", {args.forks} forks" if args.forks > 1 else "")
        print(f"nemotron executor · {model} · {where} placement · leaf {node.id}", flush=True)
        if "from" in step:
            print(f"stepped up from {before}: {step['why']}", flush=True)
        leaf = None
        try:
            last = tried >= len(ladder)  # the ladder's last rung: a next attempt asks the same model
            if args.forks > 1:
                picked = fork_and_pick(args.forks, here, node, store, repo, session, model, messages, args,
                                       params, bill)  # fmt: skip
                if isinstance(picked, str):
                    return gave_up(store, node, picked, last)
                leaf = picked
                said = leaf.done()
                print(f"done → {(said.splitlines() or [''])[0]}", flush=True)
                return 0
            place = Local(here) if args.placement == "local" else _sandbox(here, node, store, session, args)
            leaf = Leaf(store, node, place, repo, session)
            try:
                why = converse(leaf, model, messages, args, params, bill, "")
            finally:
                place.close()
                if hasattr(place, "base"):  # its operations and seconds, now that the attempt is over
                    noted = store.node_log(node.id, ("placement",))[-1]["detail"]
                    store.log_node(node.id, P._now(), "placement", f"run:{NAME}", session or None, None,
                                   noted | _box(place))  # fmt: skip
            return gave_up(store, node, why, last)
        except tf.Unreachable as no:
            return stop(store, node, str(no))
        except Exception as no:  # no sandbox, or ConTree's own errors: said to the person, not a traceback
            return stop(store, node, _relative(f"{type(no).__name__}: {no}", here))
        finally:
            bill["refused"] = (leaf.refused if leaf else 0) + bill.pop("refused_in_forks", 0)
            bill["wrote"] = {**bill.pop("wrote_in_forks", {}), **(leaf.wrote if leaf else {})}
            bill["dollars"] = round(bill["dollars"], 6)
            store.log_node(node.id, P._now(), "usage", f"run:{NAME}", session or None, None, bill)
            print(f"bill: {bill['calls']} calls, {bill['prompt_tokens']} in, "
                  f"{bill['completion_tokens']} out, ${bill['dollars']:.4f} at list price, "
                  f"{bill['refused']} writes refused", flush=True)  # fmt: skip


def gave_up(store: Store, node: P.Node, why: str | None, last: bool) -> int:
    """The model gave up (``why``) and did not hand the leaf back. On the ladder's ``last`` rung, with
    nothing changed inside the scope, the executor hands it back with that reason, as it does when it
    cannot work at all (``stop``): the same model sent round again fails the same way, and a check run
    on untouched code says nothing. Otherwise the run's boundary decides: the check may pass on what
    was done, or the next rung tries, told why the last attempt was not accepted."""
    if why is None:
        return 0
    node = P.get(store, node.id)
    if last and node.state == P.RUNNING:
        changed = P.changed_since(node.checkout or ".", node.base_sha, node.dirty_at_start)
        if not any(P.in_scope(p, node.scope) for p in changed):
            return stop(store, node, why)
    print(f"gave up: {why}", flush=True)
    return 0


def stop(store: Store, node: P.Node, why: str) -> int:
    """The executor cannot work at all (no key, a refused key, no sandbox, the spend cap): it hands the
    leaf back itself, with that reason, so the run does not send it round again to fail the same way,
    and the person reads the cause instead of a check that failed on untouched code."""
    if P.get(store, node.id).state == P.RUNNING:
        here = Path.cwd()
        Leaf(store, node, Local(here), repo_root(here), "").release(f"the executor stopped: {why}")
    print(f"stopped: {why}", flush=True)
    return 3


def _relative(said: str, root: Path) -> str:
    """``said`` with ``root`` (the checkout, or a fork's copy of it) taken out, so a path in it is the
    repository's: an error's text is a leaf's reason, and the page never carries a path to the
    checkout (64)."""
    for where in sorted({str(root), str(root.resolve())}, key=len, reverse=True):  # /private/var, /var
        said = said.replace(where + os.sep, "").replace(where, ".")
    return said


def _brief(arguments) -> str:
    try:
        said = json.loads(arguments) if isinstance(arguments, str) else dict(arguments or {})
        said = json.loads(said) if isinstance(said, str) else said  # encoded twice
    except ValueError:
        return "(arguments not JSON)"
    if not isinstance(said, dict):
        return "(arguments not an object)"
    return " ".join(str(said.get(k))[:80] for k in ("path", "command", "why") if said.get(k))


def _sandbox(here: Path, node: P.Node, store: Store, session: str, args, checkout: Path | None = None):
    """The leaf's sandbox, forked from its commit's checkpoint when another leaf made it, and a note in
    its record of where it is, so that its check (whoever runs `done`) runs in a fork of the same."""
    from . import sandbox

    name = os.environ.get("GRAPHENE_SANDBOX") or "contree"
    box = sandbox.choose(name, args.image)
    place = sandbox.Sandbox(here, node.scope, box, store, node.id, args.prepare, checkout)
    shared = "forked from the commit's checkpoint" if place.reused else "made"
    store.log_node(node.id, P._now(), "placement", f"run:{NAME}", session or None, None,
                   {"placement": "sandbox", "box": name, **_box(place)})  # fmt: skip
    print(f"sandbox {shared} ({name}, {place.timings[0]:.1f} s): image {place.base[:19]}", flush=True)
    return place


def _box(place) -> dict:
    """A sandbox as the leaf's log keeps it: the image it started from, whether that checkpoint was made
    for it or forked from one, and the operations and seconds it has taken; nothing for the local one."""
    if not hasattr(place, "base"):
        return {}
    return {"image": place.base, "checkpoint": "forked" if place.reused else "made", "ops": place.ops,
            "seconds": round(sum(place.timings), 3)}  # fmt: skip


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
    parser.add_argument("--forks", type=int, default=1, help="N conversations; the check picks")
    parser.add_argument("--image", help="the sandbox's image (default python:3.12, with git and setpriv)")
    parser.add_argument("--prepare", help="a command run once, as root, in the checkpoint (pip install -e .)")
    parser.add_argument("prompt")
    args = parser.parse_args(argv)
    signal.signal(signal.SIGTERM, _stopped)  # a stopped run: the forks' rows and the bill are still written
    return work(args, args.prompt)


def _stopped(*_) -> None:
    """TERM, heard once: a parallel run sends it twice (its stop, and the leaf's own worker), and the
    second must not cut short what the first began (a traceback, forks without their last row)."""
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    sys.exit(143)


def template(spec: str) -> str:
    """`nemotron [options]` as the command `graphene run` starts."""
    rest = spec.split(None, 1)[1] if len(spec.split(None, 1)) > 1 else ""
    return f"{shlex.quote(sys.executable)} -m graphene_map.executor {rest}".strip()


if __name__ == "__main__":
    raise SystemExit(main())
