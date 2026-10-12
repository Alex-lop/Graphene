#!/usr/bin/env python3
"""X5's executor: in its worktree (its cwd), it breaks the function the leaf owns, asks the check's own
interpreter where it imports pkg from (X5_PROBE, a shell command; the answer goes to X5_ORIGIN), then
calls done. Graphene gives it GRAPHENE_NODE; the prompt is its last argument and is not read."""

import os
import pathlib
import subprocess

node = os.environ["GRAPHENE_NODE"]
path = pathlib.Path({"a": "src/pkg/__init__.py", "b": "src/pkg/b.py"}[node])
path.write_text(path.read_text().replace("a + b", "a - b").replace("a * b", "a / b"))
print(f"broke {path} in {os.getcwd()}", flush=True)
if os.environ.get("X5_PROBE"):
    probe = subprocess.run(os.environ["X5_PROBE"], shell=True, capture_output=True, text=True)
    said = probe.stdout.strip() or probe.stderr.strip().splitlines()[-1:] or ["nothing"]
    said = said if isinstance(said, str) else said[0]
    with open(os.environ.get("X5_ORIGIN", "origin.txt"), "a", encoding="utf-8") as f:
        f.write(f"{node} in {os.getcwd()}: pkg imported from {said}\n")
subprocess.run(["graphene", "node", "done", node])
