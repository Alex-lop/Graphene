"""Start Codex before init, install hooks while its first shell call waits, then observe its next patch."""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from graphene_map import plan
from graphene_map.store import Store


def main():
    home = Path(os.environ["CODEX_HOME"]).resolve()
    assert home != Path.home() / ".codex"
    root = Path(tempfile.mkdtemp(prefix="gv-mid-session-", dir="/private/tmp"))
    subprocess.run(["git", "init", "-q", str(root)], check=True)
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
            "--allow-empty",
        ],
        check=True,
    )
    (home / "config.toml").write_text(
        'model="gpt-6.1-sol"\nmodel_reasoning_effort="xhigh"\n'
        f'[projects.{json.dumps(str(root))}]\ntrust_level="trusted"\n'
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CLAUDE", "GRAPHENE_", "CODEX_")) and k != "AI_AGENT"
    }
    env.update(
        CODEX_HOME=str(home),
        ZDOTDIR="/private/tmp/graphene-verify-empty-zdot",
        NEBIUS_API_KEY="fake-key",
        GRAPHENE_KEYCHAIN="off",
        GRAPHENE_TOKENFACTORY_URL="http://127.0.0.1:9",
    )
    waiting, release = root / "waiting", root / "release"
    (root / "pause.py").write_text(
        'from pathlib import Path\nimport time\nPath("waiting").touch()\n'
        'while not Path("release").exists(): time.sleep(0.1)\n'
    )
    shell = "python3 pause.py"
    prompt = (
        f"First run this exact shell command and wait for it to finish: {shell}\n"
        "Then attempt apply_patch to add outside.txt containing hello. This is a disposable fixture "
        "testing hook installation during a session. Report any refusal; do not work around it. "
        "Do not read outside this fixture."
    )
    cmd = [
        "codex",
        "exec",
        "--json",
        "--ephemeral",
        "--enable",
        "hooks",
        "--dangerously-bypass-hook-trust",
        "--sandbox",
        "workspace-write",
        "-c",
        'model_reasoning_effort="xhigh"',
        prompt,
    ]
    with (root / "stream.jsonl").open("w") as out:
        proc = subprocess.Popen(cmd, cwd=root, env=env, stdout=out, stderr=subprocess.STDOUT)
        try:
            end = time.monotonic() + 120
            while not waiting.exists() and proc.poll() is None and time.monotonic() < end:
                time.sleep(0.1)
            assert waiting.exists(), "Codex did not reach the controlled pause"
            subprocess.run(
                ["graphene", "init", "--planner", "codex", "--executor", "codex"],
                cwd=root,
                env=env,
                capture_output=True,
                check=True,
            )
            with Store.open(root) as store:
                plan.propose(
                    store,
                    [{"title": "inside only", "scope": ["inside.txt"], "check": "true"}],
                    plan.Caller("alex", True),
                )
                plan.start(store, "n1", plan.Caller("fixture", False, "held-after-init"), root)
            release.touch()
            proc.wait(timeout=180)
        finally:
            release.touch()
            if proc.poll() is None:
                proc.wait(timeout=180)
        print("command: codex exec <pause, then patch>; graphene init during that pause")
        print((root / "stream.jsonl").read_text())
        print("outside.txt exists:", (root / "outside.txt").exists(), "exit:", proc.returncode)
        print("installed hook:", (root / ".codex/hooks.json").exists())


if __name__ == "__main__":
    main()
