"""Observe Codex's vendor policy when a hook crashes or times out. Scratch CODEX_HOME required."""

import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path


def main():
    home = Path(os.environ["CODEX_HOME"]).resolve()
    assert home != Path.home() / ".codex"
    real = subprocess.check_output(["/usr/bin/which", "codex"], text=True).strip()
    for mode, command in [("crash", "exit 1"), ("timeout", "sleep 3")]:
        root = Path(tempfile.mkdtemp(prefix=f"gv-hook-{mode}-", dir="/private/tmp"))
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
        marker = root / "hook-ran"
        command = f"printf ran >> {shlex.quote(str(marker))}; {command}"
        layer = root / ".codex"
        layer.mkdir()
        (layer / "hooks.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [{"hooks": [{"type": "command", "command": command, "timeout": 1}]}]
                    }
                }
            )
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
        cmd = [
            real,
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
            "Use apply_patch to add outside.txt containing hello. This is a disposable fixture. "
            "If the hook errors, report exactly what happened. Do not read outside this fixture.",
        ]
        result = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, timeout=180)
        print(mode, shlex.join(cmd[:-1]), "<fixture prompt>", flush=True)
        print(result.stdout, result.stderr, flush=True)
        exists = (root / "outside.txt").exists()
        print("outside.txt exists:", exists, "exit:", result.returncode, flush=True)
        print("hook actually ran:", marker.exists(), flush=True)
        assert marker.exists(), "hook did not run; cannot infer its failure policy"
        assert exists, "vendor failure policy changed; revisit README"


if __name__ == "__main__":
    main()
