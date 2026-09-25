"""Placement B, "the harness there": OpenCode runs headless inside the leaf's sandbox, and this wrapper,
given to `graphene run --with 'python3 docs/test/spikes/harness_there/wrapper.py'`, speaks for it.

A spike, not product. For the leaf named by GRAPHENE_NODE it makes a sandbox from the leaf's checkout
(graphene_map.sandbox.Sandbox, layer 2 included, from this directory's image), runs `opencode run` there
as the leaf's unprivileged user with the contract as the prompt and Token Factory as its provider, lets
Sandbox bring back what the scope covers, and then says `graphene node release` (when OpenCode's last
message asks for it) or `graphene node done` for the leaf.

The structural cost: OpenCode calls the model from inside the sandbox, so the inference key goes in too,
as a file for the run (removed before the sandbox's checkpoint), readable by the same user that runs the
model's shell commands. The sandbox also needs a network path to Token Factory.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from graphene_map import plan as P
from graphene_map import sandbox
from graphene_map import tokenfactory as tf
from graphene_map.executor import Leaf
from graphene_map.sources.claude_code import repo_root
from graphene_map.store import Store

IMAGE = "graphene-harness-there:opencode-1.18.31"  # docker build -t <this> docs/test/spikes/harness_there
KEYFILE = "/tmp/graphene/key"
HOW = """

This leaf runs in a sandbox: the repository is /work, your working directory, and there is no `graphene`
command here. When the leaf is done, say so and stop: Graphene runs the check and asks git what changed.
If it cannot be done inside its scope, end your last message with a line `RELEASE: <why>` and one line
`WANTS: <path>` for each path outside the scope you would need."""


class WithKey:
    """The sandbox's box, with the inference key put in for each command and taken out before the
    command's checkpoint is kept. Setup runs without it."""

    def __init__(self, box, key: str):
        self.box, self.key = box, key

    def __getattr__(self, name):
        return getattr(self.box, name)

    def run(self, image: str, script: str, files: dict[str, bytes], timeout: float):
        return self.box.run(
            image, f"{script}\nrm -f {KEYFILE}", {**files, KEYFILE: self.key.encode()}, timeout
        )


def seen_from_box(url: str) -> str:
    """The endpoint as a container reaches it: this machine's loopback is host.docker.internal there."""
    parts = urlsplit(url)
    if parts.hostname in ("127.0.0.1", "localhost"):
        parts = parts._replace(netloc=parts.netloc.replace(parts.hostname, "host.docker.internal", 1))
    return urlunsplit(parts).rstrip("/")


def config(model: str, base_url: str) -> dict:
    """OpenCode's config: Token Factory as its only provider (OpenAI-compatible), everything allowed
    (the sandbox's users are the boundary, not OpenCode's permissions), nothing fetched at run time."""
    return {
        "model": f"tokenfactory/{model}",
        "small_model": f"tokenfactory/{model}",
        "enabled_providers": ["tokenfactory"],
        "share": "disabled",
        "autoupdate": False,
        "snapshot": False,
        "lsp": False,
        "formatter": False,
        # a tool denied outright is not offered to the model: the set nearest the Nemotron executor's
        "permission": {
            "*": "allow",
            **dict.fromkeys(("question", "webfetch", "task", "skill", "todowrite"), "deny"),
        },
        "provider": {
            "tokenfactory": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Token Factory",
                "options": {"baseURL": base_url, "apiKey": "{file:" + KEYFILE + "}"},
                "models": {model: {"name": model}},
            }
        },
    }


def opencode(prompt: str, model: str, base_url: str) -> str:
    off = ("AUTOUPDATE", "DEFAULT_PLUGINS", "PROJECT_CONFIG", "MODELS_FETCH", "LSP_DOWNLOAD")
    env = {"OPENCODE_CONFIG_CONTENT": json.dumps(config(model, base_url))}
    env |= {f"OPENCODE_DISABLE_{k}": "true" for k in off}
    exports = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items())
    return (
        f"export {exports}; opencode run --format json --auto --title leaf {shlex.quote(prompt)} < /dev/null"
    )


def events(output: str) -> list[dict]:
    out = []
    for line in output.splitlines():
        if line.startswith('{"type":'):
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def rel(path: str) -> str:
    return os.path.relpath(path, sandbox.WORK) if path.startswith(sandbox.WORK + "/") else path


