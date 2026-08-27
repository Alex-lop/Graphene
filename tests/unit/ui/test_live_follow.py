"""CP-B2: node states transition on screen while a scripted mission runs, read-only.

The mission runs in a separate process because that matches the real viewer.
SQLite connection lifecycles are now serialized within each process; the
separate lifecycle stress campaign guards the historical churn regression.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from graphene.cli.main import build_parser
from graphene.hashing import sha256_hex
from graphene.orchestration.scripted import load_scenario, scripted_supported
from graphene.ui.frames import compose_frame
from graphene.ui.read_only_store import ReadOnlyAttemptEvidenceStore, ReadOnlyMissionStore
from graphene.ui.run import build_source

ROOT = Path(__file__).parents[3]
requires_scripted = pytest.mark.skipif(
    not scripted_supported(), reason="the scripted-local fixture needs the macOS sandbox"
)


def _files_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _target_repository(path: Path) -> Path:
    path.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / "README.md").write_text("# Fixture target\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True, env=env)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "fixture"], check=True, env=env)
    return path


@requires_scripted
def test_live_viewer_sees_states_change_and_never_writes(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    repository = _target_repository(tmp_path / "target")
    env = {**os.environ, "GRAPHENE_STATE_DIR": str(state), "PYTHONPATH": str(ROOT / "backend"), "NO_COLOR": "1"}
    cli = [sys.executable, "-m", "graphene.cli.main"]
    subprocess.run([*cli, "init", "--repo", str(repository)], check=True, env=env, capture_output=True)
    proposed = subprocess.run(
        [*cli, "--json", "mission", "start", "--repo", str(repository), "--goal", load_scenario().goal, "--driver", "scripted-local"],
        check=True, env=env, capture_output=True, text=True,
    )
    mission_id = proposed.stdout.split('"mission_id":')[1].split('"')[1]
    runtime = state / "missions" / sha256_hex(mission_id.encode())[:32]

    source = build_source(build_parser().parse_args(["ui", "--state-dir", str(state), "--once"]))
    assert source.mission_id == mission_id  # the most recent active mission, found without --mission
    frames = [compose_frame(source)]
    assert "proposed" in frames[0].splitlines()[0] and "NOT AUTHORIZED — plan approval required" in frames[0]

    runner = subprocess.Popen(
        [*cli, "--json", "mission", "approve-plan", mission_id, "--revision", "1",
         "--operator-label", "ui-test", "--rationale", "run the fixture under the viewer"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        frame = compose_frame(source)
        if frame != frames[-1]:
            frames.append(frame)
        if "awaiting_result" in frame.splitlines()[0] and source.notice() is None:
            break
        time.sleep(0.02)
    out, err = runner.communicate(timeout=120)
    assert runner.returncode == 0, err

    banners = [frame.splitlines()[0] for frame in frames]
    assert any("running" in banner for banner in banners), banners
    assert "awaiting_result" in banners[-1] and "AUTHORIZED — revision 1 approved" in frames[-1]
    drawn = {line.strip() for frame in frames for line in frame.splitlines() if "● running" in line or "✓ done" in line}
    assert drawn, "no running or done node was ever drawn"
    assert all("->" not in frame for frame in frames)
    assert "projection refused" not in frames[-1]

    # Read-only, proven twice: the handles are the ro subclasses, and composing
    # the summary over the finished store changes no byte on disk.
    source = build_source(build_parser().parse_args(["ui", "--state-dir", str(state), "--mission", mission_id, "--once"]))
    files = [state / "missions.sqlite3", Path(str(state / "missions.sqlite3") + "-wal"), runtime / "attempt-evidence.sqlite3"]
    before = _files_digest(files)
    summary = compose_frame(source, pane="summary")
    final = source.snapshot()
    accepted = {path for item in final.publications if item.state == "accepted" for path in item.paths}
    assert "what was done" in summary and accepted and any(path in summary for path in accepted)
    assert str(final.result.state) in summary  # whatever the store says, not a guess
    assert _files_digest(files) == before
    assert isinstance(source.store, ReadOnlyMissionStore)
    assert isinstance(source.store.artifact_resolver, ReadOnlyAttemptEvidenceStore)  # bound on first read
