"""Make each of PR #60's real-editor walks fail on the behavior it claims to cover."""

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def main():
    base = Path(tempfile.mkdtemp(prefix="gv-ui-mutations-", dir="/private/tmp"))
    archive = base / "source.tar"
    with archive.open("wb") as out:
        subprocess.run(["git", "archive", "2a2c6fbb"], cwd=ROOT, stdout=out, check=True)
    subprocess.run(["tar", "-xf", str(archive), "-C", str(base)], check=True)
    (base / ".venv").symlink_to(ROOT / ".venv")
    ext = base / "editors/vscode"
    (ext / "node_modules").symlink_to(ROOT / "editors/vscode/node_modules")
    (ext / "e2e/node_modules").symlink_to(ROOT / "editors/vscode/e2e/node_modules")
    env = {
        **os.environ,
        "ZDOTDIR": "/private/tmp/graphene-verify-empty-zdot",
        "NEBIUS_API_KEY": "fake-key",
        "GRAPHENE_KEYCHAIN": "off",
        "GRAPHENE_TOKENFACTORY_URL": "http://127.0.0.1:9",
        "E2E_APP": "code",
    }

    def run(label, args, cwd):
        with (base / f"{label}.log").open("w") as log:
            code = subprocess.run(
                args, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=240
            ).returncode
        print(label, "exit", code, flush=True)
        return code

    assert run("package-control", ["npm", "run", "package"], ext) == 0
    for walk in ("home", "draw"):
        assert run(walk + "-control", ["npm", "run", walk], ext / "e2e") == 0
    cases = [
        ("draw", "commands.ts", 'argv.push("--forks", String(value))', 'argv.push("--forks", "1")'),
        ("home", "home/cards.ts", "exact && s.questions.length > 0", "false"),
    ]
    for walk, file, before, after in cases:
        path = ext / "src" / file
        original = path.read_text()
        assert before in original
        try:
            path.write_text(original.replace(before, after, 1))
            assert run(walk + "-package-mutant", ["npm", "run", "package"], ext) == 0
            assert run(walk + "-mutant", ["npm", "run", walk], ext / "e2e") != 0
            lines = (base / f"{walk}-mutant.log").read_text().splitlines()
            print(walk, "caught:", "\n".join(lines[-4:]), flush=True)
        finally:
            path.write_text(original)
    print("Both controls passed; both behavior mutations were caught. Scratch:", base)


if __name__ == "__main__":
    main()
