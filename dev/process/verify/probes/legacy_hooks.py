"""Replay an old recording-only hook file, then repair it with the current installer. No live vendor."""

import json
import subprocess
import tempfile
from pathlib import Path

from boundaries import BOT, PERSON, finish, hook

from graphene_map import plan
from graphene_map.hooks import HOOK_COMMAND, install_hooks
from graphene_map.store import Store


def main():
    with tempfile.TemporaryDirectory(prefix="gv-legacy-hooks-") as temp:
        root = Path(temp) / "repo"
        root.mkdir()
        git = ["git", "-C", str(root)]
        subprocess.run([*git, "init", "-q"], check=True)
        (root / "inside.txt").write_text("before\n")
        (root / "outside.txt").write_text("before\n")
        path = root / ".claude/settings.local.json"
        path.parent.mkdir()
        old = {"hooks": {"PostToolUse": [{"hooks": [{"type": "command", "command": HOOK_COMMAND}]}]}}
        path.write_text(json.dumps(old))
        with (root / ".git/info/exclude").open("a") as out:
            out.write("\n.claude/settings.local.json\n")
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run(
            [
                *git,
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
        assert "PreToolUse" not in old["hooks"]
        command = "printf legacy > outside.txt"
        subprocess.run(["/bin/sh", "-c", command], cwd=root, check=True)
        assert (root / "outside.txt").read_text() == "legacy"
        answer = finish(root)
        assert answer.startswith("refused:") and "changed outside its scope" in answer
        print("old hook file has PostToolUse only; no PreToolUse handler is called")
        print(command, "=> file written;", answer)
        added = install_hooks(root)
        assert "PreToolUse" in added
        repaired = json.loads(path.read_text())
        assert repaired["hooks"]["PostToolUse"] == old["hooks"]["PostToolUse"]
        answer = hook(root, tool_name="Write", tool_input={"file_path": str(root / "outside.txt")})
        assert answer["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert install_hooks(root) == []
        print("reinit adds PreToolUse, keeps the old recorder, and is idempotent")
        print("Write outside.txt after reinit =>", answer["hookSpecificOutput"]["permissionDecisionReason"])


if __name__ == "__main__":
    main()
