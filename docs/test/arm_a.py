#!/usr/bin/env python3
"""Arm A of the live pre-registration (results-2026-09-28-live-prereg.md): the paragraph to Nano, no tree.

    uv run python docs/test/arm_a.py <repo> --paragraph-file <path> [--model ID] --steps N \\
        --max-tokens M [--seconds S] [--conversation FILE]
    uv run python docs/test/arm_a.py <repo> --follow-up-file <path> --steps N ...   (the same budget)

One Nemotron session, driven by the executor's own loop (`executor.converse`) with the executor's own
view, edit, write and run, in the whole repo: no GRAPHENE_NODE, no plan, no scope and no check. `done`
only ends the session, and nothing decides what stays but the person reading the reply and `git diff`.
Commands run as the person's user in the repo (the executor's local placement), without the key.

The budget (--steps model calls, --seconds wall time) is the run's, not the message's: a follow-up
gets what the earlier messages left, read from the conversation file. That file (by default
arm-a.json beside the repo, never inside it) holds the messages and the bill, in the shape
`logline.py <runlog> executor result --from-json <file>` reads: `total_cost_usd` is the session's
running total, as `claude -p --resume` prints it, `num_turns` is this message's model calls, and
`endpoint` is who answered ("token factory", or "a stand-in"), which evidence.py reads before it draws;
a follow-up answered by another endpoint than the one before it adds " then <that one>".
Each call is in the ledger every arm shares (GRAPHENE_LEDGER, else bench.py's) under the tag
`arm-a:<session>`. The spend is bench.py's (`bench.budget`): nothing starts with GRAPHENE_SPEND_CAP_USD
unset or not a number, no new session starts at 80% of it, and the client refuses a call at 100%. A
follow-up is the session going on, so 80% does not stop it.
"""

from __future__ import annotations

import argparse
import json
import signal
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import bench
import tally  # noqa: F401  (it puts src/ on the path)

from graphene_map import executor as E
from graphene_map import night
from graphene_map import plan as P
from graphene_map import tokenfactory as tf

SYSTEM = """\
You are a coding agent in a git repository, working for the person whose message follows. You work only
through the tools. Read what you need (view, run); change files with edit or write; run what tells you
it works. When you are finished, say in a few lines what you did, then call done. Keep each step small."""

NUDGE = "Use a tool. When you are finished, say what you did and call done."
TOOLS = [t for t in E.TOOLS if t["function"]["name"] in ("view", "edit", "write", "run")] + [
    {"type": "function", "function": {
        "name": "done", "description": "Finished: the session ends, and the person reads your last message.",
        "parameters": {"type": "object", "properties": {}}}},
]  # fmt: skip


class Whole(E.Leaf):
    """The executor's tools on the whole repo: a write is refused only outside it or in .git/ and
    .graphene/ (``Leaf._rel``), never by a scope; done ends the session; there is no release."""

    tools, nudge = TOOLS, NUDGE

    def _may_write(self, path: str, how: str) -> tuple[str | None, str | None]:
        rel, no = self._rel(path)
        self.refused += no is not None
        return rel, no

    def done(self) -> str:
        self.finished = True
        return "the session is over; the person reads your last message and the diff"

    def release(self, *_, **__) -> str:
        return "there is no tool 'release'; the tools are view, edit, write, run, done"


