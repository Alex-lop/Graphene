"""Capture `graphene ui` frames while a credential-free scripted mission runs.

    uv run --frozen python scripts/capture_ui_live_frames.py OUTPUT_DIR

Proposes the scripted-local fixture mission into a private temporary state
directory, starts `graphene ui --frames` against it through the read-only
store handle, then approves the plan (which runs the fixture workers to
`awaiting_result`) and waits for the dump to stop. Writes the frames and a
README naming every node-state transition the viewer observed. macOS only:
the scripted fixture needs /usr/bin/sandbox-exec. Spends nothing.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABEL_RE = re.compile(r"[│┃] ([a-z_]+) +[│┃]")
STATE_RE = re.compile(r"[│┃] [^ ] ([a-z_]+)")


def node_states(frame: str) -> list[tuple[str, str]]:
    """Pair every card's label line with the state line beneath it."""

    lines = frame.splitlines()
    pairs: list[tuple[str, str]] = []
    for index in range(len(lines) - 1):
        labels = LABEL_RE.findall(lines[index])
        states = STATE_RE.findall(lines[index + 1])
        if labels and len(labels) == len(states):
            pairs.extend(zip(labels, states, strict=True))
    return pairs


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write(__doc__)
        return 2
    output = Path(argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / "backend"))
    from graphene.orchestration.scripted import load_scenario, scripted_supported

    if not scripted_supported():
        sys.stderr.write("scripted-local needs the macOS fixture sandbox; nothing captured\n")
        return 3
    goal = load_scenario().goal
    with tempfile.TemporaryDirectory(prefix="graphene-ui-evidence-") as scratch:
        scratch_path = Path(scratch).resolve()
        state = scratch_path / "state"
        state.mkdir(mode=0o700)
        repo = scratch_path / "target"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "README.md").write_text("# Fixture target\n", encoding="utf-8")
        git_env = {**os.environ, "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
                   "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
        subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True, env=git_env)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "fixture"], check=True, env=git_env)
        env = {**os.environ, "GRAPHENE_STATE_DIR": str(state), "PYTHONPATH": str(ROOT / "backend"), "NO_COLOR": "1"}
        cli = [sys.executable, "-m", "graphene.cli.main"]
        subprocess.run([*cli, "init", "--repo", str(repo)], check=True, env=env, capture_output=True)
        proposed = subprocess.run(
            [*cli, "--json", "mission", "start", "--repo", str(repo), "--goal", goal, "--driver", "scripted-local"],
            check=True, env=env, capture_output=True, text=True,
        ).stdout
        mission_id = re.search(r'"mission_id":\s*"([^"]+)"', proposed).group(1)
        frames = output / "frames"
        viewer = subprocess.Popen(
            [*cli, "ui", "--mission", mission_id, "--frames", str(frames), "--poll", "0.02", "--max-seconds", "180"],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        approve = subprocess.run(
            [*cli, "--json", "mission", "approve-plan", mission_id, "--revision", "1",
             "--operator-label", "ui-evidence", "--rationale", "capture the live viewer"],
            env=env, capture_output=True, text=True,
        )
        out, err = viewer.communicate(timeout=240)
    transitions: list[str] = []
    seen: dict[str, str] = {}
    files = sorted(frames.glob("frame-*.txt"))
    for frame in files:
        for node, state in node_states(frame.read_text(encoding="utf-8")):
            if seen.get(node) != state:
                transitions.append(f"{frame.name}: {node} {seen.get(node, '—')} → {state}")
                seen[node] = state
    readme = output / "README.md"
    readme.write_text(
        "# `graphene ui` attached live to a scripted-local mission\n\n"
        f"Captured by `scripts/capture_ui_live_frames.py`. The viewer ran as a separate\n"
        f"process through `ReadOnlyMissionStore` (SQLite `mode=ro`, `query_only=ON`) while\n"
        f"`graphene mission approve-plan` ran the fixture workers. Mission `{mission_id}`;\n"
        f"approve-plan exit {approve.returncode}; viewer exit {viewer.returncode}; {len(files)} distinct frames.\n\n"
        "Credential-free scripted fixture: real scheduler, fixture workers, no model, no cloud.\n"
        "What this proves: node states change on screen while the mission runs, read-only.\n"
        "What it does not prove: a person watching a live model-driven mission.\n\n"
        "## Transitions observed\n\n" + "\n".join(f"- {line}" for line in transitions) + "\n\n"
        f"## Viewer stdout\n\n```\n{out.strip()}\n```\n",
        encoding="utf-8",
    )
    sys.stdout.write(f"{len(files)} frames, {len(transitions)} transitions -> {output}\n")
    return 0 if approve.returncode == 0 and viewer.returncode == 0 and len(transitions) > 6 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
