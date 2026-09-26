"""`graphene demo`: a recorded run, replayed as `graphene watch` shows it, for someone with no key. The
recorder is run end to end by tests/test_demo_script.py, on the scripted stand-in; the recording Graphene
ships is the one made there, and says so."""

import json

from graphene_map import demo

JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0"
    ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
)


def test_a_recording_holds_no_path_of_yours_and_nothing_shaped_like_a_key(tmp_path, monkeypatch):
    """The repository's path is `{repo}`, the home directory `~`, the key in the environment and anything
    shaped like one are gone whole; ids, log names, shas and model names stay as they were."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("NEBIUS_API_KEY", "v1.not-shaped-like-one")
    root = tmp_path / "work" / "feeds"
    hide, _ = demo.hider(root)
    kept = "greet-20260926T034451-1106252f-1.txt nvidia/Llama-3_1-Nemotron-Ultra-253B-v1 9f86d081884c7d659a2f"
    said = hide(f"{root}/.graphene/runs/{kept} in {tmp_path}/elsewhere; {JWT}; v1.not-shaped-like-one")
    assert said == f"{{repo}}/.graphene/runs/{kept} in ~/elsewhere; {demo.REMOVED}; [removed]"
    detail = json.dumps({"checkout": f"{root}/.graphene/worktrees/greet", "token": f"Bearer {JWT}"})
    assert json.loads(hide({"detail": detail})["detail"]) == {
        "checkout": "{repo}/.graphene/worktrees/greet", "token": f"Bearer {demo.REMOVED}"
    }
