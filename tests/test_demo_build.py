"""docs/demo/build.sh, the rough cut: the storyboard it reads fits the rules, the narration becomes
subtitles over each scene's own footage, and rough.mp4 is refused for any take whose run was not live,
as the run's own recording says it (`graphene demo --once`), whatever the person passes."""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parents[1] / "docs" / "demo"
SHIPPED = Path(__file__).resolve().parents[1] / "src" / "graphene_map" / "demo.jsonl"
spec = importlib.util.spec_from_file_location("build", DEMO / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
needs_graphene = pytest.mark.skipif(
    shutil.which("graphene") is None, reason="needs graphene on PATH (uv run)"
)


def test_the_storyboard_is_under_three_minutes_and_each_line_can_be_said_in_its_scene():
    scenes = build.storyboard()
    assert sum(s["seconds"] for s in scenes) <= 175  # the rules' 180, less room for the cut labels
    for s in scenes:
        assert s["narration"], s
        assert len(s["narration"].split()) <= s["seconds"] * build.WORDS_A_SECOND, s
    tapes = sorted(p.name[:2] for p in (DEMO / "scenes").glob("[0-9][0-9]-*.tape"))
    assert tapes == [s["n"] for s in scenes]  # one tape a scene, and a scene for every tape


def test_every_tape_attaches_to_the_take_and_sets_what_build_rewrites():
    for tape in (DEMO / "scenes").glob("[0-9][0-9]-*.tape"):
        text = tape.read_text()
        for line in ("Output ", "Set Width ", "Set Height ", "Type 'source \"$FILM/attach\"'"):
            assert line in text, (tape.name, line)
        for wait in build.WAIT.finditer(text):
            assert int(wait["minutes"]) >= 1 and wait["what"]


def test_the_narration_is_spread_over_each_scenes_own_footage_in_order():
    scenes = [{"narration": "One. Two words here.", "filmed": 4.0}, {"narration": "Three.", "filmed": 2.5}]
    cues = [c.split("\n") for c in build.srt(scenes).strip().split("\n\n")]
    assert [c[2] for c in cues] == ["One.", "Two words here.", "Three."]
    assert cues[0][1].startswith("00:00:00,000 --> ") and cues[2][1] == "00:00:04,000 --> 00:00:06,500"


def take(tmp_path: Path, recording: str, rehearsal: bool = False) -> Path:
    t = tmp_path / "take"
    t.mkdir()
    (t / "run.jsonl").write_text(recording)
    (t / "stage.json").write_text(json.dumps({"rehearsal": rehearsal, "size": "120x36"}))
    (t / "scenes.json").write_text("[]")
    return t


def made_live(recording: str) -> str:
    """The shipped stand-in's recording, as it would read had its terminal and every call been Token
    Factory's: what a live take's recorder writes."""
    head, *lines = [json.loads(line) for line in recording.splitlines() if line]
    head |= {"stand_in": False, "shown": "as it ran, live"}
    for line in lines:
        for row in line.get("node_log") or []:
            if row["kind"] == "usage":
                row["detail"] = json.dumps(json.loads(row["detail"]) | {"endpoint": "token factory"})
    return "\n".join(json.dumps(x) for x in [head, *lines]) + "\n"


@needs_graphene
def test_rough_mp4_is_refused_for_a_take_whose_run_was_a_stand_in(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "HERE", tmp_path)
    t = take(tmp_path, SHIPPED.read_text())
    assert build.LIVE not in build.shown(t)
    with pytest.raises(SystemExit, match="rough.mp4 not written: the take's run was not live"):
        build.assemble(t, rehearsal=False)
    assert not (tmp_path / "rough.mp4").exists()


@needs_graphene
def test_a_take_with_no_recording_is_not_live_and_a_live_recording_is(tmp_path):
    t = take(tmp_path, made_live(SHIPPED.read_text()))
    assert build.LIVE in build.shown(t)
    (t / "run.jsonl").unlink()
    assert build.shown(t) == "no recording of the run"
    with pytest.raises(SystemExit, match="not live"):
        build.assemble(t, rehearsal=False)


def test_a_take_filmed_live_is_not_made_a_rehearsal_without_the_banner(tmp_path):
    t = take(tmp_path, "", rehearsal=False)
    with pytest.raises(SystemExit, match="without the rehearsal's top line"):
        build.assemble(t, rehearsal=True)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_a_clip_is_played_at_the_length_its_marks_say_it_took(tmp_path):
    """VHS caught 2 seconds of frames over 3 seconds of a busy machine: the clip plays for 3."""
    raw, clip = tmp_path / "a.raw.mp4", tmp_path / "a.mp4"
    black = "color=c=black:s=64x64:d=2:r=20"
    made = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", black, str(raw)],
                          capture_output=True)  # fmt: skip
    assert made.returncode == 0
    build.real_time(raw, clip, [100.0, 103.0])
    assert abs(build.seconds_of(clip) - 3.0) < 0.1