def unanswered(messages: list[dict]) -> list[dict]:
    """A tool result for each call a stopped session never ran, so the conversation can go on."""
    answered = {m.get("tool_call_id") for m in messages if m.get("role") == "tool"}
    return [{"role": "tool", "tool_call_id": c.get("id", ""), "content": "(not run: the session was stopped)"}
            for m in messages for c in m.get("tool_calls") or [] if c.get("id") not in answered]  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("repo", type=Path)
    first = ap.add_mutually_exclusive_group(required=True)
    first.add_argument("--paragraph-file", type=Path, help="the paragraph: starts the session")
    first.add_argument("--follow-up-file", type=Path, help="a follow-up: continues the session")
    ap.add_argument("--model", action="append", default=[], help="a model id (default: Nano, from the list)")
    ap.add_argument("--steps", type=int, required=True, help="model calls, for the whole run")
    ap.add_argument("--seconds", type=float, default=0, help="wall seconds for the whole run (0: no limit)")
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--param", action="append", default=[], help="KEY=JSON, sent in the request as is")
    ap.add_argument("--conversation", type=Path, help="default: arm-a.json beside the repo")
    args = ap.parse_args(argv)
    repo = args.repo.resolve()
    saved = (args.conversation or repo.parent / "arm-a.json").resolve()
    if saved.is_relative_to(repo):
        print(f"{saved} is inside the repo, where the model would read it and git would show it")
        return 2
    if args.paragraph_file and saved.exists():
        print(f"{saved} exists already; a run is never redone in place")
        return 2
    if args.follow_up_file and not saved.exists():
        print(f"no {saved}: a follow-up continues a session the paragraph started")
        return 2

    cap, why = bench.budget(None)
    if why and (cap is None or args.paragraph_file):  # 80% stops a new session, not one going on
        print(f"no new run: {why}")
        return 2 if cap is None else 3
    text = (args.paragraph_file or args.follow_up_file).read_text(encoding="utf-8")
    if args.paragraph_file:
        try:  # the ids the live list has: Nano by default, as the executor resolves it
            model, said = tf.resolve(args.model, "executor")
        except tf.Unreachable as no:
            print(f"stopped: {no}")
            return 3
        for line in said:
            print(line, flush=True)
        if not model:
            print("stopped: Token Factory lists no Nemotron model for this key")
            return 3
        files = P.in_tree(repo)
        mapped = "The repository's files:\n" + "\n".join(files[:400]) + ("\n…" if len(files) > 400 else "")
        opening = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"{text}\n\n{mapped}"}]
        state = {"session_id": uuid.uuid4().hex[:12], "model": model[0], "messages": opening,
                 "total_cost_usd": 0.0, "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                 "seconds_used": 0.0, "endpoint": tf.endpoint()}  # fmt: skip
    else:
        state = json.loads(saved.read_text(encoding="utf-8"))
        state["messages"] += unanswered(state["messages"]) + [{"role": "user", "content": text}]
        now = tf.endpoint()  # a session answered by two endpoints names both, so evidence.py refuses it
        if state["endpoint"].split(" then ")[-1] != now:
            state["endpoint"] += f" then {now}"

    if night.cap() is not None:  # the person's opening is set: practice, which evidence.py refuses
        state["practice"] = True
    steps = args.steps - state["calls"]
    seconds = args.seconds - state["seconds_used"] if args.seconds else None
    if steps <= 0 or (seconds is not None and seconds <= 0):
        print(f"stopped: the run's budget is spent ({state['calls']} calls, {state['seconds_used']:.0f} s)")
        return 3
    node = SimpleNamespace(id=f"arm-a:{state['session_id']}")  # the ledger's tag
    place = E.Local(repo)
    leaf = Whole(None, node, place, repo, "")
    leaf.halted = threading.Event()  # set when the time is up: converse stops at its next step
    timer = threading.Timer(seconds, lambda: (leaf.halted.set(), place.halt())) if seconds else None
    run = SimpleNamespace(steps=steps, protocol="native")
    params = {"temperature": args.temperature, "max_tokens": args.max_tokens,
              **{k: json.loads(v) for k, v in (p.split("=", 1) for p in args.param)}}  # fmt: skip
    bill = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "dollars": 0.0, "seconds": 0.0}
    print(f"arm A · {state['model']} · session {state['session_id']} · {steps} calls left", flush=True)
    began, why, code, before = time.monotonic(), None, 0, len(state["messages"])
    was = signal.signal(signal.SIGTERM, signal.default_int_handler)  # a kill ends it as Ctrl-C does: saved
    try:
        if timer:
            timer.start()
        why = E.converse(leaf, state["model"], state["messages"], run, params, bill, "", leaf.halted)
    except tf.Unreachable as no:
        why, code = f"stopped: {no}", 3
    finally:
        signal.signal(signal.SIGTERM, was)
        if timer:
            timer.cancel()
        new = state["messages"][before:]
        spoke = [m["content"] for m in new if m.get("role") == "assistant" and m.get("content")]
        state |= {
            "calls": state["calls"] + bill["calls"], "num_turns": bill["calls"],
            "prompt_tokens": state["prompt_tokens"] + bill["prompt_tokens"],
            "completion_tokens": state["completion_tokens"] + bill["completion_tokens"],
            "total_cost_usd": round(state["total_cost_usd"] + bill["dollars"], 6),
            "seconds_used": round(state["seconds_used"] + time.monotonic() - began, 1),
            "ended": "time is up" if leaf.halted.is_set() else leaf.ended or "stopped",
            "result": spoke[-1] if spoke else "",
        }  # fmt: skip
        saved.write_text(json.dumps(state, indent=1), encoding="utf-8")
        print(f"reply: {state['result']}" if state["result"] else "reply: (none)", flush=True)
        if why:
            print(f"ended: {why}", flush=True)
        print(f"bill: {bill['calls']} calls, {bill['prompt_tokens']} in, {bill['completion_tokens']} out, "
              f"${bill['dollars']:.4f} at list price; session ${state['total_cost_usd']:.4f}, "
              f"{state['calls']} of {args.steps} calls, {state['seconds_used']:.0f} s; "
              f"{leaf.refused} writes refused; ended: {state['ended']}; {saved}", flush=True)  # fmt: skip
    return code


if __name__ == "__main__":
    raise SystemExit(main())