def work(prompt: str, model: str | None) -> int:
    node_id = os.environ.get("GRAPHENE_NODE")
    if not node_id:
        print("started by `graphene run`, which names the leaf (GRAPHENE_NODE)")
        return 2
    here = Path.cwd()
    repo = repo_root(here)
    session = os.environ.get("GRAPHENE_ATTEMPT", "")
    key = os.environ.get(tf.KEY)
    if not key:
        print(f"stopped: {tf.KEY} is not set; OpenCode in the sandbox needs it")
        return 3
    if not model:  # the smallest Nemotron the live list has, as the Nemotron executor picks
        listed = tf.roles()
        model = next((listed[k] for k in ("nano", "super", "ultra") if k in listed), None)
    began = time.monotonic()
    with Store.open(repo) as store:
        node = P.get(store, node_id)
        place = sandbox.Sandbox(here, node.scope, WithKey(sandbox.Docker(IMAGE), key), store, node.id)
        print(
            f"opencode in the sandbox · {model} · leaf {node.id} · sandbox ready in {place.timings[0]:.2f} s",
            flush=True,
        )
        code, output = place.run(opencode(prompt + HOW, model, seen_from_box(tf.base())), timeout=600)
        print(f"opencode ended (exit {code}) after {place.timings[1]:.2f} s in the sandbox", flush=True)
        said, refused, calls, tokens = "", [], 0, [0, 0]
        for k, e in enumerate(ev for ev in events(output) if ev["type"] in ("tool_use", "text", "error")):
            part = e.get("part") or {}
            if e["type"] == "text":
                said = part.get("text", "")
                print(f"{k + 1:>3} says: {' '.join(said.split())[:200]}", flush=True)
            elif e["type"] == "error":
                print(f"{k + 1:>3} error: {json.dumps(e.get('error'))[:300]}", flush=True)
            else:
                calls += 1
                state = part.get("state") or {}
                given = state.get("input") or {}
                when = state.get("time") or {}
                took = (when.get("end", 0) - when.get("start", 0)) / 1000
                first = (state.get("output") or state.get("error") or "").split("\n", 1)[0][:160]
                brief = rel(given.get("filePath") or given.get("command") or "")[:80]
                print(
                    f"{k + 1:>3} {part.get('tool')} {brief} → {state.get('status')}: {first} ({took:.2f} s)",
                    flush=True,
                )
                if part.get("tool") in ("write", "edit") and state.get("status") == "error":
                    refused.append(rel(given.get("filePath", "")))
        for e in events(output):
            if e["type"] == "step_finish":
                t = (e.get("part") or {}).get("tokens") or {}
                tokens[0] += t.get("input") or 0
                tokens[1] += t.get("output") or 0
        tail = output.rsplit("\n(refused:", 1)
        if len(tail) == 2:
            print("(refused:" + tail[1], flush=True)
        leaf = Leaf(store, node, place, repo, session)
        why = re.findall(r"^RELEASE:\s*(.+)$", said, re.M)
        wants = [*re.findall(r"^WANTS:\s*(\S+)$", said, re.M), *refused]
        if why:
            answer = leaf.release(why[-1], list(dict.fromkeys(wants)))
        else:
            answer = leaf.done()
        print(f"graphene: {answer}", flush=True)
        store.log_node(
            node.id,
            P._now(),
            "usage",
            "run:opencode-sandbox",
            session or None,
            None,
            {
                "model": model,
                "harness": "opencode 1.18.31",
                "tool_calls": calls,
                "prompt_tokens": tokens[0],
                "completion_tokens": tokens[1],
                "refused_by_the_sandbox": refused,
                "seconds": round(time.monotonic() - began, 3),
            },
        )
        print(
            f"bill: {calls} tool calls, {tokens[0]} in, {tokens[1]} out, "
            f"{len(refused)} writes refused by the sandbox, {time.monotonic() - began:.2f} s",
            flush=True,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--model", help="a model id; else the smallest Nemotron Token Factory lists")
    parser.add_argument("prompt")
    args = parser.parse_args(argv)
    return work(args.prompt, args.model)


if __name__ == "__main__":
    sys.exit(main())
