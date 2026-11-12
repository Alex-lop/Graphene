"""Replay the brief's boundary cases on throwaway repos; no model or endpoint."""

import io
import json
import os
import subprocess
import tempfile
from pathlib import Path

from graphene_map import plan
from graphene_map.hooks import hook_main
from graphene_map.store import Store

PERSON = plan.Caller("alex", True)
BOT = plan.Caller("fixture", False, "verify-session")


def fixture(root):
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "inside.txt").write_text("before\n")
    (root / "outside.txt").write_text("before\n")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "base",
        ],
        check=True,
    )
    with Store.open(root) as store:
        plan.propose(store, [{"title": "inside only", "scope": ["inside.txt"], "check": "true"}], PERSON)
        plan.start(store, "n1", BOT, root)


def hook(root, **fields):
    out = io.StringIO()
    hook_main(
        io.StringIO(
            json.dumps(
                {"session_id": BOT.session_id, "cwd": str(root), "hook_event_name": "PreToolUse", **fields}
            )
        ),
        root,
        out,
    )
    return json.loads(out.getvalue()) if out.getvalue() else None


def finish(root):
    with Store.open(root) as store:
        try:
            return "accepted: " + plan.finish(store, "n1", BOT).state
        except plan.Refused as no:
            return "refused: " + str(no).splitlines()[0]


def main():
    with tempfile.TemporaryDirectory(prefix="gv-boundaries-") as temp:
        base = Path(temp)
        cases = [
            (
                "comment",
                {"tool_name": "Bash", "tool_input": {"command": "# explain\necho changed > outside.txt"}},
            ),
            (
                "literal-variable",
                {"tool_name": "Bash", "tool_input": {"command": "F=outside.txt; echo changed > $F"}},
            ),
            ("external-variable", {"tool_name": "Bash", "tool_input": {"command": "echo changed > $OUT"}}),
            (
                "alternate-path-field",
                {"tool_name": "Write", "tool_input": {"path": "outside.txt", "content": "changed"}},
            ),
        ]
        for name, event in cases:
            root = base / name
            fixture(root)
            answer = hook(root, **event)
            decision = answer["hookSpecificOutput"]["permissionDecision"] if answer else "silence"
            print(name, json.dumps(event), "=>", decision)
            if answer is None:
                if event["tool_name"] == "Bash":
                    subprocess.run(
                        ["/bin/bash", "-c", event["tool_input"]["command"]],
                        cwd=root,
                        env={**os.environ, "OUT": "outside.txt"},
                        check=True,
                    )
                else:
                    (root / "outside.txt").write_text("changed\n")
                print("  actual write outside.txt =>", finish(root))
        for name, rel in [("manual-inside", "inside.txt"), ("manual-outside", "outside.txt")]:
            root = base / name
            fixture(root)
            (root / rel).write_text("human edit\n")
            print(
                name,
                "human writes",
                rel,
                "=>",
                finish(root),
                "; content retained:",
                (root / rel).read_text().strip(),
            )
        root = base / "nothing-done"
        fixture(root)
        result = finish(root)
        assert result.startswith("refused:") and "nothing inside its scope" in result
        print("nothing-done; check=true =>", result)


if __name__ == "__main__":
    main()
